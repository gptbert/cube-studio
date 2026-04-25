"""Pipeline domain services.

Extracted from view layer to let tasks depend on service layer directly.
"""

import datetime
import json
import re
import time
import uuid
from jinja2 import BaseLoader, Environment, Undefined
from flask import g
from kubernetes import client
from kubernetes.client.models import V1EnvVar, V1SecurityContext

from myapp import app, db
from myapp.models.model_job import Repository, Task
from myapp.utils.py import py_k8s
from myapp.exceptions import MyappException
from myapp.utils import core

conf = app.config

def make_workflow_yaml(pipeline,workflow_label,hubsecret_list,dag_templates,containers_templates,dbsession=db.session):
    name = pipeline.name+"-"+uuid.uuid4().hex[:4]
    workflow_label['workflow-name']=name
    workflow_crd_json={
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            # "generateName": pipeline.name+"-",
            "annotations": {
                "name": pipeline.name,
                "description": pipeline.describe.encode("unicode_escape").decode('utf-8')
            },
            "name": name,
            "labels": workflow_label,
            "namespace": pipeline.project.pipeline_namespace
        },
        "spec": {
            "ttlStrategy": {
                "secondsAfterCompletion": 10800,  # 3个小时候自动删除
                "ttlSecondsAfterFinished": 10800,  # 3个小时候自动删除
            },
            "archiveLogs": True,  # 打包日志
            "entrypoint": pipeline.name,
            "templates": [
                             {
                                 "name": pipeline.name,
                                 "dag": {
                                     "tasks": dag_templates
                                 }
                             }
                         ] + containers_templates,
            "arguments": {
                "parameters": []
            },
            "serviceAccountName": "pipeline-runner",
            "parallelism": int(pipeline.parallelism),
            "imagePullSecrets": [
                {
                    "name": hubsecret
                } for hubsecret in hubsecret_list
            ]
        }
    }
    return workflow_crd_json


# 转化为worfklow的yaml
# @pysnooper.snoop()
def dag_to_pipeline(pipeline, dbsession, workflow_label=None, **kwargs):
    dag_json = pipeline.fix_dag_json(dbsession)
    pipeline.dag_json=dag_json
    dbsession.commit()
    dag = json.loads(dag_json)

    # 如果dag为空，就直接退出
    if not dag:
        return None, None

    all_tasks = {}
    for task_name in dag:
        # 使用临时连接，避免连接中断的问题
        # try:

        task = dbsession.query(Task).filter_by(name=task_name, pipeline_id=pipeline.id).first()
        if not task:
            raise MyappException('task %s not exist ' % task_name)
        all_tasks[task_name] = task

    template_kwargs=kwargs
    if 'execution_date' not in template_kwargs:
        template_kwargs['execution_date'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 渲染字符串模板变量
    # @pysnooper.snoop()
    def template_str(src_str):
        rtemplate = Environment(loader=BaseLoader, undefined=Undefined).from_string(src_str)
        des_str = rtemplate.render(creator=pipeline.created_by.username,
                                   datetime=datetime,
                                   runner=g.user.username if g and g.user and g.user.username else pipeline.created_by.username,
                                   uuid=uuid,
                                   pipeline_id=pipeline.id,
                                   pipeline_name=pipeline.name,
                                   cluster_name=pipeline.project.cluster['NAME'],
                                   **template_kwargs
                                   )
        return des_str

    pipeline_global_env = template_str(pipeline.global_env.strip()) if pipeline.global_env else ''  # 优先渲染，不然里面如果有date就可能存在不一致的问题
    pipeline_global_env = [env.strip() for env in pipeline_global_env.split('\n') if '=' in env.strip()]

    # 系统级别环境变量
    global_envs = json.loads(template_str(json.dumps(conf.get('GLOBAL_ENV', {}), indent=4, ensure_ascii=False)))
    for env in pipeline_global_env:
        key, value = env[:env.index('=')], env[env.index('=') + 1:]
        global_envs[key] = value
    # 全局环境变量可以在任务的参数中引用
    for global_env in pipeline_global_env:
        key,value = global_env.split('=')[0],global_env.split('=')[1]
        if key not in kwargs:
            template_kwargs[key]=value

    def make_dag_template():
        dag_template = []
        for task_name in dag:
            template_temp = {
                "name": task_name,
                "template": task_name,
                "dependencies": dag[task_name].get('upstream', [])
            }
            # 设置了跳过的话，在argo中设置跳过
            if all_tasks[task_name].skip:
                template_temp['when']='false'
            dag_template.append(template_temp)
        return dag_template

    # @pysnooper.snoop()
    def make_container_template(task_name,hubsecret_list=None):
        task = all_tasks[task_name]
        ops_args = []
        task_args = json.loads(task.args)
        for task_attr_name in task_args:
            # 布尔型只添加参数名
            if type(task_args[task_attr_name]) == bool:
                if task_args[task_attr_name]:
                    ops_args.append('%s' % str(task_attr_name))
            # 控制不添加
            elif not task_args[task_attr_name]:  # 如果参数值为空，则都不添加
                pass
            # json类型直接导入序列化以后的
            elif type(task_args[task_attr_name]) == dict or type(task_args[task_attr_name]) == list:
                ops_args.append('%s' % str(task_attr_name))
                args_values = json.dumps(task_args[task_attr_name], ensure_ascii=False)
                # args_values = template_str(args_values) if re.match('\{\{.*\}\}',args_values) else args_values
                ops_args.append('%s' % args_values)
            # # list类型，分多次导入,# list类型逗号分隔就好了
            # elif type(task_args[task_attr_name]) == list:
            #     for args_values in task_args[task_attr_name].split('\n'):
            #         ops_args.append('%s' % str(task_attr_name))
            #         # args_values = template_str(args_values) if re.match('\{\{.*\}\}',args_values) else args_values
            #         ops_args.append('%s' % args_values)
            # 其他的直接添加
            elif task_attr_name not in ['images','workdir']:
                ops_args.append('%s' % str(task_attr_name))
                args_values = task_args[task_attr_name]
                # args_values = template_str(args_values) if re.match('\{\{.*\}\}',args_values) else args_values
                ops_args.append('%s' % str(args_values))  # 这里应该对不同类型的参数名称做不同的参数处理，比如bool型，只有参数，没有值

        # 设置环境变量
        container_envs = []
        if task.job_template.env:
            envs = re.split('\r|\n', task.job_template.env)
            envs = [env.strip() for env in envs if env.strip()]
            for env in envs:
                env_key, env_value = env.split('=')[0], env.split('=')[1]
                container_envs.append((env_key, env_value))

        # 设置全局环境变量
        for global_env_key in global_envs:
            container_envs.append((global_env_key, global_envs[global_env_key]))

        # 设置task的默认环境变量
        _, _, gpu_resource_name = core.get_gpu(task.resource_gpu)
        container_envs.append(("KFJ_TASK_ID", str(task.id)))
        container_envs.append(("KFJ_TASK_NAME", str(task.name)))
        container_envs.append(("KFJ_TASK_NODE_SELECTOR", str(task.get_node_selector())))
        container_envs.append(("KFJ_TASK_VOLUME_MOUNT", str(task.volume_mount)))
        container_envs.append(("KFJ_TASK_IMAGES", str(task.job_template.images)))
        container_envs.append(("KFJ_TASK_RESOURCE_CPU", str(task.resource_cpu)))
        container_envs.append(("KFJ_TASK_RESOURCE_MEMORY", str(task.resource_memory)))
        container_envs.append(("KFJ_TASK_RESOURCE_GPU", str(task.resource_gpu)))
        container_envs.append(("KFJ_TASK_PROJECT_NAME", str(pipeline.project.name)))
        container_envs.append(("GPU_RESOURCE_NAME", gpu_resource_name))
        container_envs.append(("USERNAME", pipeline.created_by.username))
        container_envs.append(("IMAGE_PULL_POLICY", conf.get('IMAGE_PULL_POLICY','Always')))
        if hubsecret_list:
            container_envs.append(("HUBSECRET", ','.join(hubsecret_list)))


        # 创建工作目录
        working_dir = None
        if task.job_template.workdir and task.job_template.workdir.strip():
            working_dir = task.job_template.workdir.strip()
        if task.working_dir and task.working_dir.strip():
            working_dir = task.working_dir.strip()

        # 配置启动命令
        task_command = ''

        if task.command:
            commands = re.split('\r|\n', task.command)
            commands = [command.strip() for command in commands if command.strip()]
            if task_command:
                task_command += " && " + " && ".join(commands)
            else:
                task_command += " && ".join(commands)

        job_template_entrypoint = task.job_template.entrypoint.strip() if task.job_template.entrypoint else ''

        command = None
        if job_template_entrypoint:
            command = job_template_entrypoint

        if task_command:
            command = task_command

        images = task.job_template.images.name
        command = command.split(' ') if command else []
        command = [com for com in command if com]
        arguments = ops_args
        file_outputs = json.loads(task.outputs) if task.outputs and json.loads(task.outputs) else None

        # 如果模板配置了images参数，那直接用模板的这个参数
        if json.loads(task.args).get('images',''):
            images = json.loads(task.args).get('images')

        # 自定义节点
        if task.job_template.name == conf.get('CUSTOMIZE_JOB'):
            working_dir = json.loads(task.args).get('workdir')
            command = ['bash', '-c', json.loads(task.args).get('command')]
            arguments = []

        # 添加用户自定义挂载
        k8s_volumes = []
        k8s_volume_mounts = []
        task.volume_mount = task.volume_mount.strip() if task.volume_mount else ''
        if task.volume_mount:
            try:
                k8s_volumes,k8s_volume_mounts = py_k8s.K8s.get_volume_mounts(task.volume_mount,pipeline.created_by.username)
            except Exception as e:
                print(e)

        # 添加node selector
        nodeSelector, nodeAffinity = core.get_node_selector(task.get_node_selector())

        # 添加pod label
        pod_label = {
            "pipeline-id": str(pipeline.id),
            "pipeline-name": str(pipeline.name),
            "app":str(pipeline.name),
            "task-id": str(task.id),
            "task-name": str(task.name),
            "run-id": global_envs.get('KFJ_RUN_ID', ''),
            'run-username': g.user.username if g and g.user and g.user.username else pipeline.created_by.username,
            'pipeline-username': pipeline.created_by.username

        }
        pod_annotations = {
            'project': pipeline.project.name,
            'pipeline': pipeline.describe,
            "task": task.label,
            'job-template': task.job_template.describe
        }

        # 设置资源限制
        resource_cpu = task.job_template.get_env('TASK_RESOURCE_CPU') if task.job_template.get_env('TASK_RESOURCE_CPU') else task.resource_cpu
        resource_gpu = task.job_template.get_env('TASK_RESOURCE_GPU') if task.job_template.get_env('TASK_RESOURCE_GPU') else task.resource_gpu

        resource_memory = task.job_template.get_env('TASK_RESOURCE_MEMORY') if task.job_template.get_env('TASK_RESOURCE_MEMORY') else task.resource_memory

        resources_requests = resources_limits = {}

        if resource_memory:
            if not '~' in resource_memory:
                resources_requests['memory'] = resource_memory
                resources_limits['memory'] = resource_memory
            else:
                resources_requests['memory'] = resource_memory.split("~")[0]
                resources_limits['memory'] = resource_memory.split("~")[1]

        if resource_cpu:
            if not '~' in resource_cpu:
                resources_requests['cpu'] = resource_cpu
                resources_limits['cpu'] = resource_cpu

            else:
                resources_requests['cpu'] = resource_cpu.split("~")[0]
                resources_limits['cpu'] = resource_cpu.split("~")[1]

        if resource_gpu:

            gpu_num, gpu_type, gpu_resource_name = core.get_gpu(resource_gpu)

            # 整卡占用
            if gpu_num >= 1:

                resources_requests[gpu_resource_name] = str(int(gpu_num))
                resources_limits[gpu_resource_name] = str(int(gpu_num))

            if 0 == gpu_num:
                # 没要gpu的容器，就要加上可视gpu为空，不然gpu镜像能看到和使用所有gpu
                for gpu_alias in conf.get('GPU_NONE', {}):
                    container_envs.append((conf.get('GPU_NONE',{})[gpu_alias][0], conf.get('GPU_NONE',{})[gpu_alias][1]))
        # 配置host
        host_aliases = {}

        global_host_aliases = conf.get('HOSTALIASES', '')
        # global_host_aliases = ''
        if task_temp.job_template.host_aliases:
            global_host_aliases += "\n" + task_temp.job_template.host_aliases
        if global_host_aliases:
            host_aliases_list = re.split('\r|\n', global_host_aliases)
            host_aliases_list = [host.strip() for host in host_aliases_list if host.strip()]
            for row in host_aliases_list:
                hosts = row.strip().split(' ')
                hosts = [host for host in hosts if host]
                if len(hosts) > 1:
                    host_aliases[hosts[1]] = hosts[0]

        if task.skip:
            command = ["echo", "skip"]
            arguments = None
            resources_requests = None
            resources_limits = None

        task_template = {
            "name": task.name,  # 因为同一个
            "outputs": {
                "artifacts": []
            },
            "container": {
                "name": task.name + "-" + uuid.uuid4().hex[:4],
                "ports": [],

                "command": command,
                "args": arguments,
                "env": [
                    {
                        "name": item[0],
                        "value": item[1]
                    } for item in container_envs
                ],
                "image": images,
                "resources": {
                    "limits": resources_limits,
                    "requests": resources_requests
                },
                "volumeMounts": k8s_volume_mounts,
                "workingDir": working_dir,
                "imagePullPolicy": conf.get('IMAGE_PULL_POLICY', 'Always')
            },
            "nodeSelector": nodeSelector,
            "securityContext": {
                "privileged": True if task.job_template.privileged else False
            },
            "affinity": {
                "podAntiAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": [
                        {
                            "podAffinityTerm": {
                                "labelSelector": {
                                    "matchLabels": {
                                        "pipeline-id": str(pipeline.id)
                                    }
                                },
                                "topologyKey": "kubernetes.io/hostname"
                            },
                            "weight": 80
                        }
                    ]
                }
            },
            "metadata": {
                "labels": pod_label,
                "annotations": pod_annotations
            },
            "retryStrategy": {
                "limit": int(task.retry)
            } if task.retry else None,
            "volumes": k8s_volumes,
            "hostAliases": [
                {
                    "hostnames": [hostname],
                    "ip": host_aliases[hostname]
                } for hostname in host_aliases
            ],
            "activeDeadlineSeconds": task.timeout if task.timeout else None
        }

        # 统一添加一些固定环境变量，比如hostip，podip等
        task_template['container']['env'].append({
            "name":"K8S_NODE_NAME",
            "valueFrom":{
                "fieldRef":{
                    "apiVersion":"v1",
                    "fieldPath":"spec.nodeName"
                }
            }
        })
        task_template['container']['env'].append({
            "name": "K8S_POD_IP",
            "valueFrom": {
                "fieldRef": {
                    "apiVersion": "v1",
                    "fieldPath": "status.podIP"
                }
            }
        })
        task_template['container']['env'].append({
            "name": "K8S_HOST_IP",
            "valueFrom": {
                "fieldRef": {
                    "apiVersion": "v1",
                    "fieldPath": "status.hostIP"
                }
            }
        })
        task_template['container']['env'].append({
            "name": "K8S_POD_NAME",
            "valueFrom": {
                "fieldRef": {
                    "apiVersion": "v1",
                    "fieldPath": "metadata.name"
                }
            }
        })


        return task_template

    # 添加个人创建的所有仓库秘钥
    image_pull_secrets = conf.get('HUBSECRET', [])
    user_repositorys = dbsession.query(Repository).filter(Repository.created_by_fk == pipeline.created_by.id).all()
    hubsecret_list = list(set(image_pull_secrets + [rep.hubsecret for rep in user_repositorys]))

    # 配置拉取秘钥
    for task_name in all_tasks:
        # 配置拉取秘钥。本来在contain里面，workflow在外面
        task_temp = all_tasks[task_name]
        if task_temp.job_template.images.repository.hubsecret:
            hubsecret = task_temp.job_template.images.repository.hubsecret
            if hubsecret not in hubsecret_list:
                hubsecret_list.append(hubsecret)

    hubsecret_list = list(set(hubsecret_list))

    # 设置workflow标签
    if not workflow_label:
        workflow_label = {}

    workflow_label['run-username'] = g.user.username if g and g.user and g.user.username else pipeline.created_by.username
    workflow_label['pipeline-username'] = pipeline.created_by.username
    workflow_label['save-time'] = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
    workflow_label['pipeline-id'] = str(pipeline.id)
    workflow_label['pipeline-name'] = str(pipeline.name)
    workflow_label['app'] = str(pipeline.name)
    workflow_label['run-id'] = global_envs.get('KFJ_RUN_ID', '')  # 以此来绑定运行时id，不能用kfp的run—id。那个是传到kfp以后才产生的。
    workflow_label['cluster'] = pipeline.project.cluster['NAME']

    containers_template = []
    for task_name in dag:
        containers_template.append(make_container_template(task_name=task_name,hubsecret_list=hubsecret_list))

    workflow_json = make_workflow_yaml(pipeline=pipeline, workflow_label=workflow_label, hubsecret_list=hubsecret_list, dag_templates=make_dag_template(), containers_templates=containers_template,dbsession=dbsession)
    # 先这是某个模板变量不进行渲染，一直向后传递到argo
    pipeline_file = json.dumps(workflow_json,ensure_ascii=False,indent=4)
    # print(pipeline_file)
    pipeline_file = template_str(pipeline_file)

    return pipeline_file, workflow_label['run-id']


# @pysnooper.snoop(watch_explode=())
def run_pipeline(pipeline, workflow_json):
    cluster = pipeline.project.cluster
    crd_name = workflow_json.get('metadata', {}).get('name', '')
    from myapp.utils.py.py_k8s import K8s
    k8s_client = K8s(cluster.get('KUBECONFIG', ''))
    namespace = workflow_json.get('metadata', {}).get("namespace", pipeline.project.pipeline_namespace)
    crd_info = conf.get('CRD_INFO', {}).get('workflow', {})
    try:
        workflow_obj = k8s_client.get_one_crd(group=crd_info['group'], version=crd_info['version'], plural=crd_info['plural'],namespace=namespace, name=crd_name)
        if workflow_obj:
            k8s_client.delete_crd(group=crd_info['group'], version=crd_info['version'], plural=crd_info['plural'],namespace=namespace, name=crd_name)
            time.sleep(1)

        crd = k8s_client.create_crd(group=crd_info['group'], version=crd_info['version'], plural=crd_info['plural'],namespace=namespace, body=workflow_json)
        pipeline.namespace=namespace
        db.session.commit()
    except Exception as e:
        print(e)

    return crd_name
