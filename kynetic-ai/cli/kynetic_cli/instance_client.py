"""
Kynetic CLI — Instance HTTP Client (instance_client.py)
"""

from typing import Any, Dict, List, Optional
import httpx
from kynetic_cli.auth import AuthClient


class InstanceClient:

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip("/")
        self.auth_client = AuthClient(self.api_url)

    def _headers(self) -> Dict[str, str]:
        token = self.auth_client.get_stored_token()
        if not token:
            raise RuntimeError("Not authenticated. Please run 'kynetic login' first.")
        return {"Authorization": f"Bearer {token}"}

    def launch(self, listing_id: str, template_id: Optional[str] = None, hours: float = 1.0) -> Dict[str, Any]:
        """Launch instance (POST /v1/instances)."""
        payload = {
            "listing_id": listing_id,
            "template_id": template_id,
            "requested_hours": str(hours),
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{self.api_url}/v1/instances", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                raise RuntimeError(f"Launch failed ({resp.status_code}): {resp.text}")
            return resp.json()

    def list_instances(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List developer instances (GET /v1/instances)."""
        params = {}
        if status:
            params["status_filter"] = status
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.api_url}/v1/instances", params=params, headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"List failed ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data.get("items", [])

    def get_instance(self, instance_id: str) -> Dict[str, Any]:
        """Get instance detail (GET /v1/instances/{id})."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.api_url}/v1/instances/{instance_id}", headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"Get instance failed ({resp.status_code}): {resp.text}")
            return resp.json()

    def stop_instance(self, instance_id: str) -> Dict[str, Any]:
        """Stop instance (POST /v1/instances/{id}/stop)."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.api_url}/v1/instances/{instance_id}/stop", json={}, headers=self._headers())
            if resp.status_code not in (200, 202):
                raise RuntimeError(f"Stop failed ({resp.status_code}): {resp.text}")
            return resp.json()

    def terminate_instance(self, instance_id: str) -> Dict[str, Any]:
        """Terminate instance (POST /v1/instances/{id}/terminate)."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.api_url}/v1/instances/{instance_id}/terminate", json={}, headers=self._headers())
            if resp.status_code not in (200, 202):
                raise RuntimeError(f"Terminate failed ({resp.status_code}): {resp.text}")
            return resp.json()

    def get_deletion_receipt(self, instance_id: str) -> Dict[str, Any]:
        """Get deletion receipt (GET /v1/instances/{id}/deletion-receipt)."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.api_url}/v1/instances/{instance_id}/deletion-receipt", headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"Receipt fetch failed ({resp.status_code}): {resp.text}")
            return resp.json()
