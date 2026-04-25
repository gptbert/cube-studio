# Cube Studio 已收敛为 MLOps 控制面：
# 数据平台职责（SQLLab / 元数据 / 维表 / ETL 编排 / 数据智能）
# 由 DolphinScheduler + Hadoop YARN + Spark 3.5 体系承担，
# 对应视图与模型已在 Phase 2 中删除。
from . import base
from . import home
from . import route
from . import view_k8s
from . import view_team
from . import view_dataset            # 数据集：仅作训练数据引用入口
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
from . import view_log
from . import view_user_role

from . import view_aihub
from . import view_total_resource
