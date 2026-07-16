# PyInstaller 打包配置: pyinstaller desktop/feiying.spec (在仓库根目录执行)
# 产物 dist/feiying/,把 xray.exe 和 mpv.exe 放进 dist/feiying/bin/ 后整目录 zip 发布。
import os

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPECPATH)) if os.path.basename(SPECPATH) else SPECPATH

a = Analysis(
    ["shell.py"],
    pathex=[".."],
    datas=[("../app/web/templates", "app/web/templates")],
    hiddenimports=["app", "desktop.player"],
    hookspath=[],
    excludes=["tkinter"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="feiying",
    console=False,           # 排查问题时改 True 看日志
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="feiying")
