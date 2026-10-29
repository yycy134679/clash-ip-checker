import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from core.clash_api import ClashController
from core.ip_checker import IPChecker
from core.node_check import NodeCheckRunner, NodeSwitchError
from core.results import source_result
from core.sources.browser import BrowserSource
from core.sources.ippure import IPPureSource
from core.sources.ping0 import Ping0Source
from state import AppState, TaskBusyError
from routers import api
from web import app


def controller():
    result = ClashController('http://unused.invalid')
    result.get_config = AsyncMock(return_value={'mode': 'rule'})
    result.get_proxies = AsyncMock(return_value={'GLOBAL': {'now': '原节点'}})
    result.set_mode = AsyncMock(return_value=True)
    result.switch_proxy = AsyncMock(return_value=True)
    result.get_running_port = AsyncMock(return_value=7897)
    return result


def payload():
    return {'ip': '203.0.113.1', 'pure_score': '0%', 'pure_emoji': '⚪',
            'source': 'ping0', 'full_string': '【⚪ 住宅|原生】', 'error': None}


class TaskLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.control = controller()
        self.checker = IPChecker()
        self.checker.check_sources = AsyncMock(return_value=payload())
        self.checker.stop = AsyncMock()
        self.state = AppState(checker=self.checker, controller_factory=lambda *a: self.control,
                              sleep=AsyncMock())
        self.state.nodes = [{'id': 42, 'name': '旧节点'}]
        self.state.events = [{'type': 'old'}]

    async def test_bad_input_preserves_previous_state_and_retry(self):
        with self.assertRaises(ValueError):
            self.state.start_batch({'proxies': [None]}, {})
        self.assertEqual(self.state.nodes[0]['name'], '旧节点')
        self.assertEqual(self.state.events, [{'type': 'old'}])
        self.assertFalse(self.state.is_running)
        self.state.start_batch({'proxies': [{'name': '有效'}]}, {})
        await self.state.task
        self.assertEqual(self.state.progress, 1)

    async def test_task_creation_failure_preserves_previous_state(self):
        with patch('state.asyncio.create_task', side_effect=RuntimeError('创建失败')):
            with self.assertRaisesRegex(RuntimeError, '创建失败'):
                self.state.start_batch({'proxies': [{'name': '有效'}]}, {})
        self.assertEqual(self.state.nodes[0]['name'], '旧节点')
        self.assertEqual(self.state.events, [{'type': 'old'}])
        self.assertIsNone(self.state.task)
        self.assertFalse(self.state.is_running)

    async def test_switch_failure_keeps_event_and_progress_in_sync(self):
        self.control.switch_proxy.side_effect = [False, True]
        self.state.start_batch({'proxies': [{'name': '有效'}]}, {})
        await self.state.task
        event = next(e for e in self.state.events if e['type'] == 'progress')
        self.assertEqual((self.state.progress, event['progress']), (1, 1))
        self.assertEqual(event['node']['status'], '❌ 切换失败')
        self.checker.check_sources.assert_not_awaited()
        self.assertEqual(self.control.switch_proxy.await_args_list[-1].args, ('GLOBAL', '原节点'))

    async def test_all_filtered_completes_without_changing_clash(self):
        self.state.start_batch({'proxies': [{'name': '到期'}]}, {'skip_keywords_str': '到期'})
        await self.state.task
        self.assertEqual(self.state.events[-1], {'type': 'complete', 'total': 0})
        self.control.set_mode.assert_not_awaited()

    async def test_cancel_before_batch_starts_releases_busy_state(self):
        self.state.start_batch({'proxies': [{'name': '有效'}]}, {})
        task = self.state.task
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.state.is_running)
        self.assertEqual(self.state.events[-1]['type'], 'complete')
        self.control.set_mode.assert_not_awaited()

    async def test_cancel_recheck_restores_and_releases_busy_state(self):
        entered = asyncio.Event()
        async def check(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        self.checker.check_sources.side_effect = check
        self.state.nodes = [{'id': 0, 'name': '节点', 'original_name': '节点',
                             'proxy_config': {'name': '节点'}}]
        task = asyncio.create_task(self.state.recheck_node(0, {}))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.control.switch_proxy.await_args_list[-1].args, ('GLOBAL', '原节点'))
        self.assertEqual(self.control.set_mode.await_args_list[-1].args, ('rule',))
        self.assertFalse(self.state.is_running)

    async def test_shutdown_waits_for_recheck_and_restoration(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def check(*args, **kwargs):
            entered.set()
            await release.wait()
            return payload()
        self.checker.check_sources.side_effect = check
        self.state.nodes = [{'id': 0, 'name': '手动', 'display_base_name': '手动',
                             'original_name': '节点', 'proxy_config': {'name': '节点'}}]
        recheck = asyncio.create_task(self.state.recheck_node(0, {'source': 'ping0'}))
        await entered.wait()
        with self.assertRaises(TaskBusyError):
            self.state.start_batch({'proxies': [{'name': '其他'}]}, {})
        shutdown = asyncio.create_task(self.state.shutdown())
        await asyncio.sleep(0)
        self.assertFalse(shutdown.done())
        self.checker.stop.assert_not_awaited()
        release.set()
        await recheck
        await shutdown
        self.assertEqual(self.control.switch_proxy.await_args_list[-1].args, ('GLOBAL', '原节点'))
        self.checker.stop.assert_awaited_once()
        self.assertFalse(self.state.is_running)


class ValidationTests(unittest.TestCase):
    def test_validate_and_start_reject_same_invalid_inputs(self):
        state = AppState()
        with patch.object(api, 'state', state), TestClient(app) as client:
            for text in ('[]', 'proxies: []', 'proxies: [null]', 'proxies: [{name: ""}]'):
                with self.subTest(text=text):
                    body = {'yaml_content': text}
                    self.assertEqual(client.post('/api/validate', json=body).status_code, 400)
                    self.assertEqual(client.post('/api/start', json=body).status_code, 400)
                    self.assertFalse(state.is_running)


class NodeRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_cache_and_failures(self):
        order = []
        async def switch(*args):
            order.append('switch')
            return True
        async def sleep(seconds):
            self.assertEqual(seconds, 1)
            order.append('wait')
        async def check(*args, **kwargs):
            order.append('check')
            self.assertFalse(kwargs['use_cache'])
            return payload()
        control = Mock(switch_proxy=AsyncMock(side_effect=switch))
        checker = Mock(check_sources=AsyncMock(side_effect=check))
        runner = NodeCheckRunner(control, checker, 'GLOBAL', 'http://proxy', sleep=sleep)
        self.assertEqual(await runner.check('节点', use_cache=False), payload())
        self.assertEqual(order, ['switch', 'wait', 'check'])
        control.switch_proxy.return_value = False
        control.switch_proxy.side_effect = None
        with self.assertRaises(NodeSwitchError):
            await runner.check('节点')
        self.assertEqual(order, ['switch', 'wait', 'check'])
        control.switch_proxy.return_value = True
        checker.check_sources.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await runner.check('节点')


class SourceParsingTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, source, module, response):
        session = AsyncMock()
        session.get.return_value = response
        manager = AsyncMock()
        manager.__aenter__.return_value = session
        with patch(module + '.AsyncSession', return_value=manager):
            return await source.check('http://proxy')

    async def test_ping0_parses_html_and_errors(self):
        html = "window.ip = '203.0.113.1'; <div class=\"riskitem riskcurrent\"><span class=\"value\">0%</span></div><i usecount=\"11\">"
        result = await self.fetch(Ping0Source(), 'core.sources.ping0', Mock(status_code=200, text=html))
        self.assertEqual((result['pure_score'], result['pure_emoji'], result['shared_users'], result['shared_emoji']),
                         ('0%', '⚪', '11', '🟡'))
        self.assertEqual(source_result('ping0', result)['status'], 'success')
        failure = await self.fetch(Ping0Source(), 'core.sources.ping0', Mock(status_code=503))
        self.assertEqual((failure['error'], failure['full_string']), ('HTTP 503', '【❌ HTTP 503】'))

    async def test_ippure_json_validation_and_format(self):
        for score, ip, expected in [(0, '203.0.113.1', 'success'), (None, '203.0.113.1', 'failed'),
                                    (101, '203.0.113.1', 'failed'), (10, '999.0.0.1', 'failed')]:
            with self.subTest(score=score, ip=ip):
                response = Mock(status_code=200)
                response.json.return_value = {'ip': ip, 'fraudScore': score, 'isResidential': True,
                                              'isBroadcast': False}
                result = await self.fetch(IPPureSource(), 'core.sources.ippure', response)
                self.assertEqual(source_result('ippure', result)['status'], expected)
                if score == 0:
                    self.assertEqual(result['full_string'], '【⚪ 住宅|原生】')
                    self.assertEqual(result['shared_users'], 'N/A')

    async def test_browser_parses_bot_and_closes_context(self):
        source = BrowserSource()
        page = AsyncMock()
        page.inner_text.return_value = '203.0.113.1\nIPPure系数 35%\nbot 8%\nIP属性\n住宅IP\nIP来源\n原生IP'
        context = AsyncMock()
        context.new_page.return_value = page
        source.browser = AsyncMock()
        source.browser.new_context.return_value = context
        result = await source.check('http://proxy')
        self.assertEqual((result['ip'], result['bot_score'], result['full_string']),
                         ('203.0.113.1', '8%', '【🟡⚪ 住宅|原生】'))
        context.close.assert_awaited_once()
        source.browser.new_context.assert_awaited_once()
        self.assertEqual(source.browser.new_context.await_args.kwargs['proxy'], {'server': 'http://proxy'})
