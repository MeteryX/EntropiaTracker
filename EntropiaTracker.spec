# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec für die reine Desktop-Version (PySide6)
Kein lokaler Server.
"""
from pathlib import Path

block_cipher = None
BASE = Path(SPECPATH)

a = Analysis(
    ['desktop.py'],
    pathex=[str(BASE)],
    binaries=[],
    datas=[d for d in [
        (str(BASE / 'entropia_tracker.db'), '.') if (BASE / 'entropia_tracker.db').exists() else None,
    ] if d is not None],
    hiddenimports=[
        'sqlalchemy.dialects.sqlite',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='EntropiaTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',
)
