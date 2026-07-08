"""入口:单事件循环里同时跑 uvicorn(Web) + telethon(client/收藏夹) + 缓存流服务 + 看门狗。"""
import asyncio
import os
import uvicorn
from . import state, config, service, follows
from .web.routes import create_app


async def amain():
    os.umask(0o022)          # 新写的 .strm 用 644/目录755,飞牛影视才读得到
    state.cfg = config.Config.load()
    follows.load()
    print("[main] 配置已加载, data=%s 追更%d部" % (config.DATA_DIR, len(state.follows)), flush=True)
    await service.boot()
    app = create_app()
    uconf = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info", loop="asyncio")
    server = uvicorn.Server(uconf)
    print("[main] Web 配置页: http://0.0.0.0:8080", flush=True)
    await server.serve()


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
