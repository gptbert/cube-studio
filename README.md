# Cube Studio

[English](README_EN.md) | 简体中文

云原生 **MLOps 控制面**——把模型从开发到上线的全生命周期编排在 Kubernetes 上。

```
开发 → 训练 → 实验追踪 → 模型注册 → 推理服务 → GPU/Pod 监控
```

## 📖 文档

详细使用文档在 [`docs/`](docs/README.md) 目录：

| 主题 | 适合谁 |
|---|---|
| [快速上手](docs/getting-started.md) | 第一次接触 Cube Studio 的开发者 |
| [部署](docs/deployment.md) | 平台运维 / SRE |
| [Notebook 开发环境](docs/notebook.md) | 算法工程师 |
| [Pipeline 与训练任务](docs/pipeline.md) | 算法工程师 |
| [实验追踪](docs/experiment-tracking.md) | 算法工程师 |
| [推理服务](docs/inference.md) | 算法工程师 / 模型上线 owner |
| [架构与边界](docs/architecture.md) | 平台开发者 / 企业架构师 |

## 🔧 部署

Cube Studio 已收敛为纯 MLOps 控制面，依赖企业基础设施统一维护：

- **数据库** MySQL / PostgreSQL
- **缓存** Redis
- **监控** Prometheus + Grafana
- **镜像仓库** Harbor
- **K8s 控制面** Rancher 或自建
- **LLM 网关** LiteLLM
- **数据 ETL / 数仓** DolphinScheduler + Hadoop YARN + Spark
- **大文件存储** HDFS / 对象存储

仓库内不再附带这些组件的部署清单，仅依赖它们的连接信息。

```bash
# 1. 准备外部服务连接（编辑后 apply）
cp install/kubernetes/external-services.example.yaml /tmp/external.yaml
kubectl apply -f /tmp/external.yaml

# 2. 一键部署 cube-studio 控制面
cd install/kubernetes
bash start.sh <INGRESS_IP>
```

详细见 [`docs/deployment.md`](docs/deployment.md)。

## 🧩 现有能力

| 模块 | 说明 |
|---|---|
| 项目空间 / RBAC | 多租户 + 项目组配额 |
| Notebook | JupyterLab / VS Code 在线 IDE，支持 SSH Remote |
| 镜像管理 | 在线 Dockerfile 构建 + 推 Harbor |
| Pipeline | 拖拽式 DAG 编排，Argo + Volcano 底层 |
| Job 模板 | pytorch / tf / volcano / ray / xgb / yolov8 / model-register / deploy-service / 等 |
| 超参搜索 | NNI |
| 实验追踪 | `Training_Model` 表 + `cube_experiment` SDK（Phase 4.1/4.2） |
| 模型注册 | 多版本管理 + 一键发布 |
| 推理服务 | TFServing / TorchServe / Triton / vLLM / 自定义；多版本灰度；HPA |
| 模型 sidecar 服务 | SD-WebUI / xinference / TensorBoard server 等 ML 配套 |
| GPU / Pod 监控 | 复用企业 Prometheus + Grafana |
| 数据集 | 仅做"训练数据引用"（PVC 路径登记），不做数据搬运 |
| 模型市场 | AIHub 视觉 / 语音 / NLP / 多模态 / 大模型展示（只读） |

## 🚫 不在范围

以下能力**不**由 Cube Studio 提供：

- 数据 ETL / 数仓任务 → 用 DolphinScheduler
- SQL 查询 / 数据探索 → 用数仓自带 SQL 控制台
- LLM OpenAI 兼容入口 → 推理服务镜像 `OPENAI_API_BASE` 指向企业 LiteLLM
- 私有知识库 / RAG → 独立 AI 应用，不内嵌 MLOps 平台
- K8s 集群部署 / 升级 → Rancher 控制面承担
- Harbor / Prometheus / Grafana / ES / Kafka 部署 → 企业 OPS 维护

详细分工见 [`docs/architecture.md`](docs/architecture.md)。

## 🤝 开源共建

学习、部署、体验、开源建设、商业合作 欢迎来撩。或添加微信 `luanpeng1234`，备注 `<开源建设>`。

<img border="0" width="20%" src="https://user-images.githubusercontent.com/20157705/219829986-66384e34-7ae9-4511-af67-771c9bbe91ce.jpg" />

## 公司

![tencent music](https://github.com/user-attachments/assets/83064556-d9c2-4adb-a796-018883ed427b)

---

> 历史完整功能清单（含已下线模块）见 [`README_CN.md`](README_CN.md)。
> 架构演进 review 见 [`ARCHITECTURE_REVIEW_CN.md`](ARCHITECTURE_REVIEW_CN.md)。
