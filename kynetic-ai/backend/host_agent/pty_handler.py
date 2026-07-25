"""
Host Agent — PTY Shell Handler (pty_handler.py)

Spawns interactive pty shell sessions inside host microVMs / Docker containers
and bridges stdout/stdin streams over reverse tunnel WebSockets.
"""

import os
import pty
import subprocess
import structlog

log = structlog.get_logger(__name__)


class PTYShellSession:
    """
    Manages interactive PTY process for one instance session.
    """

    def __init__(self, instance_id: str, command: str = "/bin/bash"):
        self.instance_id = instance_id
        self.command = command
        self.master_fd = None
        self.slave_fd = None
        self.process = None

    def start(self) -> None:
        """Spawn pseudo-terminal process."""
        try:
            self.master_fd, self.slave_fd = pty.openpty()
            self.process = subprocess.Popen(
                self.command,
                shell=True,
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                close_fds=True,
                preexec_fn=os.setsid,
            )
            log.info("pty_session.started", instance_id=self.instance_id, pid=self.process.pid)
        except Exception as exc:
            log.error("pty_session.start_failed", instance_id=self.instance_id, error=str(exc))

    def write_input(self, data: bytes) -> None:
        """Write stdin input bytes to PTY process."""
        if self.master_fd:
            os.write(self.master_fd, data)

    def read_output(self, max_bytes: int = 4096) -> bytes:
        """Read stdout/stderr output bytes from PTY process."""
        if self.master_fd:
            try:
                return os.read(self.master_fd, max_bytes)
            except OSError:
                pass
        return b""

    def terminate(self) -> None:
        """Kill PTY process and close file descriptors."""
        if self.process:
            self.process.terminate()
        if self.master_fd:
            os.close(self.master_fd)
        if self.slave_fd:
            os.close(self.slave_fd)
        log.info("pty_session.terminated", instance_id=self.instance_id)
