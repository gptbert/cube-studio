# 实验追踪

把每次训练 run 的**超参 / 指标 / 产物 / 状态 / 日志**统一记录到 `Training_Model` 表，
按 `experiment_id` 横向对比，按 `parent_run_id` 串成增量训练链。

> 引入版本：Phase 4.1（PR #13）+ Phase 4.2（PR #15）

## 数据模型

每个 run 是 `model` 表的一行，关键字段：

| 字段 | 含义 |
|---|---|
| `name` / `version` | 模型名 + 版本 |
| `run_id` | 全局唯一 run id |
| `experiment_id` | 实验分组（同实验下的 run 可纵向对比，**带索引**） |
| `parent_run_id` | 父 run id，用于增量训练 / 微调链路追溯 |
| `status` | `pending` / `running` / `success` / `failed` / `aborted` |
| `params` | JSON dict，训练超参 |
| `metrics` | JSON dict，训练 / 验证指标 |
| `artifacts` | JSON list，产物路径 |
| `log_url` | 外部日志链接（TensorBoard / Argo logs / 对象存储） |
| `framework` | 训练框架（pytorch / tf / xgb 等） |
| `path` | 主模型文件路径 |

## 写入：Python SDK

SDK 文件在 [`job-template/job/pkgs/cube_experiment.py`](../job-template/job/pkgs/cube_experiment.py)，**零依赖 myapp / Flask**，仅需 `requests`，可在任意训练镜像里 `import`。

### 推荐写法（with-context-manager）

```python
from cube_experiment import Run

with Run.start(
    name='resnet50',
    version='v2026.04.26.1',
    experiment_id='exp-cv-baseline',
    parent_run_id='',                       # 增量训练时填上一个 run_id
    framework='pytorch',
    describe='ResNet50 on COCO subset, lr sweep',
) as run:
    run.log_param('lr', 0.001)
    run.log_param('batch_size', 32)
    run.log_params({'optimizer': 'adamw', 'warmup': 500})

    for epoch, acc in train_loop():
        run.log_metric('val_acc', acc)
        run.log_metric('epoch', epoch)

    run.log_artifact('/mnt/admin/models/resnet50.pt')
    run.log_artifact('/mnt/admin/eval/resnet50_confusion.json')

    run.set_log_url('http://tb.company.com/?run=resnet50-v2')
    run.set_model_path('/mnt/admin/models/resnet50.pt', md5='deadbeef')
# 退出 with 自动 finish('success')；with 内抛异常自动 finish('failed')
```

### 复用已有 run（pipeline 多容器接续）

```python
# 第一个容器（pipeline 起点）
run = Run.start(name='resnet50', version='v1', experiment_id='exp-cv-baseline')
# 把 run.run_id 通过 pipeline output / 环境变量传给下一个容器

# 后续容器
run = Run.attach(run_id='<previous-run-id>')      # 不发起新 POST，复用
run.log_metric('val_acc', 0.95)
run.finish('success')
```

或通过环境变量 `CUBE_RUN_ID` 自动复用：

```python
run = Run.attach()  # 读 os.environ['CUBE_RUN_ID']
```

## 配置（环境变量）

| 变量 | 默认 | 用途 |
|---|---|---|
| `CUBE_API_BASE_URL` | `http://kubeflow-dashboard.infra:80` | Cube Studio Web 入口 |
| `CUBE_API_TOKEN` | （空） | 注入为 `Authorization: Bearer <token>` |
| `CUBE_PROJECT_ID` | `0` | `Run.start()` 未传 `project_id` 时回退 |
| `CUBE_RUN_ID` | （空） | `Run.attach()` 未传 `run_id` 时回退 |
| `CUBE_EXPERIMENT_DISABLE` | （空） | 设 `1` 全 no-op，本地调试时禁用 |

## HTTP API（直接调用）

不想用 SDK 时可直接打 HTTP：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/training_model_modelview/api/run` | 创建 run，返回 `{id, run_id, status}` |
| POST | `/training_model_modelview/api/run/<run_id>/log` | payload `{type: metric\|param\|artifact, key\|path, value?}` |
| POST | `/training_model_modelview/api/run/<run_id>/finish` | payload `{status, log_url?, path?, md5?}` |
| GET | `/training_model_modelview/api/experiment/<experiment_id>` | 拉一个实验下所有 run（含解析后的 metrics / params / artifacts） |
| GET | `/training_model_modelview/api/diff/<base_run_id>/<target_run_id>` | 对比两个 run 的 params / metrics 差异 |

## 查询：实验聚合 + run 对比

`模型管理 → 训练模型` 列表页支持按 `experiment_id` 筛选。

实验聚合（按 experiment_id 拉全部 run）：

```bash
curl http://<cube>/training_model_modelview/api/experiment/exp-cv-baseline
```

返回：

```json
{
  "experiment_id": "exp-cv-baseline",
  "count": 3,
  "runs": [
    {"id": 12, "run_id": "...", "name": "resnet50", "version": "v2026.04.26.1",
     "status": "success", "framework": "pytorch",
     "metrics": {"val_acc": 0.93, "loss": 0.12},
     "params": {"lr": 0.001, "batch_size": 32},
     "artifacts": ["/mnt/admin/models/resnet50.pt"],
     "log_url": "http://tb.company.com/?run=resnet50-v2",
     "changed_on": "2026-04-26 10:23:45"}
  ]
}
```

两个 run 直接对比：

```bash
curl http://<cube>/training_model_modelview/api/diff/<base_run_id>/<target_run_id>
```

返回：

```json
{
  "base":   {"run_id": "...", "name": "resnet50", "version": "v1"},
  "target": {"run_id": "...", "name": "resnet50", "version": "v2"},
  "diff": {
    "params":  {"lr": {"base": 0.01, "target": 0.005, "changed": true},
                "bs": {"base": 32,   "target": 32,    "changed": false}},
    "metrics": {"val_acc": {"base": 0.90, "target": 0.93, "delta": 0.03},
                "loss":    {"base": 0.30, "target": null, "delta": null}}
  }
}
```

## 设计原则

- **非侵入**：不上报也能用（旧训练脚本直接跑，不报错）
- **失败安静**：SDK 上报失败仅记 `warning` 日志，**不打断训练主流程**
- **脏数据容错**：service 解析 `metrics` / `params` / `artifacts` JSON 时，老格式 / 非法 JSON 都不抛
- **自动 status**：`with` 块异常时自动 `finish('failed')`，避免 run 永远停在 `running`

## 不在范围 / 后续

- **前端可视化页**（折线图 / 并排对比 UI）尚未做，目前查询走 HTTP API；下个 Phase 的工作
- **写入侧 SDK 写到** Notebook 里也能用（直接 `pip install requests` 后 import 即可）
- **多语言 SDK**（Java / Go）：暂未提供；推理服务可直接打 REST
