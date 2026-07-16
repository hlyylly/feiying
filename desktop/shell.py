"""飞影 Windows 桌面版入口:同一套核心(app/),pywebview 窗口壳 + mpv 播放。
用法: python -m desktop.shell  (或 PyInstaller 打包后的 feiying.exe)

与 NAS 版的差异只有:
- 数据目录默认 %APPDATA%\\feiying(NAS 版是 /data)
- Web 只绑 127.0.0.1,显示在应用窗口里
- state.player 注入 mpv,媒体库页出现播放按钮(NAS 版该接口直接拒绝)
- 不依赖 .strm/外部媒体服务器
"""
import os
import socket
import sys
import threading
import time
import urllib.request


def _prep_env():
    """必须在 import app.* 之前:config.py 在 import 时读 FEIYING_DATA。"""
    if not os.environ.get("FEIYING_DATA"):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        os.environ["FEIYING_DATA"] = os.path.join(appdata, "feiying")
    base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
    xray = os.path.join(base, "bin", "xray.exe")
    if os.path.exists(xray):
        os.environ.setdefault("XRAY_BIN", xray)
    # 仓库根进 sys.path,保证 `python desktop/shell.py` 直跑也能 import app
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)


_prep_env()


def _setup_log():
    """打包后是 GUI 子系统,stdout 无处可去;全部落盘到数据目录 desktop.log。"""
    if not getattr(sys, "frozen", False):
        return
    os.makedirs(os.environ["FEIYING_DATA"], exist_ok=True)
    f = open(os.path.join(os.environ["FEIYING_DATA"], "desktop.log"),
             "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr = f


_setup_log()

WEB_PORT = int(os.environ.get("FEIYING_WEB_PORT", "0")) or None


def _pick_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _run_core(port):
    """后台线程:自有事件循环里跑 服务编排 + uvicorn(127.0.0.1)。"""
    import asyncio
    import uvicorn
    from app import state, config, service, follows
    from app.web.routes import create_app
    # PyInstaller 下 shell.py 是顶层入口脚本(无父包),不能用相对导入
    from desktop import player

    async def amain():
        state.cfg = config.Config.load()
        follows.load()
        state.player = player.play          # 桌面版标志:注入播放器
        print("[desktop] 数据目录:", config.DATA_DIR, flush=True)
        await service.boot()
        app = create_app()
        uconf = uvicorn.Config(app, host="127.0.0.1", port=port,
                               log_level="warning", loop="asyncio")
        await uvicorn.Server(uconf).serve()

    try:
        asyncio.run(amain())
    except Exception:
        import traceback
        traceback.print_exc()
        raise


def _wait_web(port, timeout=30):
    url = "http://127.0.0.1:%d/" % port
    for _ in range(timeout * 4):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.25)
    return False


def main():
    port = WEB_PORT or _pick_port()
    t = threading.Thread(target=_run_core, args=(port,), daemon=True)
    t.start()
    if not _wait_web(port):
        print("[desktop] 服务启动超时", flush=True)
        sys.exit(1)

    import webview
    webview.create_window("飞影", "http://127.0.0.1:%d/" % port,
                          width=900, height=760, min_size=(680, 520))
    webview.start()          # 阻塞到窗口关闭
    os._exit(0)              # 窗口关了就整体退出(后台线程随之结束)


if __name__ == "__main__":
    main()
