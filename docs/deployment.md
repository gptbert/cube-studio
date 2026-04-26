# 部署

> 仓库内只保留 **MLOps 控制面 + 必要的 K8s 运行时**（argo / kubeflow / volcano / istio / gpu / minio / cube）。
> 数据库 / 缓存 / 监控 / 镜像仓库 / 数据平台 / LLM 网关都依赖企业基础设施。

## 1. 前置检查

| 依赖 | 用途 | 在 cube-studio 中如何配置 |
|---|---|---|
| Kubernetes ≥ 1.24 | 运行时 | 由 `~/.kube/config` 读取 |
| MySQL 或 PostgreSQL | 元数据库 | env `MYSQL_SERVICE` / `DB_*` |
| Redis | 缓存 + Celery broker | env `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` |
| Harbor | 镜像仓库 | hubsecret + `REPOSITORY_ORG` |
| Prometheus + Grafana | 监控 | env `PROMETHEUS_URL` / `GRAFANA_URL` |
| HDFS（可选） | 模型 / 数据集大文件 | env `HDFS_NAMESERVICE` |
| ES / Kafka（可选） | 日志检索 / 事件流 | env `ES_HOSTS` / `KAFKA_BOOTSTRAP_SERVERS` |
| LiteLLM（可选） | LLM 推理 OpenAI 兼容入口 | env `OPENAI_API_BASE` / `LITELLM_API_KEY` |
| DolphinScheduler（可选） | 数据 ETL 调度 | 通过 HDFS 路径协作，不需要直连 |
| Rancher | K8s 控制面 | 直接用其管的 K8s 集群即可 |

## 2. 准备外部服务连接

把 [`install/kubernetes/external-services.example.yaml`](../install/kubernetes/external-services.example.yaml) 复制一份，
填好真实的 host / port / 账号密码，应用到 `infra` 命名空间：

```bash
cp install/kubernetes/external-services.example.yaml /tmp/external-services.yaml
# 编辑 /tmp/external-services.yaml，把 REPLACE_ME 换成真实值
kubectl apply -f /tmp/external-services.yaml
```

会创建：
- Secret `cube-db-secret`        ——  DB 连接
- Secret `cube-redis-secret`     ——  Redis 连接
- Secret `cube-litellm-secret`   ——  LiteLLM API Key
- ConfigMap `cube-external-services` —— ES / Kafka / Prometheus / Grafana / HDFS / Harbor / LiteLLM 等只读地址

## 3. 一键部署 cube-studio 控制面

```bash
cd install/kubernetes
bash start.sh <INGRESS_IP>
```

`start.sh` 会按顺序：

1. 创建命名空间 `infra` / `pipeline` / `automl` / `service` 与 RBAC
2. 装 K8s dashboard + GPU device plugin + DCGM exporter
3. 装 Volcano（批量调度）
4. 装 Istio CRD + ingressgateway + 网关 / VirtualService
5. 装 Argo Workflows + KubeFlow Training Operator
6. 创建 PV / PVC（infra / jupyter / automl / pipeline / service）
7. 用 kustomize 部署 cube-studio 自身（`install/kubernetes/cube/overlays`）

部署完成后浏览器打开 `http://<INGRESS_IP>/`。

## 4. 离线 / 内网

完整流程见 [`install/kubernetes/offline.md`](../install/kubernetes/offline.md)：
- 镜像同步到企业 Harbor（`push_harbor.sh` / `pull_harbor.sh` 由 `all_image.py` 生成）
- DNS / 代理 / pip / apt 源的内网映射

## 5. 升级与回退

cube-studio 自身镜像更新：

```bash
# 修改镜像 tag
vi install/kubernetes/cube/overlays/kustomization.yml
# 滚动应用
kubectl apply -k install/kubernetes/cube/overlays
```

回退就 `kubectl rollout undo deploy/<deployment-name> -n infra`。

DB 迁移：容器启动时 `entrypoint.sh` 会自动执行 `myapp db upgrade`，无需手动。

## 6. 常见问题

**Q: 之前看到 `start-lite.sh`，现在哪去了？**
A: 已重命名为 `start.sh`（PR #14）。Cube Studio 现在只有这一个部署入口——基础设施由企业外部维护。

**Q: 为什么要把 mysql / redis / harbor / prometheus 删掉？**
A: 企业一般已经有 DBA / SRE 维护这些组件；仓库内置部署清单会与现网维护冲突。详见 [架构与边界](architecture.md)。
