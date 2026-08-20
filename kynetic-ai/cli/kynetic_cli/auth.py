"""
OAuth2 Device Authorization Grant (RFC 8628) Auth Client.
"""

import time
import webbrowser
from typing import Any

import httpx
from rich.console import Console

from kynetic_cli.config import clear_credentials, load_credentials, save_credentials

console = Console()


class AuthClient:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")

    def request_device_code(self) -> dict[str, Any]:
        """Request a device and user code pair from the Auth Service."""
        url = f"{self.api_url}/v1/auth/device/code"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json={"client_id": "kynetic-cli"})
            if resp.status_code != 200 and resp.status_code != 201:
                # Fallback to unversioned path
                url = f"{self.api_url}/auth/device/code"
                resp = client.post(url, json={"client_id": "kynetic-cli"})

            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Device code request failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    def poll_device_token(self, device_code: str, interval: int = 5, expires_in: int = 600) -> dict[str, Any]:
        """Poll the token endpoint until the user authorizes the device code in browser."""
        url = f"{self.api_url}/v1/auth/device/token"
        start_time = time.time()

        with httpx.Client(timeout=15.0) as client:
            while time.time() - start_time < expires_in:
                time.sleep(interval)
                try:
                    resp = client.post(url, json={"device_code": device_code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                except httpx.RequestError:
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    creds = {
                        "access_token": data["access_token"],
                        "refresh_token": data["refresh_token"],
                        "token_type": data.get("token_type", "bearer"),
                        "email": data.get("user", {}).get("email", ""),
                        "user_id": data.get("user", {}).get("id", ""),
                    }
                    save_credentials(creds)
                    return data

                try:
                    err_json = resp.json()
                    detail = err_json.get("detail", {})
                    if isinstance(detail, dict):
                        err_type = detail.get("error")
                        if err_type == "authorization_pending":
                            continue
                        elif err_type == "expired_token":
                            raise RuntimeError("Device code expired. Please run 'kynetic login' again.")
                        elif err_type == "access_denied":
                            raise RuntimeError("Authorization request was denied by user.")
                except (ValueError, KeyError):
                    pass

        raise RuntimeError("Authorization timed out. Please run 'kynetic login' again.")

    def login(self) -> dict[str, Any]:
        """Execute full device-code authorization grant."""
        device_data = self.request_device_code()

        user_code = device_data["user_code"]
        verification_uri = device_data["verification_uri"]
        verification_uri_complete = device_data.get("verification_uri_complete", "")

        console.print("\n[bold cyan]========================================================[/bold cyan]")
        console.print("[bold white]  Kynetic CLI — Device Authentication[/bold white]")
        console.print("[bold cyan]========================================================[/bold cyan]")
        console.print(f"  1. Open your browser to:  [underline blue]{verification_uri}[/underline blue]")
        console.print(f"  2. Enter user code:       [bold green]{user_code}[/bold green]")
        console.print("[bold cyan]========================================================[/bold cyan]\n")

        target_url = verification_uri_complete if verification_uri_complete else verification_uri
        try:
            webbrowser.open(target_url)
        except Exception:
            pass

        console.print("[italic yellow]Waiting for browser authorization...[/italic yellow]")
        return self.poll_device_token(
            device_code=device_data["device_code"],
            interval=device_data.get("interval", 5),
            expires_in=device_data.get("expires_in", 600),
        )

    def logout(self) -> None:
        """Revoke server session and wipe local credentials."""
        creds = load_credentials()
        if creds and "access_token" in creds:
            url = f"{self.api_url}/v1/auth/logout"
            headers = {"Authorization": f"Bearer {creds['access_token']}"}
            try:
                with httpx.Client(timeout=5.0) as client:
                    client.post(url, headers=headers)
            except Exception:
                pass
        clear_credentials()

    def get_stored_token(self) -> str | None:
        """Retrieve stored access token from local credentials file."""
        creds = load_credentials()
        return creds.get("access_token") if creds else None

    def get_version(self) -> dict[str, Any]:
        """Fetch latest CLI version info from API."""
        url = f"{self.api_url}/v1/cli/version"
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch CLI version (HTTP {resp.status_code})")
            return resp.json()
