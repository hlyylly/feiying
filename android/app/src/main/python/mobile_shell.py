"""安卓端 python 入口(由 CoreService 调):同一套核心 app/,注入安卓播放桥。
CI 构建前会把仓库根的 app/ 拷到本目录(src/main/python/app/)。"""
import os
import traceback


def start(files_dir, native_lib_dir, player_bridge):
    os.environ.setdefault("FEIYING_DATA", os.path.join(files_dir, "feiying"))
    xray = os.path.join(native_lib_dir, "libxray.so")
    if os.path.exists(xray):
        os.environ.setdefault("XRAY_BIN", xray)

    log_dir = os.environ["FEIYING_DATA"]
    os.makedirs(log_dir, exist_ok=True)

    try:
        import asyncio
        import uvicorn
        from app import state, config, service, follows
        from app.web.routes import create_app

        state.cfg = config.Config.load()
        follows.load()
        state.player = lambda url, title="": player_bridge.play(url, title)
        print("[android] 数据目录:", config.DATA_DIR, flush=True)

        async def amain():
            await service.boot()
            uconf = uvicorn.Config(create_app(), host="127.0.0.1", port=8080,
                                   log_level="warning", loop="asyncio")
            await uvicorn.Server(uconf).serve()

        asyncio.run(amain())
    except Exception:
        # 崩溃写盘,logcat 之外还能从 App 数据目录捞到现场
        with open(os.path.join(log_dir, "android_crash.log"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        raise
