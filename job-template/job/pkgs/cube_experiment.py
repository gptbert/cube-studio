"""Cube Studio 实验追踪 SDK（Phase 4.2）。

供 Pipeline / Notebook 训练任务在 **任务容器内** 调用，把超参、指标、产物、
状态等实验上下文写回 Cube Studio 的 Training_Model 表（model 表）。

依赖：仅 `requests`（pkgs/ 已有），不依赖 Flask / SQLAlchemy。

环境变量
--------
- ``CUBE_API_BASE_URL``  Cube Studio Web 入口（默认 ``http://kubeflow-dashboard.infra:80``，
  通常注入为内部 service 域名；外部环境直接给完整 URL）
- ``CUBE_API_TOKEN``     可选，作为 ``Authorization: Bearer <token>`` 透传
- ``CUBE_PROJECT_ID``    任务所属项目组 id；start() 调用未指定时回退到此环境变量
- ``CUBE_RUN_ID``        如果训练任务被 pipeline 拉起时已经分配了 run_id，
  set_active_run() / Run.attach() 可直接复用，避免重复创建

最小用法（推荐）
----------------
::

    from cube_experiment import Run

    with Run.start(name='resnet50', version='v2026.04.26.1',
                   experiment_id='exp-cv-baseline',
                   framework='pytorch') as run:
        run.log_param('lr', 0.001)
        run.log_param('batch_size', 32)
        for epoch, acc in train_loop():
            run.log_metric('val_acc', acc)
        run.log_artifact('/mnt/admin/models/resnet50.pt')
        run.set_log_url('http://tb.company.com/?run=resnet50-v2')
    # 退出 with 时自动 finish(status='success')；若 with 内抛异常则 status='failed'

附加用法
--------
- ``Run.attach(run_id)``：复用既有 run（典型场景：pipeline 在 start container 时
  已经创建了 run，task container 仅 attach 上去 log）
- 临时禁用上报：环境变量 ``CUBE_EXPERIMENT_DISABLE=1``，所有 SDK 调用变成 no-op
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    # 训练镜像里通常有 requests；离线环境下作为 no-op SDK 失败模式提示
    requests = None  # type: ignore


logger = logging.getLogger(__name__)


def _disabled() -> bool:
    return os.getenv('CUBE_EXPERIMENT_DISABLE', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _api_base_url() -> str:
    return os.getenv('CUBE_API_BASE_URL', 'http://kubeflow-dashboard.infra:80').rstrip('/')


def _auth_headers() -> dict:
    headers = {'Content-Type': 'application/json'}
    token = os.getenv('CUBE_API_TOKEN', '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _post(path: str, payload: dict, *, timeout: float = 5.0) -> Optional[dict]:
    """POST JSON 到 Cube Studio API；失败只记日志、不打断训练任务主流程。"""
    if _disabled():
        logger.debug('cube_experiment disabled, skip POST %s', path)
        return None
    if requests is None:
        logger.warning('cube_experiment: requests 未安装，跳过 POST %s', path)
        return None
    url = f'{_api_base_url()}{path}'
    try:
        resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=timeout)
        if resp.status_code >= 400:
            logger.warning('cube_experiment POST %s -> %d: %s', url, resp.status_code, resp.text[:200])
            return None
        return resp.json() if resp.content else {}
    except Exception as exc:  # noqa: BLE001 — SDK 不应让上报失败拖垮训练
        logger.warning('cube_experiment POST %s failed: %s', url, exc)
        return None


# ---------------------------------------------------------------------------
# Run 抽象
# ---------------------------------------------------------------------------


class Run:
    """单次训练 run 的 SDK 句柄，封装写入 API 调用。

    优先用 ``Run.start(...)`` / ``Run.attach(...)`` 构造，不直接 ``__init__``。
    """

    _BASE = '/training_model_modelview/api'

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._log_url: Optional[str] = None
        self._final_path: Optional[str] = None
        self._final_md5: Optional[str] = None
        self._closed = False

    # -- 构造：起新 run / 接管已有 run ---------------------------------------

    @classmethod
    def start(
        cls,
        *,
        name: str,
        version: str,
        project_id: Optional[int] = None,
        experiment_id: str = '',
        parent_run_id: str = '',
        framework: str = '',
        describe: str = '',
        run_id: Optional[str] = None,
        pipeline_id: int = 0,
    ) -> 'Run':
        """请求服务端创建一条 run，返回 SDK 句柄。"""
        if project_id is None:
            project_id = int(os.getenv('CUBE_PROJECT_ID', '0') or 0)
        payload = {
            'name': name,
            'version': version,
            'project_id': project_id,
            'experiment_id': experiment_id,
            'parent_run_id': parent_run_id,
            'framework': framework,
            'describe': describe,
            'pipeline_id': pipeline_id,
        }
        if run_id:
            payload['run_id'] = run_id
        result = _post(f'{cls._BASE}/run', payload)
        # 服务端返回 {id, run_id, status}；失败/禁用时也要返回一个 no-op Run
        actual_run_id = (result or {}).get('run_id') or run_id or os.getenv('CUBE_RUN_ID', '') or 'unknown'
        return cls(actual_run_id)

    @classmethod
    def attach(cls, run_id: Optional[str] = None) -> 'Run':
        """复用已存在的 run（不发起 POST），常用于 pipeline 多容器接续场景。"""
        rid = run_id or os.getenv('CUBE_RUN_ID', '').strip()
        if not rid:
            raise ValueError('Run.attach() 需要 run_id 或环境变量 CUBE_RUN_ID')
        return cls(rid)

    # -- log 系列 ------------------------------------------------------------

    def log_metric(self, key: str, value: float) -> None:
        _post(f'{self._BASE}/run/{self.run_id}/log',
              {'type': 'metric', 'key': key, 'value': value})

    def log_metrics(self, mapping: dict) -> None:
        for k, v in mapping.items():
            self.log_metric(k, v)

    def log_param(self, key: str, value: Any) -> None:
        _post(f'{self._BASE}/run/{self.run_id}/log',
              {'type': 'param', 'key': key, 'value': value})

    def log_params(self, mapping: dict) -> None:
        for k, v in mapping.items():
            self.log_param(k, v)

    def log_artifact(self, path: str) -> None:
        _post(f'{self._BASE}/run/{self.run_id}/log',
              {'type': 'artifact', 'path': path})

    def log_artifacts(self, paths: Iterable[str]) -> None:
        for p in paths:
            self.log_artifact(p)

    # -- 收尾元数据（合并到 finish 调用，减少一次 HTTP）---------------------

    def set_log_url(self, log_url: str) -> None:
        self._log_url = log_url

    def set_model_path(self, path: str, *, md5: Optional[str] = None) -> None:
        self._final_path = path
        if md5 is not None:
            self._final_md5 = md5

    # -- 结束 ----------------------------------------------------------------

    def finish(self, status: str = 'success') -> None:
        if self._closed:
            return
        payload: dict = {'status': status}
        if self._log_url is not None:
            payload['log_url'] = self._log_url
        if self._final_path is not None:
            payload['path'] = self._final_path
        if self._final_md5 is not None:
            payload['md5'] = self._final_md5
        _post(f'{self._BASE}/run/{self.run_id}/finish', payload)
        self._closed = True

    # -- with-context-manager：异常时自动 status=failed -----------------------

    def __enter__(self) -> 'Run':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.finish('failed' if exc_type is not None else 'success')


__all__ = ['Run']
