# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for map_compositor.

Build:
    pyinstaller map_compositor.spec --clean

Produces a one-file Windows executable at ``dist/map_compositor.exe``.
"""
import os
import pythontk
import uitk

# Path roots so we can ship the workspace-source packages instead of any
# stale PyPI install. The build environment has pythontk + uitk + Pillow +
# qtpy + PySide6 importable via .venv; PyInstaller's analysis walks from
# there and pulls everything in.
PYTHONTK_ROOT = os.path.dirname(pythontk.__file__)
UITK_ROOT = os.path.dirname(uitk.__file__)

block_cipher = None

a = Analysis(
    ["map_compositor/_map_compositor.py"],
    pathex=[],
    binaries=[],
    datas=[
        # The Switchboard loader reads map_compositor.ui at runtime relative
        # to the script's directory; bundle it next to the entry point.
        ("map_compositor/map_compositor.ui", "map_compositor"),
        # uitk's widgets are discovered by Switchboard via filesystem scan;
        # ship the whole package so DEFAULT_INCLUDE / registry resolution
        # finds the .ui, theme, and icon resources.
        (UITK_ROOT, "uitk"),
        # pythontk ships data files (img registry, etc.) discovered via
        # bootstrap_package; bundle the package tree.
        (PYTHONTK_ROOT, "pythontk"),
    ],
    hiddenimports=[
        # Switchboard / LoggingMixin discover modules dynamically;
        # PyInstaller's static analysis misses these.
        "pythontk.core_utils.logging_mixin",
        "pythontk.core_utils.module_resolver",
        "pythontk.img_utils.map_factory",
        "pythontk.img_utils.map_registry",
        "pythontk.img_utils._img_utils",
        "uitk.widgets.header",
        "uitk.widgets.footer",
        "uitk.widgets.menu",
        "uitk.widgets.lineEdit",
        "uitk.widgets.progressBar",
        "uitk.widgets.optionBox.options.recent_values",
        "qtpy",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim the binary — none of these are needed at runtime.
        "tkinter",
        "matplotlib",
        "pytest",
        "unittest",
        "pydoc",
    ],
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
    name="map_compositor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # UPX hurts startup time + AV false-positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,    # GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
