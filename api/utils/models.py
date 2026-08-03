from datetime import datetime, timezone
import uuid
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative ORM models.
    All ORM models in this module should inherit from this base class so
    SQLAlchemy can configure the declarative mappings and metadata.
    """
    pass


class TenantConfig(Base):
    """Tenant-specific configuration for the dunning system.

    Attributes:
        tenant_id: Unique identifier for the tenant.
        is_active: Flag indicating whether the tenant configuration is active.
        dunning_rules: JSON payload defining the tenant's retry and collection rules.
        updated_at: Timestamp of the last update to the tenant configuration.
    """

    __tablename__ = "tenant_configs"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    dunning_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ScheduledRetry(Base):
    """Scheduled retry entry for a tenant payment event.

    Attributes:
        id: UUID primary key for the scheduled retry record.
        tenant_id: Reference to the tenant owning the retry schedule.
        event_id: Unique identifier for the payment event.
        execute_at: Scheduled execution time for the retry.
        payment_data: JSON payload containing payment-related data.
        status: Current status of the retry schedule.
        created_at: Timestamp when the retry record was created.
    """

    __tablename__ = "scheduled_retries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(
        String, ForeignKey("tenant_configs.tenant_id"), index=True
    )
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    execute_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    payment_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(String, default="PENDING", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
