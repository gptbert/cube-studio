"""Phase 4.1 实验追踪服务单测。

只覆盖纯函数与 DB 边界的"逻辑层"，不启动 Flask app / 不连真实数据库。
DB 边界函数通过传入轻量 fake session（鸭子类型）来验证 SQLAlchemy 查询装配。

设计：
- parse_metrics / parse_params / parse_artifacts：脏数据容错
- group_runs_by_experiment：分组语义
- diff_runs：params 变更 + metrics delta 计算
- list_runs_in_experiment / latest_run_per_experiment / get_run / diff_two_runs_by_id：
  使用 _FakeSession 验证查询过滤与降序入库
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
import unittest
from typing import Any, Iterable, List


# ---------------------------------------------------------------------------
# 在 import 服务模块前，stub 掉 myapp / myapp.models 的依赖，
# 避免拉起整个 Flask + SQLAlchemy 注册体系。
# myapp 与其子包注册成"虚拟 package"（带 __path__），让相对/绝对 import 都能解析。
# ---------------------------------------------------------------------------


def _make_pkg(name: str) -> types.ModuleType:
    pkg = types.ModuleType(name)
    pkg.__path__ = []  # 标记为 package
    sys.modules[name] = pkg
    return pkg


def _install_stubs() -> None:
    if 'myapp.services.training_model_service' in sys.modules:
        return  # 已加载，幂等

    if 'myapp' not in sys.modules:
        myapp_pkg = _make_pkg('myapp')
        myapp_pkg.db = types.SimpleNamespace(session=None)

    if 'myapp.models' not in sys.modules:
        _make_pkg('myapp.models')

    if 'myapp.models.model_train_model' not in sys.modules:
        model_train_module = types.ModuleType('myapp.models.model_train_model')

        class _StubColumn:
            """足够还原 SQLAlchemy column 上的 ==、in_、desc 调用。"""

            def __init__(self, name: str):
                self.name = name

            def __eq__(self, other):  # noqa: D401 (用于 query.filter 的语法占位)
                return ('eq', self.name, other)

            def in_(self, items):
                return ('in', self.name, list(items))

            def desc(self):
                return ('desc', self.name)

            def __hash__(self):
                return hash(self.name)

        class _StubTrainingModel:
            # 类属性：用于 query.filter(Training_Model.xxx == ...) 这类调用
            experiment_id = _StubColumn('experiment_id')
            project_id = _StubColumn('project_id')
            run_id = _StubColumn('run_id')
            changed_on = _StubColumn('changed_on')

            def __init__(self, **kwargs):
                # 允许 start_run() 内部 Training_Model(name=..., version=..., ...) 实例化
                # 再赋值字段；shadow class-level _StubColumn 以便后续读写
                for k, v in kwargs.items():
                    object.__setattr__(self, k, v)
                self.id = None  # 模拟自增主键（commit 后由 _FakeSession 赋值）

        model_train_module.Training_Model = _StubTrainingModel
        sys.modules['myapp.models.model_train_model'] = model_train_module

    if 'myapp.services' not in sys.modules:
        _make_pkg('myapp.services')

    # 直接按文件路径加载真实 service 模块
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    svc_path = os.path.join(repo_root, 'myapp', 'services', 'training_model_service.py')
    spec = importlib.util.spec_from_file_location(
        'myapp.services.training_model_service', svc_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['myapp.services.training_model_service'] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)


_install_stubs()

from myapp.services import training_model_service as svc  # noqa: E402


# ---------------------------------------------------------------------------
# 纯函数测试
# ---------------------------------------------------------------------------


class ParseMetricsTests(unittest.TestCase):
    def test_dict_metrics(self):
        self.assertEqual(svc.parse_metrics('{"acc": 0.93, "loss": 0.12}'),
                         {'acc': 0.93, 'loss': 0.12})

    def test_legacy_list_metrics(self):
        # 老数据：list of single-key dicts
        raw = json.dumps([{'acc': 0.91}, {'loss': 0.18}])
        self.assertEqual(svc.parse_metrics(raw), {'acc': 0.91, 'loss': 0.18})

    def test_empty_and_invalid(self):
        self.assertEqual(svc.parse_metrics(None), {})
        self.assertEqual(svc.parse_metrics(''), {})
        self.assertEqual(svc.parse_metrics('not-json'), {})

    def test_drops_non_scalar_values(self):
        raw = json.dumps({'acc': 0.9, 'note': 'best so far', 'flag': True})
        # bool 也会被 _is_scalar 排除（bool 是 int 子类，但我们显式排除）
        self.assertEqual(svc.parse_metrics(raw), {'acc': 0.9})


class ParseParamsTests(unittest.TestCase):
    def test_dict(self):
        self.assertEqual(svc.parse_params('{"lr": 0.01, "bs": 32}'),
                         {'lr': 0.01, 'bs': 32})

    def test_non_dict_returns_empty(self):
        self.assertEqual(svc.parse_params('[1,2,3]'), {})
        self.assertEqual(svc.parse_params('garbage'), {})
        self.assertEqual(svc.parse_params(None), {})


class ParseArtifactsTests(unittest.TestCase):
    def test_list(self):
        raw = json.dumps(['/mnt/a.pt', '/mnt/eval.json'])
        self.assertEqual(svc.parse_artifacts(raw), ['/mnt/a.pt', '/mnt/eval.json'])

    def test_single_string_fallback(self):
        # 单字符串路径（非 JSON）兜底为 1 元素列表
        self.assertEqual(svc.parse_artifacts('/mnt/single.pt'), ['/mnt/single.pt'])

    def test_empty_and_none(self):
        self.assertEqual(svc.parse_artifacts(''), [])
        self.assertEqual(svc.parse_artifacts(None), [])


class GroupByExperimentTests(unittest.TestCase):
    def test_groups_correctly_and_keeps_blank_bucket(self):
        runs = [
            {'run_id': 'r1', 'experiment_id': 'exp-A'},
            {'run_id': 'r2', 'experiment_id': 'exp-A'},
            {'run_id': 'r3', 'experiment_id': 'exp-B'},
            {'run_id': 'r4', 'experiment_id': ''},
            {'run_id': 'r5', 'experiment_id': None},
        ]
        grouped = svc.group_runs_by_experiment(runs)
        self.assertEqual(set(grouped.keys()), {'exp-A', 'exp-B', ''})
        self.assertEqual([r['run_id'] for r in grouped['exp-A']], ['r1', 'r2'])
        self.assertEqual([r['run_id'] for r in grouped['exp-B']], ['r3'])
        self.assertEqual([r['run_id'] for r in grouped['']], ['r4', 'r5'])


class DiffRunsTests(unittest.TestCase):
    def test_full_diff(self):
        base = {
            'params': json.dumps({'lr': 0.01, 'bs': 32}),
            'metrics': json.dumps({'acc': 0.90, 'loss': 0.30}),
        }
        target = {
            'params': json.dumps({'lr': 0.005, 'bs': 32, 'dropout': 0.1}),
            'metrics': json.dumps({'acc': 0.93}),
        }
        out = svc.diff_runs(base, target)

        self.assertEqual(out['params']['lr'], {'base': 0.01, 'target': 0.005, 'changed': True})
        self.assertEqual(out['params']['bs'], {'base': 32, 'target': 32, 'changed': False})
        self.assertEqual(out['params']['dropout'], {'base': None, 'target': 0.1, 'changed': True})

        self.assertAlmostEqual(out['metrics']['acc']['delta'], 0.03)
        # loss 只在 base 存在 → delta=None
        self.assertEqual(out['metrics']['loss'], {'base': 0.30, 'target': None, 'delta': None})

    def test_empty_inputs(self):
        out = svc.diff_runs({}, {})
        self.assertEqual(out, {'params': {}, 'metrics': {}})


# ---------------------------------------------------------------------------
# DB 边界：用 _FakeSession 验证查询装配 + 结果提取
# ---------------------------------------------------------------------------


class _FakeQuery:
    """足够还原 svc 用到的 query.filter / order_by / limit / all / first 链式调用。"""

    def __init__(self, rows: List[Any]):
        self.rows = rows
        self.calls: List[str] = []

    def filter(self, *args, **kwargs):
        self.calls.append('filter')
        return self

    def order_by(self, *args, **kwargs):
        self.calls.append('order_by')
        return self

    def limit(self, n: int):
        self.calls.append(f'limit:{n}')
        self._limit = n
        return self

    def all(self):
        rows = self.rows
        if hasattr(self, '_limit'):
            rows = rows[: self._limit]
        return rows

    def first(self):
        return self.rows[0] if self.rows else None


class _FakeSession:
    """轻量 SQLAlchemy-like session：支持 query / add / commit。

    add 把新 row 放进 _rows，commit 给最新无 id 的 row 分配自增 id；
    query 返回的 _FakeQuery 直接对当前 _rows 做线性过滤（仅 run_id 等值）。
    """

    def __init__(self, rows: Iterable[Any] = ()):
        self._rows: List[Any] = list(rows)
        self._next_id = (max([getattr(r, 'id', 0) or 0 for r in self._rows], default=0) or 0) + 1
        self.last_query: _FakeQuery | None = None
        self.commits = 0

    def query(self, _model):
        # 默认返回全量 rows；测试可在 _FakeQuery 上叠 filter/order_by/limit
        self.last_query = _FakeQuery(self._rows)
        return self.last_query

    def add(self, row: Any) -> None:
        self._rows.append(row)

    def commit(self) -> None:
        # 模拟自增主键
        for row in self._rows:
            if getattr(row, 'id', None) is None:
                row.id = self._next_id
                self._next_id += 1
        self.commits += 1


class _Row(types.SimpleNamespace):
    """简化 Training_Model row 的鸭子类型。"""


class DBBoundaryTests(unittest.TestCase):
    def test_list_runs_in_experiment_returns_filtered_rows(self):
        rows = [_Row(run_id='r1', experiment_id='exp-A'),
                _Row(run_id='r2', experiment_id='exp-A')]
        session = _FakeSession(rows)
        out = svc.list_runs_in_experiment('exp-A', dbsession=session, limit=10)
        self.assertEqual([r.run_id for r in out], ['r1', 'r2'])
        self.assertIn('order_by', session.last_query.calls)
        self.assertIn('limit:10', session.last_query.calls)

    def test_list_runs_returns_empty_when_experiment_id_blank(self):
        session = _FakeSession([_Row(run_id='r1', experiment_id='exp-A')])
        self.assertEqual(svc.list_runs_in_experiment('', dbsession=session), [])
        # 早返回，未进 query
        self.assertIsNone(session.last_query)

    def test_list_runs_with_project_id_chains_extra_filter(self):
        session = _FakeSession([_Row(run_id='r1', experiment_id='exp-A', project_id=42)])
        svc.list_runs_in_experiment('exp-A', project_id=42, dbsession=session)
        # 两次 filter（experiment_id + project_id），一次 order_by
        self.assertEqual(session.last_query.calls.count('filter'), 2)

    def test_latest_run_per_experiment_dedups_keeping_first_seen(self):
        rows = [
            _Row(run_id='r1', experiment_id='exp-A'),  # 因为按 changed_on desc，r1 视为最新
            _Row(run_id='r2', experiment_id='exp-A'),  # 老的，被忽略
            _Row(run_id='r3', experiment_id='exp-B'),
            _Row(run_id='r4', experiment_id=''),       # 空 experiment_id 不计入
        ]
        session = _FakeSession(rows)
        latest = svc.latest_run_per_experiment(dbsession=session)
        self.assertEqual(set(latest.keys()), {'exp-A', 'exp-B'})
        self.assertEqual(latest['exp-A'].run_id, 'r1')
        self.assertEqual(latest['exp-B'].run_id, 'r3')

    def test_get_run_returns_first_match(self):
        session = _FakeSession([_Row(run_id='r-target', name='m1')])
        row = svc.get_run('r-target', dbsession=session)
        self.assertIsNotNone(row)
        self.assertEqual(row.run_id, 'r-target')

    def test_get_run_handles_blank_input(self):
        session = _FakeSession([])
        self.assertIsNone(svc.get_run('', dbsession=session))

    def test_diff_two_runs_by_id_returns_404_payload_when_missing(self):
        session = _FakeSession([])
        base, target, payload = svc.diff_two_runs_by_id('a', 'b', dbsession=session)
        self.assertIsNone(base)
        self.assertIsNone(target)
        self.assertEqual(payload, {'params': {}, 'metrics': {}})


# ---------------------------------------------------------------------------
# Phase 4.2 写入侧测试
# ---------------------------------------------------------------------------


class WriteSideTests(unittest.TestCase):
    def test_start_run_inserts_with_running_status_and_assigns_id(self):
        session = _FakeSession()
        row = svc.start_run(
            name='resnet50', version='v1', project_id=7,
            experiment_id='exp-A', framework='pytorch',
            dbsession=session,
        )
        self.assertEqual(row.name, 'resnet50')
        self.assertEqual(row.status, 'running')
        self.assertEqual(row.experiment_id, 'exp-A')
        self.assertEqual(row.metrics, '{}')
        self.assertEqual(row.params, '{}')
        self.assertEqual(row.artifacts, '[]')
        self.assertIsNotNone(row.run_id)
        self.assertEqual(row.id, 1)
        self.assertEqual(session.commits, 1)

    def test_start_run_respects_explicit_run_id(self):
        session = _FakeSession()
        row = svc.start_run(name='x', version='v1', project_id=1,
                            run_id='custom-run-xyz', dbsession=session)
        self.assertEqual(row.run_id, 'custom-run-xyz')

    def test_log_metric_merges_into_existing_dict(self):
        # 注意：_FakeQuery.first() 会返回第一行；测试中 fake session 只放一行
        target = _Row(run_id='r1', metrics='{"acc": 0.9}', params='{}', artifacts='[]')
        session = _FakeSession([target])
        row = svc.log_metric('r1', 'loss', 0.12, dbsession=session)
        self.assertIs(row, target)
        merged = json.loads(target.metrics)
        self.assertEqual(merged, {'acc': 0.9, 'loss': 0.12})
        self.assertEqual(session.commits, 1)

    def test_log_metric_returns_none_when_run_missing(self):
        session = _FakeSession([])
        self.assertIsNone(svc.log_metric('missing', 'acc', 0.9, dbsession=session))
        self.assertEqual(session.commits, 0)

    def test_log_param_handles_dirty_json(self):
        target = _Row(run_id='r1', metrics='{}', params='not-json', artifacts='[]')
        session = _FakeSession([target])
        svc.log_param('r1', 'lr', 0.001, dbsession=session)
        # 脏数据被吞掉，重新起步为 {key: value}
        self.assertEqual(json.loads(target.params), {'lr': 0.001})

    def test_log_artifact_dedupes(self):
        target = _Row(run_id='r1', metrics='{}', params='{}', artifacts='["/mnt/a.pt"]')
        session = _FakeSession([target])
        svc.log_artifact('r1', '/mnt/a.pt', dbsession=session)  # 重复
        svc.log_artifact('r1', '/mnt/b.pt', dbsession=session)
        self.assertEqual(json.loads(target.artifacts), ['/mnt/a.pt', '/mnt/b.pt'])

    def test_finish_run_updates_status_and_optional_fields(self):
        target = _Row(run_id='r1', metrics='{}', params='{}', artifacts='[]',
                      status='running', log_url='', path='', md5='')
        session = _FakeSession([target])
        svc.finish_run('r1', status='success',
                       log_url='http://tb/run1', path='/mnt/m.pt', md5='deadbeef',
                       dbsession=session)
        self.assertEqual(target.status, 'success')
        self.assertEqual(target.log_url, 'http://tb/run1')
        self.assertEqual(target.path, '/mnt/m.pt')
        self.assertEqual(target.md5, 'deadbeef')

    def test_finish_run_clamps_invalid_status_to_success(self):
        target = _Row(run_id='r1', metrics='{}', params='{}', artifacts='[]',
                      status='running', log_url='', path='', md5='')
        session = _FakeSession([target])
        svc.finish_run('r1', status='garbage', dbsession=session)
        self.assertEqual(target.status, 'success')

    def test_finish_run_returns_none_when_missing(self):
        session = _FakeSession([])
        self.assertIsNone(svc.finish_run('missing', dbsession=session))


if __name__ == '__main__':
    unittest.main()
