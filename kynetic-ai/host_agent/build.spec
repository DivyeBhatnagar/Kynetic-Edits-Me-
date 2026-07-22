"""
PyInstaller build spec for the Kynetic AI Host Agent.

Usage:
    pyinstaller host_agent/build.spec

Produces a single-file binary:
    dist/kynetic-agent          (Linux/macOS)
    dist/kynetic-agent.exe      (Windows)

The binary embeds:
- All Python dependencies (psutil, pynvml, GPUtil, httpx, redis, torch, structlog)
- The libs/common modules required by the agent
- The host_agent package
"""

import platform
import sys

block_cipher = None
is_windows = sys.platform == "win32"

a = Analysis(
    ["host_agent/main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "psutil",
        "pynvml",
        "GPUtil",
        "httpx",
        "redis",
        "structlog",
        "host_agent.hardware_detect",
        "host_agent.benchmark_runner",
        "host_agent.agent_client",
        "libs.common.logging",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],  # Exclude GUI libs not needed in headless mode
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="kynetic-agent" + (".exe" if is_windows else ""),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # Console app — shows onboarding wizard in terminal
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,  # Set to Apple Developer ID cert for macOS signing
    entitlements_file=None,
    # Windows: embed version info and icon
    icon="host_agent/assets/icon.ico" if is_windows else None,
)
