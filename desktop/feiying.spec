# PyInstaller 打包配置。在仓库根目录执行: .venv\Scripts\pyinstaller desktop\feiying.spec
# 产物 dist/feiying/;把 mpv.exe/xray.exe 放进 dist/feiying/bin/ 后整目录 zip 发布。
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)

hidden = (collect_submodules("app") + collect_submodules("desktop")
          # uvicorn 按字符串动态 import 的模块,静态分析收不到
          + ["uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
             "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
             "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
             "uvicorn.lifespan", "uvicorn.lifespan.on"])

a = Analysis(
    [os.path.join(SPECPATH, "shell.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "app", "web", "templates"), "app/web/templates")],
    hiddenimports=hidden,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="feiying",
    console=False,            # 排查问题时改 True 看日志
)
coll = COLLECT(exe, a.binaries, a.datas, name="feiying")
