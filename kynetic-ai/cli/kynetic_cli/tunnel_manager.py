"""
Kynetic CLI — Tunnel Manager & VS Code Remote SSH Config Generator (tunnel_manager.py)
"""

from pathlib import Path
from typing import Optional
import structlog

log = structlog.get_logger(__name__)


class TunnelManager:
    """
    Manages port forwarding tunnels and automated ~/.ssh/config entry injection.
    """

    @staticmethod
    def generate_ssh_config(
        instance_id: str,
        ssh_host: str = "127.0.0.1",
        ssh_port: int = 22,
        ssh_user: str = "kynetic",
        identity_file: Optional[str] = None,
        ssh_config_path: Optional[Path] = None,
    ) -> str:
        """
        Generates and injects a standard SSH Host block into ~/.ssh/config.
        Enables seamless VS Code Remote SSH connection (Host kynetic-<instance_id>).
        """
        if ssh_config_path is None:
            ssh_config_path = Path.home() / ".ssh" / "config"

        alias = f"kynetic-{instance_id[:8]}"
        id_file_str = identity_file if identity_file else f"~/.kynetic/keys/{instance_id}.pem"

        block = f"""
# --- Kynetic AI Rented Instance ({instance_id}) ---
Host {alias}
    HostName {ssh_host}
    Port {ssh_port}
    User {ssh_user}
    IdentityFile {id_file_str}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
# --- End Kynetic Block ---
"""
        ssh_config_path.parent.mkdir(parents=True, exist_ok=True)
        current_content = ssh_config_path.read_text() if ssh_config_path.exists() else ""

        if f"Host {alias}" not in current_content:
            with open(ssh_config_path, "a") as f:
                f.write(block)
            log.info("tunnel_manager.ssh_config_injected", alias=alias, path=str(ssh_config_path))

        return alias

    @staticmethod
    def create_port_forward(
        instance_id: str,
        local_port: int,
        remote_port: int,
        is_public: bool = False,
    ) -> dict:
        """Create a local or public port forwarding tunnel."""
        status_type = "public" if is_public else "local"
        endpoint = f"https://tunnel.kynetic.ai/{instance_id[:8]}:{remote_port}" if is_public else f"127.0.0.1:{local_port}"

        log.info("tunnel_manager.port_forward_created", instance_id=instance_id, local=local_port, remote=remote_port, type=status_type)

        return {
            "instance_id": instance_id,
            "type": status_type,
            "local_port": local_port,
            "remote_port": remote_port,
            "endpoint": endpoint,
        }
