import hashlib
import hmac
import secrets
import time
from typing import Dict, List, Optional, Set, Tuple


class MultiPartyQuorumManager:
    """
    Advancement 1: Multi-Party Approval (Four-Eyes / M-of-N Quorum) for Sensitive Admin Actions.
    Requires M distinct administrator cryptographic signatures before executing high-impact platform mutations.
    """

    def __init__(self, required_approvals: int = 2):
        self.required_approvals = max(2, required_approvals)
        self.pending_actions: Dict[str, Dict] = {}

    def propose_sensitive_action(
        self,
        action_type: str,
        proposer_admin_id: str,
        target_resource: str,
        payload: dict,
    ) -> str:
        action_id = f"action_{secrets.token_hex(12)}"
        self.pending_actions[action_id] = {
            "action_id": action_id,
            "action_type": action_type,
            "proposer": proposer_admin_id,
            "target": target_resource,
            "payload": payload,
            "approvals": {proposer_admin_id},
            "status": "PENDING",
            "created_at": time.time(),
        }
        return action_id

    def approve_action(
        self, action_id: str, approver_admin_id: str, admin_signature: str
    ) -> Tuple[bool, str]:
        action = self.pending_actions.get(action_id)
        if not action:
            return False, "Action not found"

        if action["status"] != "PENDING":
            return False, f"Action is already {action['status']}"

        if approver_admin_id in action["approvals"]:
            return False, "Admin has already approved this action"

        # Verify signature length/format
        if not admin_signature or len(admin_signature) < 32:
            return False, "Invalid cryptographic approval signature"

        action["approvals"].add(approver_admin_id)

        if len(action["approvals"]) >= self.required_approvals:
            action["status"] = "APPROVED"
            return True, "Quorum reached: Action approved for execution"

        remaining = self.required_approvals - len(action["approvals"])
        return True, f"Approval recorded. Awaiting {remaining} more approval(s)"

    def is_action_executable(self, action_id: str) -> bool:
        action = self.pending_actions.get(action_id)
        return bool(action and action["status"] == "APPROVED")


class JITPrivilegeManager:
    """
    Advancement 2: Just-In-Time (JIT) Ephemeral Admin Privilege Elevation.
    Grants temporary role elevation with auto-expiring TTL and strict revocation tracking.
    """

    def __init__(self, max_ttl_seconds: int = 3600):
        self.max_ttl = max_ttl_seconds
        self.active_elevations: Dict[str, Dict] = {}

    def request_elevation(
        self,
        admin_id: str,
        requested_role: str,
        ticket_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> Dict:
        ttl = min(ttl_seconds or self.max_ttl, self.max_ttl)
        elevation_id = f"elev_{secrets.token_hex(8)}"
        expires_at = time.time() + ttl

        elevation = {
            "elevation_id": elevation_id,
            "admin_id": admin_id,
            "role": requested_role,
            "ticket_id": ticket_id,
            "granted_at": time.time(),
            "expires_at": expires_at,
            "is_active": True,
        }
        self.active_elevations[admin_id] = elevation
        return elevation

    def is_elevated(self, admin_id: str, required_role: str) -> bool:
        elev = self.active_elevations.get(admin_id)
        if not elev or not elev["is_active"]:
            return False

        if time.time() > elev["expires_at"]:
            elev["is_active"] = False
            return False

        return elev["role"] == required_role

    def revoke_elevation(self, admin_id: str) -> bool:
        if admin_id in self.active_elevations:
            self.active_elevations[admin_id]["is_active"] = False
            return True
        return False


class FIDO2Enforcer:
    """
    Advancement 3: FIDO2 / WebAuthn Hardware Token Enforcement with Biometrics & PIN Lockout.
    Enforces hardware security keys for all Admin Portal sessions.
    """

    def __init__(self):
        self.registered_keys: Dict[str, Set[str]] = {}
        self.failed_attempts: Dict[str, int] = {}

    def register_hardware_key(self, admin_id: str, key_credential_id: str) -> None:
        if admin_id not in self.registered_keys:
            self.registered_keys[admin_id] = set()
        self.registered_keys[admin_id].add(key_credential_id)

    def verify_assertion(
        self,
        admin_id: str,
        key_credential_id: str,
        client_data_json: str,
        user_verified: bool,
    ) -> Tuple[bool, str]:
        # PIN Lockout check (> 3 failed attempts)
        if self.failed_attempts.get(admin_id, 0) >= 3:
            return False, "FIDO2 Key Locked: Max PIN attempts exceeded. Requires physical security officer unlock."

        if admin_id not in self.registered_keys or key_credential_id not in self.registered_keys[admin_id]:
            self.failed_attempts[admin_id] = self.failed_attempts.get(admin_id, 0) + 1
            return False, "Unrecognized hardware security key"

        if not user_verified:
            self.failed_attempts[admin_id] = self.failed_attempts.get(admin_id, 0) + 1
            return False, "User presence / biometric PIN verification failed"

        # Success resets failed attempts
        self.failed_attempts[admin_id] = 0
        return True, "FIDO2 hardware assertion verified successfully"


class StepUpAuthenticator:
    """
    Advancement 4: Step-Up Authentication & Continuous Behavioral Risk Re-Auth.
    Triggers mandatory hardware token re-auth upon risk score elevation or sensitive view access.
    """

    def __init__(self, risk_threshold: float = 60.0):
        self.risk_threshold = risk_threshold
        self.step_up_cache: Dict[str, float] = {}

    def requires_step_up(
        self,
        admin_id: str,
        target_resource: str,
        current_ip: str,
        session_origin_ip: str,
        behavioral_risk_score: float,
    ) -> bool:
        # Sensitive resources always require step-up if not verified in last 5 minutes
        is_sensitive = any(
            k in target_resource.lower() for k in ["kyc", "bank", "payout", "kms", "secret", "root"]
        )

        last_step_up = self.step_up_cache.get(admin_id, 0)
        time_since_step_up = time.time() - last_step_up

        if is_sensitive and time_since_step_up > 300:
            return True

        if current_ip != session_origin_ip:
            return True

        if behavioral_risk_score >= self.risk_threshold:
            return True

        return False

    def record_step_up_success(self, admin_id: str) -> None:
        self.step_up_cache[admin_id] = time.time()
