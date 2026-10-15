# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('D:/工作台/机器狗/Lite3控制脚本/desktop/profiles.json', '.'), ('D:/工作台/机器狗/Lite3控制脚本/desktop/known_hosts', '.'), ('D:/工作台/机器狗/Lite3控制脚本/desktop/rover/remote_reader.py', 'rover')]
binaries = []
hiddenimports = ['mcp.server']
datas += collect_data_files('mcp')
hiddenimports += collect_submodules('uvicorn')
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mcp_types')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:/工作台/机器狗/Lite3控制脚本/desktop/main.py'],
    pathex=['D:/工作台/机器狗/Lite3控制脚本/desktop/vendor'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['mcp.cli', 'matplotlib', 'pandas', 'scipy', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RoverDesk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:/工作台/机器狗/Lite3控制脚本/desktop/rover.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RoverDesk',
)
