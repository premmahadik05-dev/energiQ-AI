"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-03 00:15:20.321036
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('audit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('resource_type', sa.String(length=24), nullable=False),
    sa.Column('resource_id', sa.String(length=64), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_events_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_events_ts'), ['ts'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_events_user_id'), ['user_id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('datasets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('report', sa.JSON(), nullable=False),
    sa.Column('quality_score', sa.Float(), nullable=True),
    sa.Column('hours', sa.Integer(), nullable=False),
    sa.Column('valid_hours', sa.Integer(), nullable=False),
    sa.Column('start_ts', sa.DateTime(), nullable=True),
    sa.Column('end_ts', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_datasets_owner_id'), ['owner_id'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('message', sa.String(length=300), nullable=False),
    sa.Column('link', sa.String(length=200), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_owner_id'), ['owner_id'], unique=False)

    op.create_table('tariffs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('weekday_rates', sa.JSON(), nullable=False),
    sa.Column('weekend_rates', sa.JSON(), nullable=False),
    sa.Column('daily_fixed_charge', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_id', 'name', name='uq_tariff_owner_name')
    )
    with op.batch_alter_table('tariffs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tariffs_owner_id'), ['owner_id'], unique=False)

    op.create_table('anomaly_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('sensitivity', sa.String(length=8), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('anomaly_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_anomaly_runs_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomaly_runs_owner_id'), ['owner_id'], unique=False)

    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('progress', sa.Float(), nullable=False),
    sa.Column('message', sa.String(length=255), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_owner_id'), ['owner_id'], unique=False)

    op.create_table('model_versions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('family', sa.String(length=24), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('horizon_model_ids', sa.JSON(), nullable=False),
    sa.Column('train_rows', sa.Integer(), nullable=False),
    sa.Column('train_end', sa.DateTime(), nullable=True),
    sa.Column('data_hash', sa.String(length=32), nullable=False),
    sa.Column('evaluation', sa.JSON(), nullable=False),
    sa.Column('explanation', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('model_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_model_versions_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_model_versions_owner_id'), ['owner_id'], unique=False)

    op.create_table('readings',
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('value_kw', sa.Float(), nullable=True),
    sa.Column('valid_fraction', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('dataset_id', 'ts')
    )
    op.create_table('recommendation_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('tariff_name', sa.String(length=80), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('recommendation_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recommendation_snapshots_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recommendation_snapshots_owner_id'), ['owner_id'], unique=False)

    op.create_table('anomalies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('start_ts', sa.DateTime(), nullable=False),
    sa.Column('end_ts', sa.DateTime(), nullable=False),
    sa.Column('hours', sa.Integer(), nullable=False),
    sa.Column('types', sa.JSON(), nullable=False),
    sa.Column('severity', sa.String(length=8), nullable=False),
    sa.Column('severity_level', sa.Integer(), nullable=False),
    sa.Column('peak_ts', sa.DateTime(), nullable=False),
    sa.Column('peak_value_kw', sa.Float(), nullable=True),
    sa.Column('expected_kw', sa.Float(), nullable=True),
    sa.Column('peak_excess_ratio', sa.Float(), nullable=True),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('acknowledged', sa.Boolean(), nullable=False),
    sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['anomaly_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_anomalies_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index('ix_anomalies_dataset_start', ['dataset_id', 'start_ts'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_run_id'), ['run_id'], unique=False)

    op.create_table('forecasts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('model_id', sa.String(length=64), nullable=False),
    sa.Column('origin', sa.DateTime(), nullable=False),
    sa.Column('points', sa.JSON(), nullable=False),
    sa.Column('origin_value_missing', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['model_id'], ['model_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_forecasts_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_forecasts_model_id'), ['model_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_forecasts_owner_id'), ['owner_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_forecasts_owner_id'))
        batch_op.drop_index(batch_op.f('ix_forecasts_model_id'))
        batch_op.drop_index(batch_op.f('ix_forecasts_dataset_id'))

    op.drop_table('forecasts')
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_anomalies_run_id'))
        batch_op.drop_index(batch_op.f('ix_anomalies_owner_id'))
        batch_op.drop_index('ix_anomalies_dataset_start')
        batch_op.drop_index(batch_op.f('ix_anomalies_dataset_id'))

    op.drop_table('anomalies')
    with op.batch_alter_table('recommendation_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recommendation_snapshots_owner_id'))
        batch_op.drop_index(batch_op.f('ix_recommendation_snapshots_dataset_id'))

    op.drop_table('recommendation_snapshots')
    op.drop_table('readings')
    with op.batch_alter_table('model_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_model_versions_owner_id'))
        batch_op.drop_index(batch_op.f('ix_model_versions_dataset_id'))

    op.drop_table('model_versions')
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_owner_id'))
        batch_op.drop_index(batch_op.f('ix_jobs_dataset_id'))

    op.drop_table('jobs')
    with op.batch_alter_table('anomaly_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_anomaly_runs_owner_id'))
        batch_op.drop_index(batch_op.f('ix_anomaly_runs_dataset_id'))

    op.drop_table('anomaly_runs')
    with op.batch_alter_table('tariffs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tariffs_owner_id'))

    op.drop_table('tariffs')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_owner_id'))

    op.drop_table('notifications')
    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_datasets_owner_id'))

    op.drop_table('datasets')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_events_user_id'))
        batch_op.drop_index(batch_op.f('ix_audit_events_ts'))
        batch_op.drop_index(batch_op.f('ix_audit_events_action'))

    op.drop_table('audit_events')
