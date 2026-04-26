# Pipeline 与训练任务

Cube Studio 把训练流程拆为：

- **Job 模板**：可复用的容器化任务（python / pytorch / tf / volcano / ray 等）
- **Pipeline**：DAG 形式串起多个 Job
- **Workflow 实例**：Pipeline 的一次具体运行

底层走 [Argo Workflows](https://argoproj.github.io/argo-workflows/) + [Volcano](https://volcano.sh/)。

## 内置 Job 模板

仓库自带的模板在 [`job-template/job/`](../job-template/job/)：

| 模板 | 类型 | 用途 |
|---|---|---|
| `pytorch` | 分布式深度学习 | PyTorchJob CRD（DDP / FSDP） |
| `tf` | 分布式深度学习 | TFJob CRD |
| `volcano` | 通用分布式 | volcano.sh `Job` CRD |
| `ray` | 分布式 | Ray cluster |
| `ray_sklearn` | 分布式 ML | Ray + sklearn |
| `xgb` | 单机 ML | XGBoost |
| `yolov8` | 单机 ML | Ultralytics YOLOv8 训练 |
| `model_register` | 工具 | 模型注册到平台 |
| `model_download` | 工具 | 从外部拉模型到 PVC |
| `model_offline_predict` | 工具 | 批量离线推理 |
| `deploy-service` | 工具 | 把模型部署成 InferenceService |
| `dataset` | 工具 | 数据集元数据登记（仅"引用"，非搬运） |
| `video-audio` | 多媒体 | 视频提取图片 / 抽音 |
| `pkgs` | 共享库 | 提供 `cube_experiment.py`、`utils.py` 等 SDK，供其他 job 镜像复用 |
| `demo` / `test` | 示例 | 入门参考 |

模板镜像由 `install/kubernetes/all_image.py` 维护、推送到企业 Harbor。

> 注：旧版仓库内的 `datax` / `hadoop` / `data-process` / `feature-process` 等 ETL 模板已删除（PR #16），数据 ETL 归 DolphinScheduler。

## 编排一个 Pipeline

`训练 → 任务流编排`：

1. **新建 pipeline**：填项目组、名称、调度（cron 或手动）、最大并发
2. **加任务节点**：从左侧拖 Job 模板到画布，每个节点配置参数
3. **拉边设置依赖**
4. **保存 + 运行**

例：经典 ML 流（仓库内置示例）

```
data-process       (自定义镜像，做特征处理)
        ↓
   model-train     (decision-tree 模板)
        ↓
   model-val       (decision-tree 模板，评估)
        ↓
model-register     (model_register 模板)
        ↓
deploy-service     (deploy-service 模板)
```

## 调度与监控

Pipeline 支持：

- **定时调度** —— cron 表达式
- **补录** —— 历史时间窗回填
- **依赖触发** —— 上游 Pipeline 完成后触发
- **并发限制** —— 同一 Pipeline 同一时刻最多 N 个实例
- **超时 / 重试** —— 单 task 级别
- **任务流优先级** —— 全局 + Pipeline 级
- **暂停 / 恢复** —— 在 `任务流实例` 详情页操作

## 单任务调试

每个 task 节点都可以单独"调试运行"，不走 DAG，用于：
- 镜像 / 参数 / 启动命令试错
- GPU 资源是否够、PV 是否挂得上
- 训练代码是否会 crash

## 自定义 Job 模板

如果内置模板不够用：

1. 写 Dockerfile，构建镜像并推到企业 Harbor
2. `训练 → 模板分类 → 新建模板`：填镜像名、参数 schema、启动命令、资源默认值
3. 保存后所有项目组都可以在 Pipeline 里拖这个新模板

模板参数 schema 用 JSON Schema 表达，会渲染成前端表单。可以参考 `myapp/init/init-job-template.json` 中的现成定义。

## 与训练 SDK 配合

训练任务在容器内调用 [`cube_experiment` SDK](experiment-tracking.md) 上报实验上下文：

```python
from cube_experiment import Run

with Run.start(name='resnet50', version='v2026.04.26.1',
               experiment_id='exp-cv-baseline') as run:
    run.log_param('lr', 0.001)
    run.log_metric('val_acc', 0.93)
    run.log_artifact('/mnt/admin/models/resnet50.pt')
```

需要训练镜像里有 `requests`，并把 `cube_experiment.py` 复制到镜像 `PYTHONPATH`（`pkgs/` 模板已经做了）。
