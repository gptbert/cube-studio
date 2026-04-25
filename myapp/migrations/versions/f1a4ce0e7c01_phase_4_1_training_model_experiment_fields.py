"""Phase 4.1 实验追踪：扩展 model 表

为 Training_Model 增加实验追踪所需的 6 个字段：
  - params         训练超参（JSON dict）
  - artifacts      训练产物路径列表（JSON list）
  - log_url        训练日志链接
  - status         训练状态
  - experiment_id  实验分组 ID（带索引，便于按实验聚合查询）
  - parent_run_id  父 run id，用于增量训练 / 微调链路追溯

新字段全部带服务器侧默认值，历史行无需回填即可继续工作。

Revision ID: f1a4ce0e7c01
Revises: 593366be4eff
Create Date: 2026-04-25 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a4ce0e7c01'
down_revision = '593366be4eff'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'model',
        sa.Column('params', sa.Text(length=65536), nullable=True, server_default='{}'),
    )
    op.add_column(
        'model',
        sa.Column('artifacts', sa.Text(length=65536), nullable=True, server_default='[]'),
    )
    op.add_column(
        'model',
        sa.Column('log_url', sa.String(length=500), nullable=True, server_default=''),
    )
    op.add_column(
        'model',
        sa.Column('status', sa.String(length=32), nullable=True, server_default='success'),
    )
    op.add_column(
        'model',
        sa.Column('experiment_id', sa.String(length=100), nullable=True, server_default=''),
    )
    op.add_column(
        'model',
        sa.Column('parent_run_id', sa.String(length=100), nullable=True, server_default=''),
    )
    op.create_index(
        'ix_model_experiment_id', 'model', ['experiment_id'], unique=False,
    )


def downgrade():
    op.drop_index('ix_model_experiment_id', table_name='model')
    op.drop_column('model', 'parent_run_id')
    op.drop_column('model', 'experiment_id')
    op.drop_column('model', 'status')
    op.drop_column('model', 'log_url')
    op.drop_column('model', 'artifacts')
    op.drop_column('model', 'params')
