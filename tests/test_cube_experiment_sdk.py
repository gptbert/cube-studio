"""Cube Studio 实验追踪 SDK 单测（Phase 4.2）。

通过 monkey-patch ``requests.post`` 验证：
- start / attach 构造路径
- log_metric / log_param / log_artifact / finish 各自发的 path 与 payload
- with-context-manager 异常时 status=failed
- CUBE_EXPERIMENT_DISABLE 时全 no-op
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from typing import List
from unittest import mock


def _load_sdk():
    """按文件路径直接 import SDK，避免依赖 job-template 路径。"""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    sdk_path = os.path.join(repo_root, 'job-template', 'job', 'pkgs', 'cube_experiment.py')
    spec = importlib.util.spec_from_file_location('cube_experiment', sdk_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sdk = _load_sdk()


class _Resp:
    def __init__(self, status_code: int = 200, json_body=None, text: str = ''):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text
        self.content = b'{}' if json_body is not None else b''

    def json(self):
        return self._json


class _RecordingPost:
    """记录所有 requests.post 调用，方便断言 path / payload。"""

    def __init__(self, response: _Resp | None = None):
        self.calls: List[dict] = []
        self.response = response or _Resp(200, {'id': 1, 'run_id': 'srv-run-1', 'status': 'running'})

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls.append({'url': url, 'json': json or {}, 'headers': headers or {}})
        return self.response


class StartAndAttachTests(unittest.TestCase):
    def test_start_posts_create_run_and_uses_server_run_id(self):
        recorder = _RecordingPost(_Resp(200, {'id': 9, 'run_id': 'srv-9', 'status': 'running'}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)), \
             mock.patch.dict(os.environ, {'CUBE_API_BASE_URL': 'http://api.test'}, clear=False):
            run = sdk.Run.start(name='m1', version='v1', project_id=42,
                                experiment_id='exp-A', framework='pytorch')
        self.assertEqual(run.run_id, 'srv-9')
        self.assertEqual(len(recorder.calls), 1)
        call = recorder.calls[0]
        self.assertTrue(call['url'].endswith('/training_model_modelview/api/run'))
        self.assertEqual(call['json']['name'], 'm1')
        self.assertEqual(call['json']['project_id'], 42)
        self.assertEqual(call['json']['experiment_id'], 'exp-A')

    def test_start_falls_back_to_env_project_id_when_omitted(self):
        recorder = _RecordingPost()
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)), \
             mock.patch.dict(os.environ, {'CUBE_PROJECT_ID': '77'}, clear=False):
            sdk.Run.start(name='m1', version='v1')
        self.assertEqual(recorder.calls[0]['json']['project_id'], 77)

    def test_attach_does_not_post(self):
        recorder = _RecordingPost()
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)):
            run = sdk.Run.attach(run_id='existing-run')
        self.assertEqual(run.run_id, 'existing-run')
        self.assertEqual(recorder.calls, [])

    def test_attach_reads_env_var_when_no_arg(self):
        recorder = _RecordingPost()
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)), \
             mock.patch.dict(os.environ, {'CUBE_RUN_ID': 'env-run-99'}, clear=False):
            run = sdk.Run.attach()
        self.assertEqual(run.run_id, 'env-run-99')

    def test_attach_raises_when_no_run_id(self):
        with mock.patch.dict(os.environ, {'CUBE_RUN_ID': ''}, clear=False), \
             self.assertRaises(ValueError):
            sdk.Run.attach()


class LogTests(unittest.TestCase):
    def setUp(self):
        self.recorder = _RecordingPost(_Resp(200, {}))
        self._patch = mock.patch.object(sdk, 'requests', mock.MagicMock(post=self.recorder))
        self._patch.start()
        self.run = sdk.Run.attach(run_id='r-test')

    def tearDown(self):
        self._patch.stop()

    def test_log_metric_posts_correct_payload(self):
        self.run.log_metric('val_acc', 0.93)
        call = self.recorder.calls[0]
        self.assertTrue(call['url'].endswith('/training_model_modelview/api/run/r-test/log'))
        self.assertEqual(call['json'], {'type': 'metric', 'key': 'val_acc', 'value': 0.93})

    def test_log_param_posts_correct_payload(self):
        self.run.log_param('lr', 0.01)
        self.assertEqual(self.recorder.calls[0]['json'],
                         {'type': 'param', 'key': 'lr', 'value': 0.01})

    def test_log_artifact_posts_correct_payload(self):
        self.run.log_artifact('/mnt/m.pt')
        self.assertEqual(self.recorder.calls[0]['json'],
                         {'type': 'artifact', 'path': '/mnt/m.pt'})

    def test_log_metrics_batch_makes_n_calls(self):
        self.run.log_metrics({'a': 0.1, 'b': 0.2, 'c': 0.3})
        self.assertEqual(len(self.recorder.calls), 3)


class FinishTests(unittest.TestCase):
    def test_finish_includes_optional_fields_when_set(self):
        recorder = _RecordingPost(_Resp(200, {}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)):
            run = sdk.Run.attach(run_id='r1')
            run.set_log_url('http://tb/run1')
            run.set_model_path('/mnt/m.pt', md5='deadbeef')
            run.finish(status='success')
        call = recorder.calls[0]
        self.assertTrue(call['url'].endswith('/training_model_modelview/api/run/r1/finish'))
        self.assertEqual(call['json'],
                         {'status': 'success', 'log_url': 'http://tb/run1',
                          'path': '/mnt/m.pt', 'md5': 'deadbeef'})

    def test_finish_idempotent(self):
        recorder = _RecordingPost(_Resp(200, {}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)):
            run = sdk.Run.attach(run_id='r1')
            run.finish('success')
            run.finish('success')  # 第二次应被 _closed 短路
        self.assertEqual(len(recorder.calls), 1)


class ContextManagerTests(unittest.TestCase):
    def test_normal_exit_finishes_with_success(self):
        recorder = _RecordingPost(_Resp(200, {}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)):
            with sdk.Run.attach(run_id='r1') as run:
                run.log_metric('acc', 0.9)
        # 1 次 log + 1 次 finish
        finish_call = recorder.calls[-1]
        self.assertTrue(finish_call['url'].endswith('/finish'))
        self.assertEqual(finish_call['json']['status'], 'success')

    def test_exception_exit_finishes_with_failed(self):
        recorder = _RecordingPost(_Resp(200, {}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)):
            with self.assertRaises(RuntimeError):
                with sdk.Run.attach(run_id='r1'):
                    raise RuntimeError('boom')
        self.assertEqual(recorder.calls[-1]['json']['status'], 'failed')


class DisableSwitchTests(unittest.TestCase):
    def test_disabled_sdk_makes_no_http_calls(self):
        recorder = _RecordingPost()
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)), \
             mock.patch.dict(os.environ, {'CUBE_EXPERIMENT_DISABLE': '1'}, clear=False):
            run = sdk.Run.start(name='m', version='v', project_id=1)
            run.log_metric('acc', 0.9)
            run.log_param('lr', 0.01)
            run.log_artifact('/mnt/m.pt')
            run.finish('success')
        self.assertEqual(recorder.calls, [])


class AuthHeaderTests(unittest.TestCase):
    def test_token_injected_as_bearer_header(self):
        recorder = _RecordingPost(_Resp(200, {}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)), \
             mock.patch.dict(os.environ, {'CUBE_API_TOKEN': 'tok-abc'}, clear=False):
            sdk.Run.attach(run_id='r1').log_metric('acc', 0.9)
        self.assertEqual(recorder.calls[0]['headers'].get('Authorization'), 'Bearer tok-abc')

    def test_no_token_means_no_auth_header(self):
        recorder = _RecordingPost(_Resp(200, {}))
        with mock.patch.object(sdk, 'requests', mock.MagicMock(post=recorder)), \
             mock.patch.dict(os.environ, {'CUBE_API_TOKEN': ''}, clear=False):
            sdk.Run.attach(run_id='r1').log_metric('acc', 0.9)
        self.assertNotIn('Authorization', recorder.calls[0]['headers'])


if __name__ == '__main__':
    unittest.main()
