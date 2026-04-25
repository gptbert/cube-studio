"""Training model / experiment tracking services.

把"实验追踪"相关的查询、聚合、对比逻辑从 view 中抽离，view 只负责
HTTP 序列化与权限边界，业务逻辑集中在这里以便单元测试与复用。

设计要点：
- 纯函数 (parse_metrics / parse_params / group_runs_by_experiment / diff_runs)
  不接触 DB，输入是 dict / list，便于在 tests/ 下用纯 Python 数据构造跑通。
- DB 边界函数 (list_runs_in_experiment / get_run / latest_run_per_experiment)
  接受 dbsession 注入，默认走 myapp.db.session；测试可传内存 sqlite session。
- 不引入新外部依赖（沿用 SQLAlchemy + json）。

Phase 4.1 的实验追踪只覆盖"读 + 聚合 + 对比"，"写入" 仍由 pipeline/notebook
任务在结束时直接 INSERT Training_Model 行（沿用现状）。后续 Phase 4.2
再考虑通过 SDK 暴露 log_metric / log_artifact 接口。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from myapp import db
from myapp.models.model_train_model import Training_Model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 纯函数：JSON 解析 / 聚合 / 对比
# ---------------------------------------------------------------------------


def parse_metrics(raw: Optional[str]) -> Dict[str, float]:
    """把 Training_Model.metrics 解析成扁平 {name: value} dict。

    metrics 历史上可能存成：
      - dict:   {"acc": 0.93, "loss": 0.12}
      - list:   [{"acc": 0.93}, {"loss": 0.12}]   (老数据)
      - 空 / 非 JSON 文本：返回 {}
    解析失败时记 warning 但不抛，保证列表页不会因脏数据 500。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("metrics 字段解析失败: %r", raw[:80])
        return {}

    if isinstance(parsed, dict):
        return {str(k): _to_float(v) for k, v in parsed.items() if _is_scalar(v)}
    if isinstance(parsed, list):
        merged: Dict[str, float] = {}
        for item in parsed:
            if isinstance(item, dict):
                for k, v in item.items():
                    if _is_scalar(v):
                        merged[str(k)] = _to_float(v)
        return merged
    return {}


def parse_params(raw: Optional[str]) -> Dict[str, Any]:
    """把 Training_Model.params 解析成扁平 {name: value} dict。

    params 应当是 JSON dict；非 dict 或解析失败一律返回空 dict。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("params 字段解析失败: %r", raw[:80])
        return {}
    if isinstance(parsed, dict):
        return {str(k): v for k, v in parsed.items()}
    return {}


def parse_artifacts(raw: Optional[str]) -> List[str]:
    """把 Training_Model.artifacts 解析成 list[str]。

    artifacts 应当是 JSON list[str]；如存了单字符串路径则视作 1 元素列表，
    其他形态回退为空列表。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [raw] if isinstance(raw, str) else []
    if isinstance(parsed, list):
        return [str(x) for x in parsed if x is not None]
    if isinstance(parsed, str):
        return [parsed]
    return []


def group_runs_by_experiment(runs: Iterable[Mapping[str, Any]]) -> Dict[str, List[Mapping[str, Any]]]:
    """按 experiment_id 把 run 分组。

    入参为可迭代的 mapping（dict / SQLAlchemy row），每项至少包含 experiment_id 字段。
    空 / None 的 experiment_id 统一归到 "" key 下，调用方决定是否单独展示。
    """
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for run in runs:
        key = (run.get('experiment_id') or '').strip()
        grouped.setdefault(key, []).append(run)
    return grouped


def diff_runs(
    base: Mapping[str, Any], target: Mapping[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """对比两个 run 的 params / metrics 差异。

    返回结构：
      {
        "params":  {"key": {"base": .., "target": .., "changed": bool}, ...},
        "metrics": {"key": {"base": .., "target": .., "delta": float|None}, ...},
      }
    用于前端"实验对比"卡片直接渲染。
    """
    base_params = parse_params(base.get('params'))
    target_params = parse_params(target.get('params'))
    base_metrics = parse_metrics(base.get('metrics'))
    target_metrics = parse_metrics(target.get('metrics'))

    params_diff: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(base_params) | set(target_params)):
        b = base_params.get(key)
        t = target_params.get(key)
        params_diff[key] = {'base': b, 'target': t, 'changed': b != t}

    metrics_diff: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(base_metrics) | set(target_metrics)):
        b = base_metrics.get(key)
        t = target_metrics.get(key)
        delta: Optional[float]
        if b is not None and t is not None:
            delta = t - b
        else:
            delta = None
        metrics_diff[key] = {'base': b, 'target': t, 'delta': delta}

    return {'params': params_diff, 'metrics': metrics_diff}


# ---------------------------------------------------------------------------
# DB 边界函数
# ---------------------------------------------------------------------------


def list_runs_in_experiment(
    experiment_id: str,
    *,
    project_id: Optional[int] = None,
    dbsession=None,
    limit: int = 200,
) -> List[Training_Model]:
    """取一个 experiment 下的所有 run，按 changed_on 倒序，最多 limit 条。

    project_id 提供时叠加过滤；dbsession 缺省走全局 db.session（生产路径），
    测试可传 sqlite 内存 session。
    """
    if not experiment_id:
        return []
    session = dbsession if dbsession is not None else db.session
    query = session.query(Training_Model).filter(
        Training_Model.experiment_id == experiment_id,
    )
    if project_id is not None:
        query = query.filter(Training_Model.project_id == project_id)
    query = query.order_by(Training_Model.changed_on.desc()).limit(limit)
    return query.all()


def latest_run_per_experiment(
    *, project_id: Optional[int] = None, dbsession=None
) -> Dict[str, Training_Model]:
    """每个 experiment_id 返回最新的一条 run，便于实验列表概览。

    返回 {experiment_id: Training_Model}。空 experiment_id 不进入结果。
    """
    session = dbsession if dbsession is not None else db.session
    query = session.query(Training_Model)
    if project_id is not None:
        query = query.filter(Training_Model.project_id == project_id)
    query = query.order_by(Training_Model.changed_on.desc())
    rows = query.all()
    latest: Dict[str, Training_Model] = {}
    for row in rows:
        exp = (row.experiment_id or '').strip()
        if not exp:
            continue
        latest.setdefault(exp, row)
    return latest


def get_run(run_id: str, *, dbsession=None) -> Optional[Training_Model]:
    """按 run_id 精确取一条 run，None 表示未找到。"""
    if not run_id:
        return None
    session = dbsession if dbsession is not None else db.session
    return session.query(Training_Model).filter(Training_Model.run_id == run_id).first()


def diff_two_runs_by_id(
    base_run_id: str, target_run_id: str, *, dbsession=None
) -> Tuple[Optional[Training_Model], Optional[Training_Model], Dict[str, Dict[str, Any]]]:
    """便捷封装：按 run_id 取两条 run 并直接 diff，便于 view 直接使用。"""
    base = get_run(base_run_id, dbsession=dbsession)
    target = get_run(target_run_id, dbsession=dbsession)
    if base is None or target is None:
        return base, target, {'params': {}, 'metrics': {}}
    payload = diff_runs(_to_mapping(base), _to_mapping(target))
    return base, target, payload


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _to_mapping(row: Any) -> Mapping[str, Any]:
    """把 SQLAlchemy row 包装成普通 dict-like，方便纯函数处理。"""
    return {
        'metrics': getattr(row, 'metrics', None),
        'params': getattr(row, 'params', None),
        'artifacts': getattr(row, 'artifacts', None),
        'experiment_id': getattr(row, 'experiment_id', None),
        'parent_run_id': getattr(row, 'parent_run_id', None),
        'status': getattr(row, 'status', None),
        'log_url': getattr(row, 'log_url', None),
    }
