"""indexes on FK columns used by ON DELETE cascades (keeps scenario reset fast)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_pod_members_passenger_id", "pod_members", ["passenger_id"]),
    ("ix_idempotency_keys_passenger_id", "idempotency_keys", ["passenger_id"]),
    ("ix_allocations_run_id", "allocations", ["run_id"]),
    ("ix_allocation_runs_batch_id", "allocation_runs", ["batch_id"]),
    ("ix_disruptions_service_id", "disruptions", ["service_id"]),
    ("ix_disruptions_edge_id", "disruptions", ["edge_id"]),
    ("ix_passenger_disruptions_disruption_id", "passenger_disruptions", ["disruption_id"]),
    ("ix_edges_from_node_id", "edges", ["from_node_id"]),
    ("ix_edges_to_node_id", "edges", ["to_node_id"]),
    ("ix_service_stops_node_id", "service_stops", ["node_id"]),
    ("ix_passengers_hub_node_id", "passengers", ["hub_node_id"]),
    ("ix_passengers_destination_node_id", "passengers", ["destination_node_id"]),
    ("ix_passengers_group_id", "passengers", ["group_id"]),
    ("ix_requests_choice1_service_id", "requests", ["choice1_service_id"]),
    ("ix_requests_choice2_service_id", "requests", ["choice2_service_id"]),
    ("ix_pods_origin_node_id", "pods", ["origin_node_id"]),
    ("ix_pods_destination_node_id", "pods", ["destination_node_id"]),
    ("ix_waitlist_entries_service_status", "waitlist_entries", ["service_id", "status"]),
    ("ix_notifications_scenario_created", "notifications", ["scenario_id", "id"]),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
