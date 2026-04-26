# 快速上手

5 分钟跑通"开 Notebook → 跑 Pipeline → 部署推理服务"主链路。

## 前置

- 浏览器能访问 Cube Studio Web 入口（部署完成后由管理员给出 IP / 域名）
- 已有项目组（管理员在`项目空间 → 项目分组`里加入了你的账号）

## 1. 登录

打开 `http://<ingress-ip>/`，默认管理员账号 `admin / admin`（生产环境请立即改密码）。

普通用户走企业 SSO（OAUTH / LDAP / Remote User，由 `AUTH_TYPE` 控制）。

## 2. 在 Notebook 里写代码

`在线开发 → notebook` 中新建一个 notebook：

| 字段 | 推荐值 |
|---|---|
| 项目组 | 选你所在的组 |
| ide_type | `jupyter` 或 `vscode` |
| 镜像 | `notebook:jupyter-ubuntu22.04-cuda11.8.0-cudnn8`（CV/DL）/ `notebook:vscode-ubuntu-cpu-base`（CPU 开发） |
| 资源 | CPU 4 / 内存 8G / GPU 0~1 |

点击启动，待状态变绿后点击名称进入。所有文件保存到 `/mnt/<your-username>/`，跨容器持久。

更多：[Notebook 详解](notebook.md)。

## 3. 跑一个示例 Pipeline

`训练 → Pipeline 任务` 中找到内置示例 `ml`（决策树训练 + 部署）：

```
data-process  →  model-train  →  model-val  →  model-register  →  deploy-service
```

点击运行，几分钟后查看 `任务流实例` 看到所有节点变绿。

更多：[Pipeline 与训练任务](pipeline.md)。

## 4. 在训练代码里上报实验

在你的训练脚本中加入 SDK，可记录超参、指标、产物，便于之后在「实验追踪」对比 run：

```python
from cube_experiment import Run

with Run.start(name='resnet50',
               version='v2026.04.26.1',
               experiment_id='exp-cv-baseline',
               framework='pytorch') as run:
    run.log_param('lr', 0.001)
    run.log_param('batch_size', 32)
    for epoch, acc in train_loop():
        run.log_metric('val_acc', acc)
    run.log_artifact('/mnt/admin/models/resnet50.pt')
```

with 块退出会自动 `finish('success')`；异常时自动 `finish('failed')`。

更多：[实验追踪](experiment-tracking.md)。

## 5. 注册模型并部署成推理服务

Pipeline 跑完后到 `模型管理 → 训练模型`，找到刚生成的 model 行：

- 点 **下载** 校验产物
- 点 **发布** 自动跳到推理服务创建表单，填好 GPU 资源 / 副本数后保存

或者从 `推理服务` 直接新建。支持 vLLM / Triton / TFServing / TorchServe / 自定义镜像。

更多：[推理服务](inference.md)。

## 下一步

- [部署](deployment.md) —— 想自己装一套
- [架构与边界](architecture.md) —— 想理解 Cube Studio 跟 DolphinScheduler / LiteLLM 的分工
