# 推理服务

把模型部署成 K8s 上的常驻服务，对外暴露 HTTP / gRPC，支持多版本灰度、滚动升级、HPA。

## 创建推理服务

`推理服务 → 模型服务 → 新建`：

| 字段 | 说明 |
|---|---|
| 项目组 | 决定命名空间、RBAC、域名前缀 |
| name | DNS-safe 名称（小写字母 / 数字 / `-`），全局唯一 |
| label | 中文名 |
| service_type | `serving` / `tfserving` / `torchserve` / `triton-server` / `onnxruntime` / `ml-server` |
| 镜像 | 推理服务镜像（按 `service_type` 选预置或自定义） |
| 模型路径 | PVC 路径或 HTTP/HTTPS 下载地址 |
| 资源 | CPU / 内存 / GPU |
| 副本数 | 并发能力 |
| 端口 | HTTP / gRPC 端口，逗号分隔 |
| 模型版本 | 多版本灰度的版本标签 |

## 内置 service_type

| 类型 | 适用 | 镜像示例 |
|---|---|---|
| `tfserving` | TF saved_model | `tfserving:2.3.4` |
| `torchserve` | TorchServe `.mar` 文件 | `torchserve:0.7.1-cpu` |
| `triton-server` | TensorRT / ONNX / PyTorch / TF 多框架 | `tritonserver:22.07-py3` |
| `serving` / `ml-server` | 自定义 / sklearn / xgboost | 用户自定义镜像 |
| `onnxruntime` | ONNX | `onnxruntime:latest` |

模型路径格式参考表单上的 placeholder：
- `serving`：自定义镜像，模型地址随意
- `tfserving`：仅支持添加了服务签名的 saved_model 目录，例如 `/mnt/admin/.../saved_model/`
- `torchserve`：torch-model-archiver 编译后的 mar 文件
- `triton-server`：`框架:地址`，例如 `onnx:/mnt/.../model.onnx`、`pytorch:/mnt/.../model.pt`

## 多版本灰度

同一 `model_name` 下可同时存在多个 `model_version`，通过 Istio VirtualService
按权重分流：

1. 部署 v1：100% 流量 → v1
2. 部署 v2：在 v1 详情页设置"灰度发布"权重，例如 v1=80, v2=20
3. 观察 v2 监控指标稳定后逐步提高权重
4. v2=100 后下线 v1

## 弹性伸缩

支持 HPA：
- CPU / 内存 / GPU 阈值
- 自定义指标（如 QPS、p99 延迟）通过 Prometheus + prometheus-adapter
  > 注：prometheus-adapter 由企业基础设施统一维护
- 定时伸缩（白天高峰扩容，夜间缩容）

## 与 LiteLLM 网关协作

LLM 类推理服务统一走企业 LiteLLM 网关，避免每个服务各自配 OpenAI key：

```yaml
env:
  OPENAI_API_BASE: http://litellm.company.local/v1
  OPENAI_API_KEY:  $(LITELLM_API_KEY)   # 来自 cube-litellm-secret
```

LiteLLM 由 OPS 维护，cube-studio 仅消费。

## 自定义镜像

写一个起 HTTP 的镜像（FastAPI / Flask / Triton custom backend），按规范暴露端口与
健康检查路径，提交到企业 Harbor，然后在 `推理服务` 选 `serving` + 自己镜像即可。

健康检查约定：
- `GET /health` 或表单里设置的 `health` 路径，返回 200 视为就绪

## 模型从训练自动发布

`模型管理 → 训练模型` 找到 run 行 → 点 **发布** → 自动跳到推理服务创建表单，
填好 GPU 资源 / 副本后保存。

或在 Pipeline 里使用 `deploy-service` 模板自动化。

## 监控

每个推理服务都自动接入：
- CPU / 内存 / GPU 利用率
- 请求量 / 错误率 / p99 延迟（通过 Istio sidecar 指标）
- Pod 状态 / 副本数

数据来自企业 Prometheus，Grafana 可视化由企业监控平台承担。

## sidecar 自定义服务

`模型 sidecar 服务` 菜单（原"内部服务"）用来部署 ML / LLM 推理配套 sidecar：

- vLLM / Triton 自定义版本
- SD-WebUI（图像生成 web）
- xinference（多 LLM 推理框架）
- TensorBoard server

不用于部署数据库管理工具或日志栈，那些归企业 OPS。
