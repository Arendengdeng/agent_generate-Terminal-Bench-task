"""Small replaceable OpenAI-compatible Chat Completions client (stdlib only)."""
import json
import errno
import logging
import socket
import time
import re
from typing import Protocol
import urllib.error
import urllib.request
from urllib.parse import urlsplit, quote

from .errors import BudgetExceeded, SynthesisError
from .trace import redact


def transient_transport_error(error):
    """Retry only transport failures with their original cause; never parse messages."""
    if getattr(error, 'retry_handled', False):
        return False
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, urllib.error.HTTPError):
            return False
        if isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError)):
            return True
        error = error.__cause__
    return False


class ModelClient(Protocol):
    def complete(self, messages: list, tools: list) -> dict:
        """Return an assistant message containing tool_calls."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SynthesisError("model endpoint redirects are disabled")


def api_error_detail(raw, api_key):
    """Expose only selected JSON error fields, never headers or raw bodies."""
    try:
        error = json.loads(raw).get("error")
    except (ValueError, UnicodeError, AttributeError):
        return ""
    if not isinstance(error, dict):
        return ""
    fields = {}
    for name in ("type", "code", "message"):
        value = error.get(name)
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            continue
        value = str(value)
        if api_key:
            for secret in (api_key, quote(api_key, safe="")):
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\bBearer\s+[^\s\"',;}]+", "Bearer [REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
        value = re.sub(
            r'''(?ix)(\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)\b["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''',
            r"\1[REDACTED]", value)
        value = re.sub(r"https?://[^\s\"'<>]+", "[REDACTED URL]", value)
        fields[name] = value[:1000]
    return " " + json.dumps(fields, ensure_ascii=True) if fields else ""


def retryable_network_error(error):
    """Retry typed temporary transport failures only, never HTTP or string guesses."""
    seen = set()
    while isinstance(error, BaseException) and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, urllib.error.HTTPError):
            return False
        if isinstance(error, urllib.error.URLError):
            error = error.reason
            continue
        if isinstance(error, (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return True
        if isinstance(error, socket.gaierror):
            return error.errno == socket.EAI_AGAIN
        if isinstance(error, OSError) and error.errno in {
                errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED,
                errno.EPIPE, errno.EAGAIN, errno.EINTR}:
            return True
        error = error.__cause__
    return False


def exception_details(error, api_key='', secrets=()):
    """Bounded structured chain without traceback locals, headers or request bodies."""
    seen = set()
    def describe(exc, depth=0):
        if depth >= 8 or id(exc) in seen:
            return {'type': type(exc).__name__, 'truncated': True}
        seen.add(id(exc))
        message = str(exc)
        for secret in secrets:
            if secret:
                message = message.replace(secret, '[REDACTED]')
        message = redact(message, api_key)[:1000]
        result = {'type': type(exc).__name__, 'message': message}
        number = getattr(exc, 'errno', None)
        if type(number) is int:
            result['errno'] = number
        if isinstance(exc, urllib.error.HTTPError):
            result['http_status'] = exc.code
        if isinstance(exc, urllib.error.URLError):
            result['reason'] = describe(exc.reason, depth + 1)
        cause = getattr(exc, '__cause__', None)
        context = getattr(exc, '__context__', None)
        if cause is not None:
            result['cause'] = describe(cause, depth + 1)
        elif context is not None and not getattr(exc, '__suppress_context__', False):
            result['context'] = describe(context, depth + 1)
        return result
    return describe(error)


def complete_accounted(client, messages, tools, *, budget, config, on_retry, on_event):
    """Transport accounting only. Caller has already counted the first attempt."""
    reserve = len(json.dumps({'messages': messages, 'tools': tools}).encode()) + 4096 + config.max_completion_tokens
    def check_tokens():
        limit = budget.get('max_total_tokens')
        known = budget.get('token_usage', {}).get('total_tokens', 0)
        if limit is not None and known + budget.get('unknown_token_reserve', 0) + reserve > limit:
            raise BudgetExceeded('shared token budget cannot reserve next model attempt')

    def retry():
        check_tokens()
        if budget['model_calls'] >= config.max_model_calls:
            raise BudgetExceeded('shared model budget exhausted before transport retry')
        budget['model_calls'] += 1
        on_retry()

    def usage(value):
        if not isinstance(value, dict) or (type(value.get('total_tokens')) is not int or value['total_tokens'] < 0):
            budget['token_usage_complete'] = False
            budget.setdefault('usage_unknown_attempts', []).append(budget['model_calls'])
            budget['unknown_token_reserve'] = budget.get('unknown_token_reserve', 0) + reserve
        else:
            budget.setdefault('token_usage_complete', True)
        if isinstance(value, dict):
            totals = budget.setdefault('token_usage', {})
            for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                if type(value.get(key)) is int and value[key] >= 0:
                    totals[key] = totals.get(key, 0) + value[key]
        checkpoint = getattr(budget, 'checkpoint', None)
        if checkpoint is not None:
            checkpoint()

    check_tokens()
    if isinstance(client, OpenAICompatibleClient):
        return client.complete(messages, tools, before_retry=retry,
            on_event=lambda event: on_event({**event, 'model_call': budget['model_calls']}), on_usage=usage)
    # Injected/scripted clients retain their interface; no hidden retries here.
    try:
        return client.complete(messages, tools)
    finally:
        usage(getattr(client, 'last_usage', None))


class OpenAICompatibleClient:
    def __init__(self, config):
        self.config = config
        self.last_usage = None
        self.last_attempts = []
        self.attempt_count = 0
        if not config.model:
            raise SynthesisError("configure SYNTHESIS_MODEL or --model")
        self.opener = urllib.request.build_opener(NoRedirect())
        self._proxies = {}
        for handler in self.opener.handlers:
            if isinstance(handler, urllib.request.ProxyHandler):
                self._proxies.update(handler.proxies)

    def complete(self, messages, tools, *, before_retry=None, on_event=None, on_usage=None):
        self.last_usage = None
        self.last_attempts = []
        c = self.config
        payload = {"model": c.model, "messages": messages, "tools": tools,
                   "tool_choice": "required", "parallel_tool_calls": False}
        if urlsplit(c.base_url).hostname == "api.deepseek.com":
            payload.update(thinking={"type": "disabled"}, max_tokens=c.max_completion_tokens)
            payload.pop("parallel_tool_calls")
        else:
            payload["max_completion_tokens"] = c.max_completion_tokens
        data = json.dumps(payload).encode()
        if len(data) > c.max_context_bytes:
            raise BudgetExceeded("model context byte budget exceeded")
        headers = {"Content-Type": "application/json"}
        if c.api_key:
            headers["Authorization"] = "Bearer " + c.api_key
        request = urllib.request.Request(c.base_url.rstrip("/") + "/chat/completions", data=data, headers=headers)
        endpoint = urlsplit(c.base_url)
        proxy_configured = bool(self._proxies.get(endpoint.scheme))
        bypass = urllib.request.proxy_bypass(endpoint.hostname)
        proxy = {'configured': proxy_configured, 'bypassed': bool(bypass),
                 'used': proxy_configured and not bypass}
        secrets = []
        from urllib.parse import unquote
        for scheme, value in self._proxies.items():
            if scheme != 'no' and isinstance(value, str):
                try:
                    parsed = urlsplit(value if '://' in value else '//' + value)
                except ValueError:
                    continue
                secrets.extend(v for v in (parsed.username, parsed.password,
                               unquote(parsed.username or ''), unquote(parsed.password or '')) if v)
        for attempt in range(2):
            if self.attempt_count >= c.max_model_calls:
                raise BudgetExceeded('client model attempt budget exhausted')
            if attempt:
                if before_retry is not None:
                    before_retry()
                time.sleep(0.5)
            self.attempt_count += 1
            self.last_usage = None
            started = phase_started = time.monotonic()
            phase = 'open'
            record = {'attempt': attempt + 1, 'timeout_sec': c.api_timeout_sec, 'proxy': proxy}
            try:
                with self.opener.open(request, timeout=c.api_timeout_sec) as response:
                    record['http_status'] = getattr(response, 'status', None)
                    record['open_wall_sec'] = round(time.monotonic() - phase_started, 6)
                    phase, phase_started = 'read_body', time.monotonic()
                    raw = response.read(c.max_response_bytes + 1)
                    record['read_body_wall_sec'] = round(time.monotonic() - phase_started, 6)
                if len(raw) > c.max_response_bytes:
                    raise BudgetExceeded("model response byte budget exceeded")
                phase, phase_started = 'parse_response', time.monotonic()
                result = json.loads(raw)
                usage = result.get('usage')
                if isinstance(usage, dict):
                    self.last_usage = {k: v for k, v in usage.items()
                                       if k in {'prompt_tokens', 'completion_tokens', 'total_tokens',
                                                'prompt_tokens_details', 'completion_tokens_details'}}
                if result["choices"][0].get("finish_reason") == "length":
                    raise SynthesisError("model response truncated by token limit")
                message = result["choices"][0]["message"]
                if not isinstance(message, dict):
                    raise ValueError("expected assistant message")
                record.update(event='api_success', phase=phase)
                return message
            except Exception as exc:
                retrying = attempt == 0 and retryable_network_error(exc)
                record.update(event='api_failure', phase=phase, retry_scheduled=retrying,
                              exception=exception_details(exc, c.api_key, secrets))
                if retrying:
                    continue
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        raw = exc.read(min(c.max_response_bytes, 16_384) + 1)
                        detail = api_error_detail(raw, c.api_key) if len(raw) <= min(c.max_response_bytes, 16_384) else ''
                    except (OSError, ValueError):
                        detail = ''
                    finally:
                        exc.close()
                    failure = SynthesisError(f'model API HTTP {exc.code}{detail}')
                elif isinstance(exc, (urllib.error.URLError, OSError)):
                    failure = SynthesisError(f'model API unavailable ({type(exc).__name__})')
                elif isinstance(exc, (ValueError, KeyError, IndexError, TypeError)):
                    failure = SynthesisError('malformed model API response')
                elif isinstance(exc, SynthesisError):
                    failure = exc
                else:
                    failure = SynthesisError(f'model API request failed ({type(exc).__name__})')
                failure.retry_handled = True
                if failure is exc:
                    raise failure from None
                failure.api_failure = record
                raise failure from None
            finally:
                finished = time.monotonic()
                record.update(wall_sec=round(finished - started, 6),
                              phase_wall_sec=round(finished - phase_started, 6),
                              usage=redact(self.last_usage, c.api_key),
                              usage_status='known' if isinstance(self.last_usage, dict)
                                  and type(self.last_usage.get('total_tokens')) is int
                                  and self.last_usage['total_tokens'] >= 0 else 'unknown')
                self.last_attempts.append(record)
                if on_usage is not None:
                    on_usage(self.last_usage)
                if on_event is not None:
                    on_event(record)
                elif record.get('event') == 'api_failure':
                    logging.getLogger(__name__).warning('model_api_attempt %s', json.dumps(record))
