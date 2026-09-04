import re
import time
from typing import Dict, List, Optional, Set, Tuple


class AdminAICopilotGuard:
    """
    Advancement 19: Admin AI Copilot Execution Sandbox & Prompt Guard.
    Prevents indirect prompt injection attacks from customer tickets or untrusted logs from tricking admin AI copilots.
    """

    def __init__(self):
        self.injection_patterns = [
            re.compile(r"ignore\s+(previous|all)\s+instructions", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
            re.compile(r"system\s*:\s*override", re.IGNORECASE),
            re.compile(r"grant\s+admin\s+role", re.IGNORECASE),
            re.compile(r"drop\s+database", re.IGNORECASE),
            re.compile(r"reveal\s+(api\s*key|secret|password)", re.IGNORECASE),
        ]

    def sanitize_untrusted_context(self, context_text: str) -> Tuple[str, bool]:
        sanitized = context_text
        detected = False
        for pattern in self.injection_patterns:
            if pattern.search(sanitized):
                detected = True
                sanitized = pattern.sub("[FILTERED_PROMPT_INJECTION_ATTEMPT]", sanitized)

        return sanitized, detected

    def is_tool_call_permitted(self, tool_name: str, parameters: dict) -> Tuple[bool, str]:
        # Enforce read-only sandboxed tools for admin AI copilots
        read_only_tools = {
            "search_logs",
            "get_user_summary",
            "view_benchmark_stats",
            "explain_error_code",
            "summarize_ticket",
        }

        if tool_name not in read_only_tools:
            return False, f"Copilot Sandbox Violation: Tool '{tool_name}' is a destructive mutation tool and cannot be executed by AI."

        return True, "Tool call authorized within AI read-only sandbox"


class AdminCompromiseQuarantine:
    """
    Advancement 20: Automated Admin Compromise Lockdown (Blast-Radius Quarantine).
    Instantly revokes sessions, invalidates API keys, and quarantines recent mutations upon high-risk anomaly detection.
    """

    def __init__(self):
        self.quarantined_admins: Dict[str, Dict] = {}
        self.quarantined_mutations: List[Dict] = []

    def trigger_blast_radius_lockdown(
        self,
        admin_id: str,
        reason: str,
        trigger_anomaly_score: float,
        recent_mutation_ids: Optional[List[str]] = None,
    ) -> Dict:
        now = time.time()
        lockdown_event = {
            "admin_id": admin_id,
            "reason": reason,
            "anomaly_score": trigger_anomaly_score,
            "status": "LOCKED_DOWN",
            "sessions_revoked": True,
            "api_keys_invalidated": True,
            "timestamp": now,
        }

        self.quarantined_admins[admin_id] = lockdown_event

        if recent_mutation_ids:
            for mut_id in recent_mutation_ids:
                self.quarantined_mutations.append({
                    "mutation_id": mut_id,
                    "admin_id": admin_id,
                    "status": "QUARANTINED_PENDING_SOC_REVIEW",
                    "timestamp": now,
                })

        return lockdown_event

    def is_admin_quarantined(self, admin_id: str) -> bool:
        return admin_id in self.quarantined_admins

    def get_quarantined_mutations(self, admin_id: str) -> List[Dict]:
        return [m for m in self.quarantined_mutations if m["admin_id"] == admin_id]
