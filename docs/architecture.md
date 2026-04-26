# 架构与边界

> 详细的架构 review 见仓库根目录 [`ARCHITECTURE_REVIEW_CN.md`](../ARCHITECTURE_REVIEW_CN.md)。
> 本文聚焦"边界"——cube-studio **管什么**、**不管什么**。

## 核心定位

```
Cube Studio = MLOps 控制面
            = 模型生命周期管理 + K8s 调度
            ≠ 数据平台
            ≠ K8s 集群引导工具
            ≠ LLM 网关
            ≠ 监控 / 日志平台
```

## 系统全景

```
                  ┌──────────────────────────┐
                  │     DolphinScheduler     │  ← 数据 ETL 调度（外部）
                  │ Hadoop YARN + Spark 3.5  │
                  └─────────────┬────────────┘
                                │  写
                                ▼
                  ┌──────────────────────────┐
                  │    HDFS / 对象存储        │  ← 训练数据 / 模型产物
                  └─────────────┬────────────┘
                                │  路径引用
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                       Cube Studio (本仓库)                           │
│                                                                     │
│  开发      Notebook (JupyterLab/VSCode) + 镜像构建                   │
│  训练      Pipeline + Job 模板 + NNI 超参                            │
│  追踪      Training_Model 表 (params/metrics/artifacts/status)       │
│            cube_experiment SDK (容器内上报)                          │
│  模型      模型注册 + 多版本                                         │
│  推理      Multi-version + Istio 灰度 + HPA                         │
│  资源      Argo / KubeFlow / Volcano / GPU device plugin             │
└──────────┬──────────────────────────────────────────┬──────────────┘
           │                                          │
           ▼                                          ▼
   ┌──────────────┐                       ┌─────────────────────┐
   │ K8s Cluster  │ ← 由企业 Rancher 管控   │  LiteLLM 网关        │
   │  CPU/GPU/NPU │                       │  (LLM OpenAI 兼容)   │
   └──────────────┘                       └─────────────────────┘
           ▲                                          ▲
           │ 推 / 拉镜像                                │ 推理服务调
           │
   ┌──────────────┐
   │   Harbor     │ ← 企业镜像仓库
   └──────────────┘

依赖（全部由企业 DBA / OPS 统一维护）：
  MySQL / PostgreSQL    平台元数据库
  Redis                 缓存 + Celery broker
  Prometheus + Grafana  监控
  ES / Kafka            可选：日志检索 / 事件流
```

## 职责边界

| 责任 | 由谁承担 | 备注 |
|---|---|---|
| **模型开发** | Cube Studio | Notebook + 镜像构建 |
| **模型训练** | Cube Studio | Pipeline + Job 模板 |
| **实验追踪** | Cube Studio | Training_Model + cube_experiment SDK |
| **模型注册 / 版本** | Cube Studio | model 表 |
| **推理服务部署** | Cube Studio | InferenceService + Istio |
| **GPU / Pod 调度** | Cube Studio + K8s | 通过 K8s API |
| 数据 ETL / 数仓任务 | DolphinScheduler | cube-studio 内部已无相关代码 |
| SQL 查询 / 数据探索 | 数仓自带 SQL 控制台 / BI | 已删 SqlLab（PR #10） |
| LLM OpenAI 兼容入口 | LiteLLM 网关 | 推理服务镜像走 `OPENAI_API_BASE` |
| K8s 集群部署 / 升级 | Rancher | 已删 install/kubernetes/rancher/（PR #18） |
| 镜像仓库部署 | Harbor | 已删 install/kubernetes/harbor/（PR #14） |
| 数据库 / Redis / ES / Kafka | 企业 DBA / OPS | 已删对应部署目录 |
| 监控指标采集 | Prometheus + Grafana | 已删 install/kubernetes/prometheus/ |
| 日志采集 / 检索 | 企业 ELK / 日志平台 | 已删 install/kubernetes/efk/ + ilogtail/ |

## 后端模块（精简后 21 个 view）

```
myapp/views/
├── 项目 / 用户
│   ├── view_team               项目空间 / 项目组
│   └── view_user_role          用户 / 角色 / 权限
├── 资源
│   ├── view_total_resource     整体资源 + GPU 监控
│   ├── view_k8s                K8s 资源浏览
│   └── view_log                操作审计日志
├── 开发
│   ├── view_notebook           在线 IDE
│   ├── view_images             镜像管理
│   └── view_docker             在线镜像构建
├── 训练
│   ├── view_job_template       Job 模板
│   ├── view_task               任务定义
│   ├── view_pipeline           Pipeline 编排
│   ├── view_workflow           Workflow 实例
│   ├── view_runhistory         调度记录
│   └── view_nni                超参搜索
├── 模型 + 推理
│   ├── view_train_model        模型注册 + 实验追踪
│   ├── view_serving            模型 sidecar 服务
│   └── view_inferenceserving   推理服务（多版本 / 灰度）
├── 数据
│   └── view_dataset            数据集元数据登记（仅引用，不搬运）
└── 应用
    └── view_aihub              模型市场展示层（只读）
```

## 服务层（按 codex 引入的模式）

```
myapp/services/
├── pipeline_service.py            Pipeline / Argo Workflow 编排逻辑
├── training_model_service.py      实验追踪：纯函数 + DB 边界 + 写入
└── (后续按需扩展)
```

服务层规则：
- **纯函数**（解析 / 计算 / 聚合）+ **DB 边界**（query / upsert）分离
- DB 边界通过 `dbsession=` 注入，便于单测

## 删了什么（按时间）

| PR | 内容 | 净删 |
|---|---|---|
| #3 | Phase 1+2a+2b：MLOPS_ONLY 隐藏开关 + 数据平台 view/model + Hive + Python 3.12 | ~12k 行 |
| #4 | Phase 2c+3：ETL job 模板 + 前端 SqlLab + visionPlus | ~50k 行 |
| #14 | install/kubernetes/{mysql,redis,prometheus,harbor,efk,kafka,ilogtail} | ~66k 行 |
| #16 | model_service_pipeline 孤儿 + example/{datax,hadoop,data-process,...} 残余 | ~10k 行 |
| #17 | view_serving 改名 + view_dataset 仅做引用 + view_aihub 现状确认 | ~60 行 |
| #18 | install/kubernetes/rancher/ + LiteLLM 外部清单 | ~2.9k 行 |

合计净删 ~140k 行；同时新增 Phase 4.1/4.2 实验追踪能力（+1.5k 行 / 48 个单测）。

## 未来方向

- **前端实验追踪页**（折线图 / 并排对比 UI）
- **模型评估 / 审批工作流**
- **拆臃肿 view**：`baseApi.py` 2313 行、`view_inferenceserving.py` 1357 行
- **view 层补单测**：目前只有 `services/` 与 SDK 有覆盖
