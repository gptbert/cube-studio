import json
import os,re
# 所需要的所有镜像
# 注：MySQL / Redis / Prometheus / Grafana / Harbor / ES / Kafka 由企业基础设施
# 统一维护，对应 install/kubernetes/{mysql,redis,prometheus,harbor,efk,kafka,...}
# 内置部署目录已删除，本镜像清单也不再列出。
kubeflow = [
    "busybox:1.36.0",
    "kubeflow/training-operator:v1-8a066f9",  # 分布式训练
    'alpine:3.10',
]

kubernetes_dashboard = [
    'kubernetesui/dashboard:v2.6.1',  # k8s dashboard
    'ccr.ccs.tencentyun.com/cube-studio/k8s-dashboard:v2.6.1',
    'kubernetesui/metrics-scraper:v1.0.8',  # k8s dashboard 上的指标监控
]

new_gpu = [
    'nvidia/k8s-device-plugin:v0.11.0-ubuntu20.04',  # gpu k8s插件
    'nvidia/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04',  # gpu监控
]

istio = [
    "istio/proxyv2:1.15.0",  # ingressgateway
    "istio/pilot:1.15.0"  # 数据面
]
volcano = [
    'volcanosh/vc-controller-manager:v1.7.0',  # 控制器
    'volcanosh/vc-scheduler:v1.7.0',  # 调度器
    'volcanosh/vc-webhook-manager:v1.7.0'  # 拦截器
]

pipeline = [
    'minio/minio:RELEASE.2023-04-20T17-56-55Z',
    'ccr.ccs.tencentyun.com/cube-argoproj/argoexec:v3.4.3',
    'ccr.ccs.tencentyun.com/cube-argoproj/workflow-controller:v3.4.3',
    'ccr.ccs.tencentyun.com/cube-argoproj/argocli:v3.4.3'
]
cube_studio = [
    # 前后端
    'ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01',
    'ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.03.01',
    # notebook基础镜像
    'ccr.ccs.tencentyun.com/cube-studio/notebook:vscode-ubuntu-cpu-base',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:vscode-ubuntu-gpu-base',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu22.04',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu22.04-cuda11.8.0-cudnn8',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-cpu-1.0.0',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-bigdata',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-machinelearning',
    'ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-deeplearning',
    # 超参搜索的镜像
    'ccr.ccs.tencentyun.com/cube-studio/nni:20240501',
    # 注：mysql / pgadmin / redis-ui / mongo-express / neo4j / es 等
    # 数据库 UI sidecar 镜像已随 init-service.json 中对应模板移除。
    # 推理服务的镜像

    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.14.1-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.14.1',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.13.1-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.13.1',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.12.2-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.12.2',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.11.1-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.11.1',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.10.1-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.10.1',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.9.3-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.9.3',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.8.4-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.8.4',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.7.4-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.7.4',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.6.5-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.6.5',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.5.4-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.5.4',
    'ccr.ccs.tencentyun.com/cube-studio/tfserving:2.3.4',
    # 'ccr.ccs.tencentyun.com/cube-studio/tritonserver:21.12-py3',
    # 'ccr.ccs.tencentyun.com/cube-studio/tritonserver:21.09-py3',
    'ccr.ccs.tencentyun.com/cube-studio/tritonserver:22.07-py3',
    'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.7.1-cpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.9.0-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.9.0-cpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.8.2-gpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.8.2-cpu',
    # 'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.7.1-gpu',
    'ccr.ccs.tencentyun.com/cube-studio/torchserve:0.7.1-cpu'
    # 'ccr.ccs.tencentyun.com/cube-studio/onnxruntime:latest',
    # 'ccr.ccs.tencentyun.com/cube-studio/onnxruntime:latest-cuda',
]

user_image = [
    # 任务模板的镜像
    "ubuntu:20.04",
    'python:3.9',
    'docker:23.0.4',

    # 用户可能使用的基础镜像
    'ccr.ccs.tencentyun.com/cube-studio/ubuntu-gpu:cuda11.8.0-cudnn8-python3.9',

]

# 任务模板的镜像
all_job_templates = json.load(open('../../myapp/init/init-job-template.json',mode='r'))
job_template_images = [template['image_name'] for template in list(all_job_templates.values())]

## 示例需要的镜像
example_images=[]
for file in os.listdir('../../myapp/init/'):
    file = os.path.join('../../myapp/init',file)
    content = open(file).read()
    matchs = re.findall('"(ccr.ccs.tencentyun.com/cube-studio.*)"', content)
    for match in matchs:
        if match not in example_images:
            example_images.append(match.strip())

images = kubeflow + kubernetes_dashboard + new_gpu + istio + volcano + pipeline + cube_studio + user_image + job_template_images + example_images
images = list(set(images))
init_images = kubeflow + kubernetes_dashboard + new_gpu + istio + volcano + pipeline



# 通过私有仓库，将公有镜像下发到内网每台机器上，例如内网docker.oa.com的仓库
harbor_repo = 'xx.xx.xx.xx:xx/cube-studio/'
pull_file = open('pull_images.sh',mode='w')
push_harbor_file = open('push_harbor.sh',mode='w')
pull_harbor_file = open('pull_harbor.sh', mode='w')

pull_save_file = open('image_save.sh',mode='w')
load_image_file = open('image_load.sh',mode='w')

# push_harbor_file.write(f'准备登录: {harbor_repo}\n')
push_harbor_file.write('docker login '+harbor_repo[:harbor_repo.index('/')]+"\n")
pull_harbor_file.write('docker login '+harbor_repo[:harbor_repo.index('/')]+"\n")

for image in images:
    # print(image)
    # print(image)
    image = image.replace('<none>', '')
    new_image = harbor_repo + image.replace('ccr.ccs.tencentyun.com/cube-studio/', '').replace('/', '-')

    # 可联网机器上拉取公有镜像并推送到私有仓库
    # print('docker pull %s && docker tag %s %s && docker push %s &' % (image,image,image_name,image_name))
    push_harbor_file.write('docker pull %s && docker tag %s %s && docker push %s &\n' % (image,image,new_image,new_image))
    pull_save_file.write('docker pull %s && docker save %s | gzip > %s.tar.gz &\n' % (image, image, image.replace('/','-').replace(':','-')))

    # # # 内网机器上拉取私有仓库镜像
    # print("docker pull %s && docker tag %s %s &" % (image_name,image_name,image))
    if image in init_images:
        pull_harbor_file.write("docker pull %s && docker tag %s %s &\n" % (new_image,new_image,image))
    load_image_file.write('gunzip -c %s.tar.gz | docker load &\n' % (image.replace('/','-').replace(':','-')))

    # # 拉取公有镜像
    # print("docker pull %s && docker tag %s %s &" % (image_name,image_name,image))
    # print("docker pull %s &" % (image,))
    pull_file.write("docker pull %s &\n" % (image,))

pull_file.write('\nwait\n')
pull_save_file.write('\nwait\n')
load_image_file.write('\nwait\n')
pull_harbor_file.write('\nwait\n')
push_harbor_file.write('\nwait\n')

print('若服务器可以链网，直接执行sh pull_images.sh')
print('若服务器无法联网，替换本代码中的内网harbor仓库名，先在可联网机器上执行push_harbor.sh，再在内网机器上执行pull_harbor.sh')



