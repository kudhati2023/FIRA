"""Initial schema with all FIRA entities, RLS policies, and audit log protection

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-02 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_SCOPED_TABLES = [
    "app_user",
    "client",
    "client_branch",
    "mapping_profile",
    "engagement",
    "import_batch",
    "ap_line",
    "zimra_line",
    "match",
    "supplier",
    "exception",
    "supplier_action",
    "report_artifact",
    "engagement_metric",
    "audit_log",
]

def upgrade() -> None:
    # 1. Create Enums
    user_role = postgresql.ENUM("ADMIN", "REVIEWER", "OPERATOR", name="user_role_enum")
    user_role.create(op.get_bind(), checkfirst=True)

    engagement_type = postgresql.ENUM("AUDIT", "RETAINER_MONTHLY", name="engagement_type_enum")
    engagement_type.create(op.get_bind(), checkfirst=True)

    engagement_status = postgresql.ENUM("DRAFT", "INGESTING", "RECONCILING", "REVIEW", "REPORTED", "CLOSED", name="engagement_status_enum")
    engagement_status.create(op.get_bind(), checkfirst=True)

    source_type = postgresql.ENUM("AP_LEDGER", "ZIMRA_CLAIM_LIST", "MANUAL_ENTRY", name="source_type_enum")
    source_type.create(op.get_bind(), checkfirst=True)

    document_type = postgresql.ENUM("INVOICE", "CREDIT_NOTE", "DEBIT_NOTE", name="document_type_enum")
    document_type.create(op.get_bind(), checkfirst=True)

    line_status = postgresql.ENUM("OK", "NEEDS_ATTENTION", "EXCLUDED", name="line_status_enum")
    line_status.create(op.get_bind(), checkfirst=True)

    exception_class = postgresql.ENUM("E1", "E2", "E3", "E4", "E5", "E6", "E7", name="exception_class_enum")
    exception_class.create(op.get_bind(), checkfirst=True)

    exception_status = postgresql.ENUM("OPEN", "NOTIFIED", "SUPPLIER_ACKNOWLEDGED", "RESOLVED", "UNRECOVERABLE", "DISMISSED", name="exception_status_enum")
    exception_status.create(op.get_bind(), checkfirst=True)

    supplier_outcome = postgresql.ENUM("PENDING", "CORRECTED", "REFUSED", "NO_RESPONSE", "PARTIAL", name="supplier_outcome_enum")
    supplier_outcome.create(op.get_bind(), checkfirst=True)

    report_artifact_kind = postgresql.ENUM("EXCEPTION_REGISTER_XLSX", "FINDINGS_PACK_PDF", "SUPPLIER_LETTER_DOCX", "SUPPLIER_LETTER_PDF", "METRICS_CSV", name="report_artifact_kind_enum")
    report_artifact_kind.create(op.get_bind(), checkfirst=True)

    # 2. Global / Master Tables
    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("settings_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("retention_months", sa.Integer(), server_default=sa.text("24"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )
    op.create_index("ix_tenant_slug", "tenant", ["slug"])

    op.create_table(
        "vat_rate_period",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("jurisdiction", sa.String(10), server_default="ZW", nullable=False),
        sa.Column("rate_basis_points", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vat_rate_period_jurisdiction", "vat_rate_period", ["jurisdiction"])
    op.create_index("ix_vat_rate_period_effective_from", "vat_rate_period", ["effective_from"])
    op.create_index("ix_vat_rate_period_effective_to", "vat_rate_period", ["effective_to"])

    op.create_table(
        "config_setting",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_config_setting_tenant_id", "config_setting", ["tenant_id"])
    op.create_index("ix_config_setting_key", "config_setting", ["key"])

    # 3. Tenant-Scoped Tables
    op.create_table(
        "app_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="OPERATOR"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret_encrypted", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
    )
    op.create_index("ix_app_user_tenant_id", "app_user", ["tenant_id"])
    op.create_index("ix_app_user_email", "app_user", ["email"])

    op.create_table(
        "client",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("trading_name", sa.String(255), nullable=True),
        sa.Column("tin_raw", sa.String(50), nullable=False),
        sa.Column("tin_normalised", sa.String(50), nullable=False),
        sa.Column("vat_number", sa.String(50), nullable=True),
        sa.Column("vat_category", sa.String(10), server_default="C", nullable=False),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(100), nullable=True),
        sa.Column("industry_code", sa.String(50), nullable=True),
        sa.Column("default_currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("retention_months_override", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_client_tenant_id", "client", ["tenant_id"])
    op.create_index("ix_client_tin_normalised", "client", ["tin_normalised"])
    op.create_index(
        "ix_client_tenant_tin_active",
        "client",
        ["tenant_id", "tin_normalised"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL")
    )

    op.create_table(
        "client_branch",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("device_serials_json", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_client_branch_tenant_id", "client_branch", ["tenant_id"])
    op.create_index("ix_client_branch_client_id", "client_branch", ["client_id"])

    op.create_table(
        "mapping_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("header_signature", sa.String(255), nullable=False),
        sa.Column("column_map_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mapping_profile_tenant_id", "mapping_profile", ["tenant_id"])
    op.create_index("ix_mapping_profile_client_id", "mapping_profile", ["client_id"])
    op.create_index("ix_mapping_profile_header_signature", "mapping_profile", ["header_signature"])

    op.create_table(
        "engagement",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("vat_category", sa.String(10), server_default="C", nullable=False),
        sa.Column("engagement_type", engagement_type, server_default="AUDIT", nullable=False),
        sa.Column("status", engagement_status, server_default="DRAFT", nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fee_quoted_minor", sa.BigInteger(), nullable=True),
        sa.Column("fee_accepted_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warnings_json", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_engagement_tenant_reference"),
    )
    op.create_index("ix_engagement_tenant_id", "engagement", ["tenant_id"])
    op.create_index("ix_engagement_client_id", "engagement", ["client_id"])
    op.create_index("ix_engagement_reference", "engagement", ["reference"])

    op.create_table(
        "import_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("row_count_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("row_count_accepted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("row_count_rejected", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("mapping_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mapping_profile.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(50), server_default="PROCESSED", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "file_sha256", name="uq_import_batch_engagement_sha256"),
    )
    op.create_index("ix_import_batch_tenant_id", "import_batch", ["tenant_id"])
    op.create_index("ix_import_batch_engagement_id", "import_batch", ["engagement_id"])

    op.create_table(
        "ap_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_batch.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("supplier_name_raw", sa.String(255), nullable=False),
        sa.Column("supplier_name_norm", sa.String(255), nullable=False),
        sa.Column("supplier_tin_raw", sa.String(50), nullable=True),
        sa.Column("supplier_tin_norm", sa.String(50), nullable=True),
        sa.Column("invoice_number_raw", sa.String(100), nullable=False),
        sa.Column("invoice_number_norm", sa.String(100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("document_type", document_type, server_default="INVOICE", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("net_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("gross_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("expense_category", sa.String(100), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("status", line_status, server_default="OK", nullable=False),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ap_line_tenant_id", "ap_line", ["tenant_id"])
    op.create_index("ix_ap_line_engagement_id", "ap_line", ["engagement_id"])
    op.create_index("ix_ap_line_supplier_name_norm", "ap_line", ["supplier_name_norm"])
    op.create_index("ix_ap_line_supplier_tin_norm", "ap_line", ["supplier_tin_norm"])
    op.create_index("ix_ap_line_invoice_number_norm", "ap_line", ["invoice_number_norm"])
    op.create_index("ix_ap_line_invoice_date", "ap_line", ["invoice_date"])

    op.create_table(
        "zimra_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_batch.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("supplier_name_raw", sa.String(255), nullable=False),
        sa.Column("supplier_name_norm", sa.String(255), nullable=False),
        sa.Column("supplier_tin_raw", sa.String(50), nullable=True),
        sa.Column("supplier_tin_norm", sa.String(50), nullable=True),
        sa.Column("invoice_number_raw", sa.String(100), nullable=False),
        sa.Column("invoice_number_norm", sa.String(100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("document_type", document_type, server_default="INVOICE", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("net_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("gross_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("buyer_name_raw", sa.String(255), nullable=True),
        sa.Column("buyer_tin_raw", sa.String(50), nullable=True),
        sa.Column("buyer_tin_norm", sa.String(50), nullable=True),
        sa.Column("buyer_vat_number", sa.String(50), nullable=True),
        sa.Column("validity_status_raw", sa.String(50), nullable=True),
        sa.Column("validity_is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("device_id", sa.String(100), nullable=True),
        sa.Column("receipt_global_no", sa.String(100), nullable=True),
        sa.Column("fiscal_day_no", sa.String(100), nullable=True),
        sa.Column("status", line_status, server_default="OK", nullable=False),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_zimra_line_tenant_id", "zimra_line", ["tenant_id"])
    op.create_index("ix_zimra_line_engagement_id", "zimra_line", ["engagement_id"])
    op.create_index("ix_zimra_line_supplier_name_norm", "zimra_line", ["supplier_name_norm"])
    op.create_index("ix_zimra_line_supplier_tin_norm", "zimra_line", ["supplier_tin_norm"])
    op.create_index("ix_zimra_line_invoice_number_norm", "zimra_line", ["invoice_number_norm"])
    op.create_index("ix_zimra_line_invoice_date", "zimra_line", ["invoice_date"])
    op.create_index("ix_zimra_line_buyer_tin_norm", "zimra_line", ["buyer_tin_norm"])

    op.create_table(
        "match",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ap_line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ap_line.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zimra_line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("zimra_line.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pass_id", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "ap_line_id", name="uq_match_engagement_ap_line"),
        sa.UniqueConstraint("engagement_id", "zimra_line_id", name="uq_match_engagement_zimra_line"),
    )
    op.create_index("ix_match_tenant_id", "match", ["tenant_id"])
    op.create_index("ix_match_engagement_id", "match", ["engagement_id"])

    op.create_table(
        "supplier",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tin_normalised", sa.String(50), nullable=False),
        sa.Column("name_norm", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(100), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "tin_normalised", name="uq_supplier_tenant_tin"),
    )
    op.create_index("ix_supplier_tenant_id", "supplier", ["tenant_id"])
    op.create_index("ix_supplier_tin_normalised", "supplier", ["tin_normalised"])
    op.create_index("ix_supplier_name_norm", "supplier", ["name_norm"])

    op.create_table(
        "exception",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ap_line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ap_line.id", ondelete="CASCADE"), nullable=True),
        sa.Column("zimra_line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("zimra_line.id", ondelete="CASCADE"), nullable=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("primary_class", exception_class, nullable=False),
        sa.Column("all_classes_json", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("vat_at_risk_minor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("is_recoverable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_advisory", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("supplier.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", exception_status, server_default="OPEN", nullable=False),
        sa.Column("override_of_class", exception_class, nullable=True),
        sa.Column("override_reason", sa.String(500), nullable=True),
        sa.Column("overridden_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exception_tenant_id", "exception", ["tenant_id"])
    op.create_index("ix_exception_engagement_id", "exception", ["engagement_id"])
    op.create_index("ix_exception_primary_class", "exception", ["primary_class"])
    op.create_index("ix_exception_status", "exception", ["status"])

    op.create_table(
        "supplier_action",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("supplier.id", ondelete="CASCADE"), nullable=False),
        sa.Column("letter_ref", sa.String(100), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_summary", sa.String(1000), nullable=True),
        sa.Column("outcome", supplier_outcome, server_default="PENDING", nullable=False),
        sa.Column("exception_ids_json", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_action_tenant_id", "supplier_action", ["tenant_id"])
    op.create_index("ix_supplier_action_engagement_id", "supplier_action", ["engagement_id"])

    op.create_table(
        "report_artifact",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("kind", report_artifact_kind, nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_report_artifact_tenant_id", "report_artifact", ["tenant_id"])
    op.create_index("ix_report_artifact_engagement_id", "report_artifact", ["engagement_id"])

    op.create_table(
        "engagement_metric",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(500), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("captured_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_engagement_metric_tenant_id", "engagement_metric", ["tenant_id"])
    op.create_index("ix_engagement_metric_engagement_id", "engagement_metric", ["engagement_id"])
    op.create_index("ix_engagement_metric_key", "engagement_metric", ["key"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("before_json", postgresql.JSONB, nullable=True),
        sa.Column("after_json", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])

    # 4. Enable Row-Level Security (RLS) & Policies on all tenant-scoped tables
    for table_name in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table_name}
            AS PERMISSIVE
            FOR ALL
            TO PUBLIC
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                OR current_setting('app.is_admin', true) = 'true'
            );
        """)

    # 5. Enforce Append-Only Protection on audit_log (FR-AUD-1 & §11.4)
    op.execute("""
        CREATE OR REPLACE FUNCTION protect_audit_log() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'UPDATE and DELETE operations are strictly prohibited on audit_log table (FR-AUD-1)';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_audit_log_prevent_mutations
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION protect_audit_log();
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_prevent_mutations ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS protect_audit_log();")

    for table_name in reversed(TENANT_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")

    for table_name in [
        "audit_log",
        "engagement_metric",
        "report_artifact",
        "supplier_action",
        "exception",
        "supplier",
        "match",
        "zimra_line",
        "ap_line",
        "import_batch",
        "engagement",
        "mapping_profile",
        "client_branch",
        "client",
        "app_user",
        "config_setting",
        "vat_rate_period",
        "tenant",
    ]:
        op.drop_table(table_name)

    for enum_name in [
        "report_artifact_kind_enum",
        "supplier_outcome_enum",
        "exception_status_enum",
        "exception_class_enum",
        "line_status_enum",
        "document_type_enum",
        "source_type_enum",
        "engagement_status_enum",
        "engagement_type_enum",
        "user_role_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
