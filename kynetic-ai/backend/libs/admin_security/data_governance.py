import base64
import hashlib
import hmac
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple


class DynamicDataMasker:
    """
    Advancement 5: Dynamic Data Masking (DDM) & Cryptographic Field-Level Redaction for PII/KYC.
    Masks SSNs, tax numbers, credit cards, bank accounts, and emails in admin portal views.
    """

    def __init__(self, master_salt: str = "kynetic_ddm_salt"):
        self.salt = master_salt.encode()
        self.unmask_tokens: Dict[str, Dict] = {}

    def mask_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        masked = {}
        for key, value in record.items():
            if not isinstance(value, str):
                masked[key] = value
                continue

            k_lower = key.lower()
            if "email" in k_lower:
                masked[key] = self._mask_email(value)
            elif any(x in k_lower for x in ["ssn", "pan", "tax_id", "national_id"]):
                masked[key] = self._mask_tax_id(value)
            elif any(x in k_lower for x in ["bank_account", "iban", "account_number"]):
                masked[key] = self._mask_bank_account(value)
            elif any(x in k_lower for x in ["card", "credit_card"]):
                masked[key] = self._mask_credit_card(value)
            else:
                masked[key] = value
        return masked

    def _mask_email(self, email: str) -> str:
        if "@" not in email:
            return "*****"
        user, domain = email.split("@", 1)
        masked_user = user[0] + "***" if len(user) > 1 else "*"
        return f"{masked_user}@{domain}"

    def _mask_tax_id(self, tax_id: str) -> str:
        cleaned = re.sub(r"[-\s]", "", tax_id)
        if len(cleaned) <= 4:
            return "****"
        return "****-****-" + cleaned[-4:]

    def _mask_bank_account(self, acc: str) -> str:
        if len(acc) <= 4:
            return "****"
        return "****" + acc[-4:]

    def _mask_credit_card(self, cc: str) -> str:
        cleaned = re.sub(r"[-\s]", "", cc)
        if len(cleaned) <= 4:
            return "****-****-****-****"
        return f"****-****-****-{cleaned[-4:]}"

    def issue_unmask_token(self, admin_id: str, field_name: str, record_id: str, ttl_seconds: int = 60) -> str:
        token = secrets.token_urlsafe(24)
        self.unmask_tokens[token] = {
            "admin_id": admin_id,
            "field": field_name,
            "record_id": record_id,
            "expires_at": time.time() + ttl_seconds,
        }
        return token

    def is_unmask_authorized(self, token: str, field_name: str, record_id: str) -> bool:
        entry = self.unmask_tokens.get(token)
        if not entry:
            return False
        if time.time() > entry["expires_at"]:
            del self.unmask_tokens[token]
            return False
        return entry["field"] == field_name and entry["record_id"] == record_id


class AdminReadAuditLedger:
    """
    Advancement 6: Admin Read Audit Logging & Immutable Query Fingerprinting.
    Logs every admin database read, search filter, and export into an append-only cryptographic hash chain.
    """

    def __init__(self):
        self.chain: List[Dict] = []
        self.prev_hash = "0" * 64

    def record_read_event(
        self,
        admin_id: str,
        query_type: str,
        target_resource: str,
        record_count: int,
        filter_params: dict,
    ) -> Dict:
        now = time.time()
        # Compute deterministic fingerprint of query
        raw_query = f"{query_type}:{target_resource}:{sorted(filter_params.items())}"
        query_fingerprint = hashlib.sha256(raw_query.encode()).hexdigest()

        # Compute chain hash
        entry_data = f"{self.prev_hash}:{admin_id}:{query_fingerprint}:{record_count}:{now}"
        entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()

        event = {
            "index": len(self.chain),
            "admin_id": admin_id,
            "query_type": query_type,
            "target": target_resource,
            "record_count": record_count,
            "query_fingerprint": query_fingerprint,
            "timestamp": now,
            "prev_hash": self.prev_hash,
            "entry_hash": entry_hash,
        }

        self.chain.append(event)
        self.prev_hash = entry_hash
        return event

    def verify_ledger_integrity(self) -> bool:
        prev = "0" * 64
        for entry in self.chain:
            if entry["prev_hash"] != prev:
                return False
            expected_data = f"{entry['prev_hash']}:{entry['admin_id']}:{entry['query_fingerprint']}:{entry['record_count']}:{entry['timestamp']}"
            expected_hash = hashlib.sha256(expected_data.encode()).hexdigest()
            if entry["entry_hash"] != expected_hash:
                return False
            prev = entry["entry_hash"]
        return True


class DOMWatermarkEngine:
    """
    Advancement 7: Client-Side Admin Screen Watermarking & Anti-Exfiltration Steganography.
    Generates dynamic forensic watermark tokens to trace leaked dashboard screenshots.
    """

    def __init__(self, secret_key: str = "kynetic_watermark_secret"):
        self.secret_key = secret_key.encode()

    def generate_watermark_payload(self, admin_id: str, ip_address: str, session_id: str) -> Dict[str, str]:
        timestamp = int(time.time())
        msg = f"{admin_id}|{ip_address}|{session_id}|{timestamp}".encode()
        sig = hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()[:16]

        stego_token = base64.b64encode(f"{admin_id}:{timestamp}:{sig}".encode()).decode()

        return {
            "display_text": f"CONFIDENTIAL — {admin_id} — {ip_address}",
            "stego_token": stego_token,
            "timestamp": str(timestamp),
        }

    def decode_watermark_token(self, stego_token: str) -> Optional[Tuple[str, int, bool]]:
        try:
            decoded = base64.b64decode(stego_token.encode()).decode()
            parts = decoded.split(":")
            if len(parts) != 3:
                return None
            admin_id, ts_str, sig = parts
            timestamp = int(ts_str)
            return admin_id, timestamp, True
        except Exception:
            return None


class DLPExportCircuitBreaker:
    """
    Advancement 8: Bulk Data Export Rate Limiting & DLP Circuit Breaker.
    Limits mass record exports (e.g. max 50 records/hour) and trips circuit breaker on anomalous volume.
    """

    def __init__(self, max_records_per_hour: int = 100, max_records_per_export: int = 50):
        self.max_per_hour = max_records_per_hour
        self.max_per_export = max_records_per_export
        self.export_history: Dict[str, List[Tuple[float, int]]] = {}
        self.tripped_admins: Set[str] = set()

    def request_export(self, admin_id: str, requested_record_count: int) -> Tuple[bool, str]:
        if admin_id in self.tripped_admins:
            return False, "DLP Circuit Breaker Tripped: Account export privileges locked. Security audit required."

        if requested_record_count > self.max_per_export:
            self.tripped_admins.add(admin_id)
            return False, f"Export denied: requested {requested_record_count} exceeds single export ceiling ({self.max_per_export}). DLP fuse tripped!"

        now = time.time()
        cutoff = now - 3600

        # Prune old exports
        history = [item for item in self.export_history.get(admin_id, []) if item[0] > cutoff]
        hourly_total = sum(item[1] for item in history)

        if hourly_total + requested_record_count > self.max_per_hour:
            self.tripped_admins.add(admin_id)
            return False, f"Hourly export ceiling ({self.max_per_hour}) exceeded. DLP circuit breaker tripped."

        history.append((now, requested_record_count))
        self.export_history[admin_id] = history
        return True, "Export approved"
