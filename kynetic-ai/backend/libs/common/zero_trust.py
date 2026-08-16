"""
Zero Trust Policy Engine (PDP) — Part 8.

Evaluates 8 dimensions for every sensitive operation across Kynetic AI:
1. identity        — account_id, host_id, or service identity
2. authentication  — JWT validity, mTLS cert validity, attestation status
3. authorization   — RBAC role + ABAC conditions
4. attestation     — current Trust Score band (LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL)
5. policy          — applicable rule set for operation
6. risk            — current Risk Engine score for actor
7. resource        — instance_id, listing_id, host_id being acted on
8. operation       — specific action requested
"""

import enum
from dataclasses import dataclass
import structlog

log = structlog.get_logger(__name__)


class PolicyDecision(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"


@dataclass
class EvaluationContext:
    identity: str
    authentication_type: str            # 'jwt', 'mtls_attested', 'api_token'
    role: str                           # 'developer', 'host', 'admin', 'security'
    attestation_band: str               # 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK', 'CRITICAL'
    risk_score: float                   # 0 - 100
    resource_id: str
    resource_owner_id: str | None = None
    operation: str = "read"


class PolicyDecisionPoint:
    """
    Synchronous, lightweight Policy Decision Point (PDP) library.
    Called by backend microservices before executing sensitive actions.
    """

    @staticmethod
    def evaluate(ctx: EvaluationContext) -> tuple[PolicyDecision, str]:
        """
        Evaluates the 8 Zero Trust dimensions and returns (PolicyDecision, reason).
        """
        # 1. CRITICAL Risk Band / Attestation Failure -> DENY immediately
        if ctx.attestation_band == "CRITICAL" and ctx.role != "admin":
            log.warning("zero_trust.denied_critical_risk_band", identity=ctx.identity, op=ctx.operation)
            return PolicyDecision.DENY, "Operation denied: Host/Actor in CRITICAL risk band (attestation failure or severe compromise)."

        # 2. Risk score severe threshold (> 80.0 risk score = high threat)
        if ctx.risk_score >= 80.0 and ctx.role not in ("admin", "security"):
            log.warning("zero_trust.denied_high_risk_score", identity=ctx.identity, score=ctx.risk_score)
            return PolicyDecision.DENY, f"Operation denied: Actor risk score ({ctx.risk_score}) exceeds severe threshold."

        # 3. Ownership / Resource Isolation check for developers
        if ctx.role == "developer" and ctx.resource_owner_id and ctx.identity != ctx.resource_owner_id:
            log.warning("zero_trust.denied_cross_account_access", identity=ctx.identity, owner=ctx.resource_owner_id)
            return PolicyDecision.DENY, "Operation denied: Cross-account resource access is prohibited."

        # 4. Step-Up Authentication for sensitive administrative actions
        if ctx.operation in ("kill_switch_trigger", "secret_broker_rotate", "host_quarantine") and ctx.role not in ("admin", "security"):
            log.warning("zero_trust.denied_unauthorized_admin_op", identity=ctx.identity, op=ctx.operation)
            return PolicyDecision.DENY, f"Operation denied: {ctx.operation} requires admin/security role."

        log.debug("zero_trust.allowed", identity=ctx.identity, op=ctx.operation)
        return PolicyDecision.ALLOW, "Operation authorized by Zero Trust PDP."
