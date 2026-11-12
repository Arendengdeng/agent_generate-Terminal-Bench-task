"""Small replaceable OpenAI-compatible Chat Completions client (stdlib only)."""
import json
import re
from typing import Protocol
import urllib.error
import urllib.request
from urllib.parse import urlsplit, quote

from .errors import BudgetExceeded, SynthesisError


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


class OpenAICompatibleClient:
    def __init__(self, config):
        self.config = config
        if not config.model:
            raise SynthesisError("configure SYNTHESIS_MODEL or --model")
        self.opener = urllib.request.build_opener(NoRedirect())

    def complete(self, messages, tools):
        c = self.config
        payload = {"model": c.model, "messages": messages, "tools": tools,
                   "tool_choice": "required", "parallel_tool_calls": False}
        if urlsplit(c.base_url).hostname == "api.deepseek.com":
            # Required tool choice is incompatible with DeepSeek thinking mode.
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
        try:
            with self.opener.open(request, timeout=c.api_timeout_sec) as response:
                raw = response.read(c.max_response_bytes + 1)
            if len(raw) > c.max_response_bytes:
                raise BudgetExceeded("model response byte budget exceeded")
            result = json.loads(raw)
            if result["choices"][0].get("finish_reason") == "length":
                raise SynthesisError("model response truncated by token limit")
            message = result["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("expected assistant message")
            return message
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read(min(c.max_response_bytes, 16_384) + 1)
                detail = api_error_detail(raw, c.api_key) if len(raw) <= min(c.max_response_bytes, 16_384) else ""
            except (OSError, ValueError):
                detail = ""
            finally:
                exc.close()
            raise SynthesisError(f"model API HTTP {exc.code}{detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SynthesisError(f"model API unavailable ({type(exc).__name__})") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise SynthesisError("malformed model API response") from exc
