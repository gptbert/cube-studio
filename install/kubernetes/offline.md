# Cube Studio 离线安装

> 前置：企业的 Harbor / K8s（Rancher 等控制面）/ MySQL / Redis / Prometheus / Grafana / HDFS /
> ES / Kafka / LiteLLM 网关 等基础设施已经独立运行并对接好。
> 本文档只覆盖 cube-studio 控制面镜像 / 模型 / 示例数据的内网同步与部署。

前置条件：内网机器已安装 docker、docker-compose、iptables。

# [部署视频](https://cube-studio.oss-cn-hangzhou.aliyuncs.com/video/%E5%86%85%E7%BD%91%E7%A6%BB%E7%BA%BF%E9%83%A8%E7%BD%B2.mp4)

# 完全无法联网的内网机器

## 安装依赖组件和数据

能连接外网的机器上执行下面的命令，把 `offline/` 目录拷贝到内网机器上：

```bash
mkdir offline
cd offline
# 下载 kubectl
# amd64 版本
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl
# arm64 版本
# wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl-arm64 && mv kubectl-arm64 kubectl

# 下载示例模型
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/inference/resnet50.onnx
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/inference/resnet50-torchscript.pt
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/inference/resnet50.mar
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/inference/tf-mnist.tar.gz
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/inference/decisionTree_model.pkl

# 训练 / 标注示例数据集
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/pipeline/coco.zip
wget https://docker-76009.sz.gfp.tencent-cloud.com/github/cube-studio/aihub/deeplearning/cv-tinynas-object-detection-damoyolo/dataset/coco2014.zip
```

`offline/` 目录拷贝到内网机器上后：

1. 安装 kubectl
   ```bash
   cd offline
   chmod +x kubectl && cp kubectl /usr/bin/ && cp kubectl /usr/local/bin/
   ```

2. 配置每台机器的 docker insecure-registries 指向企业 Harbor（如非 https）；
   确认在企业 Harbor 上创建了 `cube-studio` 项目用于存放镜像。

3. 把示例数据放到个人目录：
   ```bash
   cp -r offline /data/k8s/kubeflow/pipeline/workspace/admin/
   ```

## 同步 cube-studio 镜像到企业 Harbor

修改 `install/kubernetes/all_image.py` 中的内网仓库地址 `harbor_repo`，运行导出 / 推送 / 拉取脚本：

- 联网机器：`bash push_harbor.sh` 推到企业内网 Harbor，
  或 `bash image_save.sh` 压成 tar 文件后再带入内网。
- 内网机器（每台都要）：`bash pull_harbor.sh` 从企业 Harbor 拉镜像，
  或 `bash image_load.sh` 从压缩文件导入。

## 内网部署 cube-studio

1. 修改 `init_node.sh`，把 `pull_images.sh` 替换为 `pull_harbor.sh`，每台机器都要执行
2. 注释掉 `start.sh` 里的 kubectl 在线下载段（前面已离线安装）
3. 修改 cube-studio 的镜像引用：
   ```bash
   vi install/kubernetes/cube/overlays/kustomization.yml
   # 修改最底部的 newName 和 newTag 指向企业 Harbor
   ```
4. 修改 cube-studio 配置：
   ```bash
   vi install/kubernetes/cube/overlays/config/config.py
   # 下面的值改为内网仓库地址：
   #   REPOSITORY_ORG  PUSH_REPOSITORY_ORG  USER_IMAGE  NOTEBOOK_IMAGES
   #   DOCKER_IMAGES   NERDCTL_IMAGES       NNI_IMAGES  WAIT_POD_IMAGES
   #   INFERNENCE_IMAGES
   #
   # 其他需要改：
   #   SERVICE_EXTERNAL_IP        添加内网 ip
   #   DEFAULT_GPU_RESOURCE_NAME  改为默认的 K8s 资源名
   ```
5. 复制 K8s 的 config 文件，按 `bash start.sh <内网 IP>` 部署

## Web 界面的部分内网修正

1. Web 界面 hubsecret 改为企业 Harbor 的账号密码
2. 修改配置文件中的内网仓库信息和内外网 ip
3. 自带的目标识别 pipeline 中，第一个数据拉取任务启动命令改为
   `cp offline/coco.zip ./ && ...`
4. 自带的推理服务启动命令把 `wget https://xxxx/xx.zip` 改为
   `cp /mnt/admin/offline/xx.zip ./`

# 内网中有可以联网的机器

##  联网机器设置代理服务器

联网机器上设置 nginx 代理软件源，参考 `install/kubernetes/nginx-https/apt-yum-pip-source.conf`。

启动 nginx 代理（需要监听 80 和 443 端口）：
```bash
docker run --name proxy-repo -d --restart=always --network=host \
  -v $PWD/nginx-https/apt-yum-pip-source.conf:/etc/nginx/nginx.conf nginx
```

## 在内网机器上配置 host

```bash
<出口服务器的IP地址>    mirrors.aliyun.com
<出口服务器的IP地址>    ccr.ccs.tencentyun.com
<出口服务器的IP地址>    registry-1.docker.io
<出口服务器的IP地址>    auth.docker.io
<出口服务器的IP地址>    hub.docker.com
<出口服务器的IP地址>    www.modelscope.cn
<出口服务器的IP地址>    modelscope.oss-cn-beijing.aliyuncs.com
<出口服务器的IP地址>    archive.ubuntu.com
<出口服务器的IP地址>    security.ubuntu.com
<出口服务器的IP地址>    cloud.r-project.org
<出口服务器的IP地址>    deb.nodesource.com
<出口服务器的IP地址>    docker-76009.sz.gfp.tencent-cloud.com
```

添加新的 host 后要重启下 kubelet：`docker restart kubelet`。

如果代理机器没法占用 80/443，需要使用 iptables 转发：
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -d mirrors.aliyun.com \
  -j DNAT --to-destination <出口服务器的IP地址>:<出口服务器的端口>
```

## K8s 配置域名解析

在 `kube-system` 命名空间，修改 coredns 的 ConfigMap，添加需要访问的地址映射：

```yaml
{
    "Corefile": ".:53 {
        errors
        health { lameduck 5s }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
          pods insecure
          fallthrough in-addr.arpa ip6.arpa
        }
        # 自定义 host
        hosts {
            <出口服务器的IP地址>    mirrors.aliyun.com
            <出口服务器的IP地址>    ccr.ccs.tencentyun.com
            <出口服务器的IP地址>    registry-1.docker.io
            <出口服务器的IP地址>    auth.docker.io
            <出口服务器的IP地址>    hub.docker.com
            <出口服务器的IP地址>    www.modelscope.cn
            <出口服务器的IP地址>    modelscope.oss-cn-beijing.aliyuncs.com
            <出口服务器的IP地址>    archive.ubuntu.com
            <出口服务器的IP地址>    security.ubuntu.com
            <出口服务器的IP地址>    cloud.r-project.org
            <出口服务器的IP地址>    deb.nodesource.com
            <出口服务器的IP地址>    docker-76009.sz.gfp.tencent-cloud.com
            fallthrough
        }
        prometheus :9153
        forward . \"/etc/resolv.conf\"
        cache 30
        loop
        reload
        loadbalance
    }"
}
```

重启 coredns 的 pod。

## 容器里使用放开的域名

pip 配置 https 源：
```bash
pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple
```

apt 配置 https 源（修改 `/etc/apt/sources.list`，ubuntu 20.04）：
```
deb https://mirrors.aliyun.com/ubuntu/ focal main restricted universe multiverse
deb-src https://mirrors.aliyun.com/ubuntu/ focal main restricted universe multiverse
deb https://mirrors.aliyun.com/ubuntu/ focal-updates main restricted universe multiverse
deb-src https://mirrors.aliyun.com/ubuntu/ focal-updates main restricted universe multiverse
deb https://mirrors.aliyun.com/ubuntu/ focal-backports main restricted universe multiverse
deb-src https://mirrors.aliyun.com/ubuntu/ focal-backports main restricted universe multiverse
deb https://mirrors.aliyun.com/ubuntu/ focal-security main restricted universe multiverse
deb-src https://mirrors.aliyun.com/ubuntu/ focal-security main restricted universe multiverse
```

yum 配置 https 源（下载阿里的源）：
```bash
wget -O /etc/yum.repos.d/CentOS-Base.repo https://mirrors.aliyun.com/repo/Centos-8.repo
```
