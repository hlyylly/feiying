"""进程内自愈看门狗:定时探健康,代理挂/client 不通就重启代理并重连(替代外部 cron)。"""
import asyncio
from . import state

INTERVAL = 900   # 15 分钟


async def loop():
    from . import service
    while True:
        await asyncio.sleep(INTERVAL)
        try:
            if state.proxy and state.cfg.vmess and not state.cfg.proxy_url \
                    and not state.proxy.is_running():
                print("[watchdog] xray 挂了,重启", flush=True)
                state.proxy.restart()
            ok = False
            if state.client:
                try:
                    await asyncio.wait_for(state.client.get_me(), timeout=20)
                    ok = True
                except Exception:
                    ok = False
            if state.cfg.session and not ok:
                print("[watchdog] client 不健康,重启代理+重连", flush=True)
                await service.recover()
            else:
                print("[watchdog] ok", flush=True)
        except Exception as e:
            print("[watchdog] loop err", repr(e), flush=True)
