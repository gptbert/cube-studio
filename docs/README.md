# Cube Studio 用户文档

Cube Studio 是一个**纯 MLOps 控制面**——把模型从开发到上线的全生命周期编排在 K8s 上。
基础设施（数据库 / 缓存 / 监控 / 镜像仓库 / 数据平台 / LLM 网关）由企业统一维护。

## 文档目录

| 主题 | 适合谁 |
|---|---|
| [快速上手](getting-started.md) | 第一次接触 Cube Studio 的开发者 |
| [部署](deployment.md) | 平台运维 / SRE |
| [Notebook 开发环境](notebook.md) | 算法工程师 |
| [Pipeline 与训练任务](pipeline.md) | 算法工程师 / 平台开发者 |
| [实验追踪](experiment-tracking.md) | 算法工程师 |
| [推理服务](inference.md) | 算法工程师 / 模型上线 owner |
| [架构与边界](architecture.md) | 平台开发者 / 企业架构师 |

## 30 秒概览

```
┌──────────────────────────────────────────────────────────┐
│                    Cube Studio                            │
│                  MLOps Control Plane                      │
├──────────────────────────────────────────────────────────┤
│  开发    Notebook (JupyterLab / VSCode) + 镜像构建         │
│  训练    Pipeline + Job 模板 + NNI 超参 + 实验追踪          │
│  模型    模型注册 + 版本管理                                │
│  推理    多版本灰度 + sidecar 服务                          │
│  资源    K8s 调度 + GPU 监控 + 项目组配额                   │
└──────────────────────────────────────────────────────────┘
                         ▲
                         │ 依赖（外部维护）
                         │
  MySQL / PostgreSQL  Redis  Prometheus / Grafana  Harbor
  HDFS  ES  Kafka  Rancher (K8s)  LiteLLM  DolphinScheduler
```

## 不在范围

以下能力**不**由 Cube Studio 提供，请使用对应的企业基础设施：

- 数据 ETL / 数仓任务 → DolphinScheduler + Hadoop YARN + Spark
- SQL 查询 / 数据探索 → 数仓自带 SQL 控制台或 BI 工具
- LLM 推理 OpenAI 兼容入口 → 企业 LiteLLM 网关
- 私有知识库 / RAG → 独立 AI 应用（不强制内嵌到 MLOps 平台）

详见 [架构与边界](architecture.md)。
