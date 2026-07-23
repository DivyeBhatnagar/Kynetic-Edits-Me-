"""
libs/db_models — Shared SQLAlchemy 2.0 async models + Alembic migration setup.

All Kynetic AI services share one PostgreSQL database.
Tables are logically owned per service domain but physically in one DB.
"""

# Import all models so Alembic autogenerate and relationship resolution work
from libs.db_models.models import User, RefreshToken, AuditLog                            # noqa: F401
from libs.db_models.host_models import Host, HostHardwareSpec, HostBenchmark, HostHeartbeat  # noqa: F401
from libs.db_models.marketplace_models import Listing, Wallet, WalletTransaction, StripeAccount  # noqa: F401
from libs.db_models.provisioning_models import Instance, SSHSession, SecureDeletionReceipt  # noqa: F401
from libs.db_models.security_models import DeviceFingerprint, TrustTier, SecurityEventLog, KillSwitchEvent  # noqa: F401
from libs.db_models.template_models import Template, TemplateWebUISession            # noqa: F401
from libs.db_models.billing_monitoring_models import Invoice, InvoiceSequence, Notification, NotificationPreference, SupportTicket  # noqa: F401
from libs.db_models.infrastructure_models import DeploymentRelease, EnvironmentConfig, ServiceHealthCheck  # noqa: F401 — Phase 12
from libs.db_models.observability_models import AlertEvent, IncidentRecord  # noqa: F401 — Phase 13
from libs.db_models.admin_models import AdminUser, TicketActivityLog, FraudReviewItem  # noqa: F401 — Phase 15
from libs.db_models.financial_models import LedgerEntry, Chargeback, TaxWithholding  # noqa: F401 — Phase 16
