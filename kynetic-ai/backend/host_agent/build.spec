"""
PyInstaller build spec for the Kynetic AI Host Agent.

Phase 1 Optimization:
  - torch and redis are NO LONGER bundled (removed from requirements.txt).
    This is the single largest size reduction: ~1.8–2.2 GB saved.
  - Extended excludes list removes unused Python stdlib modules that PyInstaller
    otherwise bundles (~20–40 MB additional savings).
  - strip=True enables symbol stripping on Linux/macOS (additional ~15 MB saved).
  - UPX compression is already enabled (upx=True).

Usage:
    pyinstaller host_agent/build.spec

Produces a single-file binary:
    dist/kynetic-agent          (Linux/macOS, target: ~35–55 MB)
    dist/kynetic-agent.exe      (Windows)

The binary embeds:
  - Core runtime deps: psutil, pynvml, GPUtil, httpx, structlog
  - The libs/common modules required by the agent
  - The host_agent package
  - ctypes bindings to host libcuda.so / libnvidia-ml.so (loaded at runtime, NOT bundled)
"""

import sys

block_cipher = None
is_windows = sys.platform == "win32"

# ── Unused stdlib modules to exclude ──────────────────────────────────────────
# Removing these saves ~20–40 MB from the final binary.
_STDLIB_EXCLUDES = [
    # GUI / display
    "tkinter", "_tkinter", "matplotlib", "PIL",
    # Database (not used by host agent)
    "sqlite3", "_sqlite3",
    # Testing / development
    "unittest", "doctest", "pdb", "profile", "cProfile", "timeit", "trace",
    # Documentation generation
    "pydoc", "pydoc_data",
    # Email / network protocols (agent uses httpx only)
    "email", "html", "http.server", "ftplib", "poplib", "imaplib",
    "telnetlib", "smtplib", "smtpd", "nntplib", "xmlrpc",
    # CGI / web server utilities
    "cgi", "cgitb", "wsgiref",
    # Legacy distutils (not needed at runtime)
    "distutils", "pkg_resources._vendor.jaraco",
    # XML processing (agent doesn't parse XML)
    "xml.etree", "xml.dom", "xml.sax",
    # Audio / multimedia
    "wave", "sunau", "aifc", "audioop", "ossaudiodev",
    # Curses
    "curses", "_curses",
    # Unused crypto / compression (httpx brings its own)
    "bz2", "lzma",
    # Misc
    "turtle", "turtledemo", "antigravity", "this",
]

a = Analysis(
    ["host_agent/main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Core agent dependencies (torch and redis intentionally absent)
        "psutil",
        "pynvml",
        "GPUtil",
        "httpx",
        "structlog",
        # Host agent modules
        "host_agent.hardware_detect",
        "host_agent.benchmark_runner",
        "host_agent.agent_client",
        "host_agent.command_listener",
        "host_agent.idempotency_store",
        "libs.common.logging",
        # ctypes is stdlib and auto-included, but explicit for clarity
        "ctypes",
        "ctypes.util",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_STDLIB_EXCLUDES,
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
    strip=True,          # Phase 1: strip debug symbols (saves ~10–20 MB on Linux/macOS)
    upx=True,            # UPX compression (saves additional ~30–40%)
    upx_exclude=[
        # Do not compress pynvml — it uses ctypes dlopen and compression breaks it
        "pynvml",
    ],
    runtime_tmpdir=None,
    console=True,        # Console app — shows onboarding wizard in terminal
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,  # Set to Apple Developer ID cert for macOS signing
    entitlements_file=None,
    # Windows: embed version info and icon
    icon="host_agent/assets/icon.ico" if is_windows else None,
)
