from myapp import conf

# MLOps-Only 模式：数仓 / ETL / SQL 查询 / 元数据 等数据平台职责由
# DolphinScheduler + Hadoop YARN + Spark 3.5 体系承担，Cube Studio
# 聚焦 MLOps 控制面（开发 / 训练 / 模型 / 推理 / 资源）。
# 默认开启；如需临时恢复完整数据能力，在 config.py 设置：
#     MLOPS_ONLY_MODE = False
MLOPS_ONLY_MODE = conf.get("MLOPS_ONLY_MODE", True)

from . import base
from . import home
from . import route
from . import view_k8s
from . import view_team
from . import view_dataset            # 数据集：保留作训练数据引用，不做完整数据平台
from . import view_images
from . import view_notebook
from . import view_docker

from . import view_job_template
from . import view_task
from . import view_pipeline
from . import view_runhistory
from . import view_workflow
from . import view_nni
from . import view_train_model
from . import view_serving
from . import view_inferenceserving
# from . import view_service_pipeline
from . import view_log
from . import view_user_role

from . import view_aihub
from . import view_total_resource

# 数据平台 / 知识库模块：默认隐藏，避免与数仓体系职责重叠
if not MLOPS_ONLY_MODE:
    from . import view_metadata          # 数据地图：库表
    from . import view_metadata_metric   # 数据地图：指标
    from . import view_dimension         # 维表
    from . import view_etl_pipeline      # ETL 编排（包含 airflow/azkaban/dolphinscheduler 适配）
    from . import view_sqllab            # SqlLab 在线查询
    from . import view_chat              # 数据智能 / RAG 知识库（P2 后续作为独立 AI 应用接入）
