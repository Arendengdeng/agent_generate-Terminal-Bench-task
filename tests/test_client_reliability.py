"""Fault injection only; no external model or network access."""
import errno
import io
import json
from pathlib import Path
import socket
import ssl
import tempfile
import traceback
import unittest
from unittest.mock import patch
import urllib.error

from synthesis_agent.client import OpenAICompatibleClient, complete_accounted, retryable_network_error
from synthesis_agent.config import Config
from synthesis_agent.errors import BudgetExceeded, SynthesisError
from independent_verification.challenge import Calls


def response():
    return io.BytesIO(json.dumps({'choices':[{'message': {'role':'assistant','content':None,
        'tool_calls':[{'id':'r','type':'function','function':{'name':'review','arguments':'{"verdict":"confirmed","reason":"fixture"}'}}]}}],
        'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}}).encode())


class ClientReliabilityTests(unittest.TestCase):
    def client(self, **overrides):
        return OpenAICompatibleClient(Config(model='offline-fixture', **overrides))

    def accounted(self, client, budget, events, retries):
        return complete_accounted(client, [], [], config=client.config, budget=budget,
                                  on_retry=lambda: retries.append(True), on_event=events.append)

    def test_timeout_retry_counts_unknown_and_known_usage(self):
        client=self.client(); events=[]; retries=[]; budget={'model_calls':1,'tool_calls':0}
        with patch.object(client.opener,'open',side_effect=[urllib.error.URLError(TimeoutError(errno.ETIMEDOUT,'timed out')),response()]) as op, patch('synthesis_agent.client.time.sleep') as sleep:
            self.accounted(client,budget,events,retries)
        self.assertEqual(op.call_count,2); sleep.assert_called_once_with(.5)
        self.assertEqual(budget['model_calls'],2); self.assertEqual(retries,[True])
        self.assertEqual(budget['token_usage']['total_tokens'],14)
        self.assertFalse(budget['token_usage_complete']); self.assertEqual(budget['usage_unknown_attempts'],[1])
        self.assertGreater(budget['unknown_token_reserve'],0)
        self.assertEqual(events[0]['phase'],'open')
        reason=events[0]['exception']['reason']
        self.assertEqual(reason['type'],'TimeoutError'); self.assertEqual(reason['errno'],errno.ETIMEDOUT)
        self.assertEqual(events[0]['usage_status'],'unknown'); self.assertEqual(events[1]['usage_status'],'known')
        self.assertEqual([e['model_call'] for e in events],[1,2])
        self.assertIn('phase_wall_sec',events[0]); self.assertEqual(events[0]['timeout_sec'],90)

    def test_retry_never_exceeds_shared_budget(self):
        client=self.client(max_model_calls=1); budget={'model_calls':1,'tool_calls':0}
        with patch.object(client.opener,'open',side_effect=TimeoutError('timeout')) as op, patch('synthesis_agent.client.time.sleep') as sleep, self.assertRaises(BudgetExceeded):
            self.accounted(client,budget,[],[])
        self.assertEqual(op.call_count,1); sleep.assert_not_called()
        self.assertEqual(budget['model_calls'],1); self.assertEqual(budget['usage_unknown_attempts'],[1])

    def test_client_standalone_max_attempts_and_no_nested_challenge_retry(self):
        client=self.client(); budget={'model_calls':0,'tool_calls':0}
        with tempfile.TemporaryDirectory() as tmp, patch.object(client.opener,'open',side_effect=urllib.error.URLError(ConnectionResetError(errno.ECONNRESET,'reset'))) as op, patch('synthesis_agent.client.time.sleep'), self.assertRaises(SynthesisError):
            Calls(client.config,client,budget,Path(tmp)).complete([],[])
        self.assertEqual(op.call_count,2); self.assertEqual(budget['model_calls'],2)
        self.assertEqual(budget['usage_unknown_attempts'],[1,2]); self.assertNotIn('token_usage',budget)

    def test_http_auth_payment_and_server_errors_never_retry(self):
        for code in (400,401,402,403,429,500,503):
            with self.subTest(code=code):
                client=self.client(api_key='PRIVATE-API-KEY'); events=[]
                error=urllib.error.HTTPError('https://user:password@host/?token=secret',code,'PRIVATE-API-KEY',{},io.BytesIO(b'{}'))
                with patch.object(client.opener,'open',side_effect=error) as op, self.assertRaises(SynthesisError) as ctx:
                    client.complete([],[],on_event=events.append)
                self.assertEqual(op.call_count,1)
                self.assertEqual(events[0]['exception']['http_status'],code)
                rendered=''.join(traceback.format_exception(ctx.exception))
                self.assertNotIn('PRIVATE-API-KEY',rendered); self.assertNotIn('password',rendered)
                self.assertNotIn('PRIVATE-API-KEY',json.dumps(events))
                self.assertFalse(events[0]['retry_scheduled'])

    def test_read_failure_has_its_own_phase_and_one_retry(self):
        class Broken(io.BytesIO):
            def read(self,*args): raise TimeoutError('body timed out')
        client=self.client(); events=[]
        with patch.object(client.opener,'open',side_effect=[Broken(),response()]) as op, patch('synthesis_agent.client.time.sleep'):
            client.complete([],[],on_event=events.append)
        self.assertEqual(op.call_count,2); self.assertEqual(events[0]['phase'],'read_body')
        self.assertIn('open_wall_sec',events[0]); self.assertEqual(events[0]['exception']['type'],'TimeoutError')

    def test_parse_error_is_not_retried(self):
        client=self.client(); events=[]
        with patch.object(client.opener,'open',return_value=io.BytesIO(b'not-json')) as op, self.assertRaisesRegex(SynthesisError,'malformed'):
            client.complete([],[],on_event=events.append)
        self.assertEqual(op.call_count,1); self.assertEqual(events[0]['phase'],'parse_response')
        self.assertEqual(events[0]['exception']['type'],'JSONDecodeError')

    def test_proxy_and_exception_chain_are_redacted(self):
        proxies={'https':'http://proxy-user:proxy-password@proxy.invalid:8080'}
        with patch('urllib.request.getproxies',return_value=proxies),patch('urllib.request.proxy_bypass',return_value=False):
            client=self.client(api_key='PRIVATE-API-KEY')
            cause=OSError(errno.ECONNRESET,'api_key=OTHER-SECRET proxy-password PRIVATE-API-KEY https://user:secret@host/?q=private')
            error=urllib.error.URLError(cause)
            events=[]
            with patch.object(client.opener,'open',side_effect=error),patch('synthesis_agent.client.time.sleep'),self.assertRaises(SynthesisError):
                client.complete([],[],on_event=events.append)
        self.assertTrue(events[0]['proxy']['used'])
        rendered=json.dumps(events)
        for secret in ('OTHER-SECRET','proxy-password','PRIVATE-API-KEY','q=private','user:secret'):
            self.assertNotIn(secret,rendered)
        self.assertEqual(events[0]['exception']['reason']['errno'],errno.ECONNRESET)

    def test_permanent_dns_tls_and_untyped_url_errors_do_not_retry(self):
        for error in (urllib.error.URLError(socket.gaierror(socket.EAI_NONAME,'no such host')),
                      urllib.error.URLError(ssl.SSLCertVerificationError('certificate verification failed')),
                      urllib.error.URLError('unknown transport problem')):
            with self.subTest(error=type(error.reason).__name__):
                self.assertFalse(retryable_network_error(error))
                client=self.client()
                with patch.object(client.opener,'open',side_effect=error) as op,self.assertRaises(SynthesisError):
                    client.complete([],[],on_event=lambda e:None)
                self.assertEqual(op.call_count,1)
        self.assertTrue(retryable_network_error(urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN,'try again'))))
        self.assertTrue(retryable_network_error(ConnectionResetError('reset')))

    def test_synthesis_retry_is_counted_without_replaying_tools(self):
        from synthesis_agent.agent import SynthesisAgent
        from tests.helpers import FakeSandbox, candidate_calls, call, example
        client=self.client(); budget={'model_calls':0,'tool_calls':0}
        messages=candidate_calls()+[call('self_check'),call('finish')]
        bodies=[io.BytesIO(json.dumps({'choices':[{'message':m}],
            'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}}).encode()) for m in messages]
        with tempfile.TemporaryDirectory() as tmp, patch('synthesis_agent.agent.DockerSandbox',FakeSandbox), \
             patch.object(client.opener,'open',side_effect=[TimeoutError('timeout'),*bodies]) as op, \
             patch('synthesis_agent.client.time.sleep'):
            result=SynthesisAgent(client.config,client).generate(*example(),Path(tmp)/'candidate',budget=budget)
        self.assertEqual(result['status'],'candidate_generated')
        self.assertEqual(op.call_count,7); self.assertEqual(budget['model_calls'],7)
        self.assertEqual(result['budget_used']['model_calls']['used'],7)
        self.assertEqual(budget['tool_calls'],6); self.assertEqual(budget['usage_unknown_attempts'],[1])
        self.assertEqual(budget['token_usage']['total_tokens'],84)

    def test_token_reservation_blocks_call_and_preserves_unknown(self):
        client=self.client(); budget={'model_calls':1,'tool_calls':0,'max_total_tokens':1,
                                     'token_usage_complete':False,'usage_unknown_attempts':[0],'unknown_token_reserve':1}
        with patch.object(client.opener,'open') as op,self.assertRaises(BudgetExceeded):
            self.accounted(client,budget,[],[])
        op.assert_not_called(); self.assertFalse(budget['token_usage_complete'])
