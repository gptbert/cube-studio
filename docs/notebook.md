# Notebook 开发环境

在线 IDE，支持 JupyterLab / VS Code / Matlab / RStudio 等多种类型，
跑在用户私有 Pod 中，文件持久化到 PVC。

## 创建一个 Notebook

`在线开发 → notebook → 新建`：

| 字段 | 说明 |
|---|---|
| 项目组 | 决定调度命名空间、RBAC、PVC 子目录 |
| 名称 | 小写字母 / 数字 / `-`，全局唯一 |
| ide_type | `jupyter` / `vscode` / `matlab` / `rstudio` 等 |
| 镜像 | 选预置的 notebook 镜像（见下表）或自定义 |
| 资源 | CPU / 内存 / GPU |
| 环境变量 | `KEY=value`，每行一个 |
| 挂载 | `pvc-name(pvc):/容器路径,host-path(hostpath):/容器路径`<br>项目组 PVC 自动挂在 `/mnt/<username>/`，无需重复声明 |

启动后状态变绿，点击名称在浏览器内打开。

## 内置 Notebook 镜像

| 镜像 | 适合场景 |
|---|---|
| `notebook:vscode-ubuntu-cpu-base` | 纯 CPU 通用开发 |
| `notebook:vscode-ubuntu-gpu-base` | GPU 通用开发 |
| `notebook:jupyter-ubuntu22.04` | Python 通用 |
| `notebook:jupyter-ubuntu22.04-cuda11.8.0-cudnn8` | 深度学习（CUDA 11.8） |
| `notebook:jupyter-ubuntu-machinelearning` | 传统 ML（sklearn / xgboost / lightgbm） |
| `notebook:jupyter-ubuntu-deeplearning` | TF / PyTorch 全家桶 |
| `notebook:jupyter-ubuntu-bigdata` | hdfs / hive / spark client（如仍连接外部 Hadoop） |
| `notebook:jupyter-ubuntu-cpu-1.0.0` | 轻量 CPU 老镜像 |

镜像列表维护在 `install/kubernetes/all_image.py` 与 `install/docker/config.py:NOTEBOOK_IMAGES`。

## 持久化 / 数据流转

- `/mnt/<username>/` —— 用户个人空间，跨 Notebook / Pipeline / 推理任务共享
- `/mnt/<username>/pipeline/` —— Pipeline 任务的工作目录（Notebook 里写代码，Pipeline 里跑同一份）
- 大文件 / 数据集建议放企业 HDFS，Notebook 里通过 `hdfs dfs -get` 拉取

## 自定义镜像

`在线开发 → 镜像构建` 可以在浏览器里 docker build：

1. 选基础镜像（推荐从 `notebook:*-base` 起步）
2. 写 Dockerfile（在线编辑器）
3. 提交后会起一个 commit pod，构建完镜像 push 到企业 Harbor
4. 完成后镜像可在 Notebook / Pipeline / 推理服务里直接选

## SSH Remote 开发

VS Code 模式可以暴露 SSH 端口，本地 VS Code 通过 `Remote - SSH` 连接 Notebook Pod：

1. Notebook 启动后查看详情，复制 ssh 连接命令
2. 本地 `~/.ssh/config` 加入对应 host
3. 本地 VS Code: `Remote-SSH: Connect to Host`

## 常见操作

- **保存当前环境为新镜像**：详情页 → "保存"，会触发 commit + push 到 Harbor
- **修改资源**：编辑后会重启 Pod，文件不丢
- **批量定时清理**：管理员可在 `定时任务` 中启用 notebook 自动停止策略
