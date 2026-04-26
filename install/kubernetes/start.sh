#!/bin/bash
set -euo pipefail

if [ $# -eq 0 ]; then
  echo "错误：请提供 内网ip地址 作为参数"
  echo "用法: bash start.sh <INGRESS_IP>"
  exit 1
fi

INGRESS_IP="$1"

bash init_node.sh
mkdir -p ~/.kube && rm -rf ~/.kube/config && cp config ~/.kube/config
mkdir -p kubeconfig && echo "" > kubeconfig/dev-kubeconfig

ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
  wget -O kubectl https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl-amd64-1.28
  chmod +x kubectl && cp kubectl /usr/bin/ && mv kubectl /usr/local/bin/
elif [ "$ARCH" = "aarch64" ]; then
  wget -O kubectl https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl-arm64-1.28
  chmod +x kubectl && cp kubectl /usr/bin/ && mv kubectl /usr/local/bin/
fi

version=$(kubectl version --short | awk '/Server Version:/ {print $3}')
echo "kubernetes version" "$version"

node=$(kubectl get node -o wide | grep "$INGRESS_IP" | awk '{print $1}' | head -n 1)
if [ -z "$node" ]; then
  echo "错误：未找到包含IP $INGRESS_IP 的节点"
  exit 1
fi

# 仅保留 MLOps 控制面与任务编排能力（基础设施统一外部维护）
kubectl label node "$node" train=true cpu=true notebook=true service=true org=public istio=true kubeflow=true kubeflow-dashboard=true --overwrite

# Cube Studio 控制面安装入口
# 前置依赖：MySQL/PG、Redis、Prometheus/Grafana、Harbor、HDFS 等基础设施
# 已由企业统一维护，不再随仓库内置部署。请先用
#   external-services.example.yaml
# 准备 Secret/ConfigMap 注入连接信息，再执行本脚本。

# 创建命名空间和基础 RBAC
sh create_ns_secret.sh
kubectl apply -f sa-rbac.yaml

# k8s dashboard
kubectl apply -f dashboard/v2.6.1-cluster.yaml
kubectl apply -f dashboard/v2.6.1-user.yaml

# GPU 能力
kubectl apply -f gpu/nvidia-device-plugin.yml
kubectl apply -f gpu/dcgm-exporter.yaml

# Volcano
kubectl delete -f volcano/volcano-development.yaml || true
kubectl apply -f volcano/volcano-development.yaml
kubectl wait crd/jobs.batch.volcano.sh --for condition=established --timeout=60s

# Istio
kubectl delete -f istio/install-1.15.0.yaml || true
kubectl apply -f istio/install-crd.yaml
kubectl wait crd/envoyfilters.networking.istio.io --for condition=established --timeout=60s
kubectl apply -f istio/install-1.15.0.yaml
kubectl wait crd/virtualservices.networking.istio.io --for condition=established --timeout=60s
kubectl wait crd/gateways.networking.istio.io --for condition=established --timeout=60s
kubectl apply -f gateway.yaml
kubectl apply -f virtual.yaml

# Argo / Pipeline（可按需保留 MinIO）
kubectl apply -f argo/minio-pv-pvc-hostpath.yaml
kubectl apply -f argo/pipeline-runner-rolebinding.yaml
kubectl apply -f argo/install-3.4.3-all.yaml

# Train operator
kubectl apply -f kubeflow/sa-rbac.yaml
kubectl apply -k kubeflow/train-operator/manifests/overlays/standalone

# 管理平台（依赖外部 MySQL/PG、Redis、可选 ES/Kafka/Prometheus）
kubectl delete configmap kubernetes-config -n infra || true
kubectl create configmap kubernetes-config --from-file=kubeconfig -n infra
kubectl delete configmap kubernetes-config -n pipeline || true
kubectl create configmap kubernetes-config --from-file=kubeconfig -n pipeline
kubectl delete configmap kubernetes-config -n automl || true
kubectl create configmap kubernetes-config --from-file=kubeconfig -n automl

kubectl create -f pv-pvc-infra.yaml
kubectl create -f pv-pvc-jupyter.yaml
kubectl create -f pv-pvc-automl.yaml
kubectl create -f pv-pvc-pipeline.yaml
kubectl create -f pv-pvc-service.yaml

# 替换配置文件config.py中的内网ip地址
sed -i "s/SERVICE_EXTERNAL_IP=\\[\\]/SERVICE_EXTERNAL_IP=\[\"$INGRESS_IP\"\]/g" cube/overlays/config/config.py

kubectl delete -k cube/overlays || true
kubectl apply -k cube/overlays

# 配置入口
kubectl patch svc istio-ingressgateway -n istio-system -p '{"spec":{"externalIPs":["'"$INGRESS_IP"'"]}}'
echo "Cube Studio 控制面部署完成，打开网址：http://$INGRESS_IP"
echo "请确认已通过 Secret/ConfigMap 注入外部 MySQL/PostgreSQL、Redis 连接信息。"
