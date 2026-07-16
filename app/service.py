"""生命周期编排:起代理 → 连 client → (已登录则)起缓存流服务 + 注册收藏夹监听 + 看门狗。
Web 和 main 都通过它驱动。"""
import asyncio
from . import state, proxy as proxymod, tg, cache_server, control, watchdog, updater

_flags = {"watchdog": False, "updater": False}


def _use_xray():
    """外部代理(proxy_url)或直连模式都不起内置 xray。"""
    return bool(state.cfg.vmess and not state.cfg.proxy_url)


async def start_proxy():
    if state.proxy:
        state.proxy.stop()
    state.proxy = proxymod.XrayProxy(state.cfg.vmess if _use_xray() else "")
    state.proxy.start()


async def connect_client():
    if _use_xray() and not (state.proxy and state.proxy.is_running()):
        await start_proxy()
    await tg.connect()


async def start_services():
    """登录成功后:缓存流服务(端口只绑一次) + (重新)注册收藏夹监听 + 断点续缓。"""
    first = state.cache is None
    if first:
        state.cache = cache_server.CacheServer(state.cfg)
        await state.cache.start()
    control.register()
    if first:
        asyncio.create_task(state.cache.resume_incomplete())


async def _start_watchdog():
    if not _flags["watchdog"]:
        asyncio.create_task(watchdog.loop())
        _flags["watchdog"] = True
    if not _flags["updater"]:
        asyncio.create_task(updater.loop())
        _flags["updater"] = True


async def boot():
    """进程启动时调用。"""
    if _use_xray():
        await start_proxy()
    if state.cfg.session:
        try:
            await connect_client()
            if await tg.is_authorized():
                await start_services()
                print("[service] 已登录并启动全部服务", flush=True)
        except Exception as e:
            print("[service] boot 连接失败:", repr(e), flush=True)
    await _start_watchdog()


async def reload_after_config():
    """Web 保存配置后:重启代理并按需重连、起服务。"""
    await start_proxy()
    try:
        if state.cfg.session:
            await connect_client()
            if await tg.is_authorized():
                await start_services()
    except Exception as e:
        print("[service] reload 失败:", repr(e), flush=True)


async def recover():
    """看门狗自愈:重启代理 + 重连 + 重绑服务。"""
    if state.proxy:
        state.proxy.restart()
    await asyncio.sleep(3)
    try:
        await tg.connect()
        if await tg.is_authorized():
            await start_services()
    except Exception as e:
        print("[service] recover 失败:", repr(e), flush=True)


def status():
    return {
        "logged_in": bool(state.cfg.session),
        "phone": state.cfg.phone,
        "proxy_running": bool(state.proxy and state.proxy.is_running()),
        "proxy_mode": ("external" if state.cfg.proxy_url
                       else "xray" if state.cfg.vmess else "direct"),
        "vmess_set": bool(state.cfg.vmess),
        "source": state.cfg.source,
        "media_dir": state.cfg.media_dir,
        "stream_base": state.cfg.stream_base,
        "cache_gb": state.cache.cache_usage_gb() if state.cache else 0,
        "quota_gb": state.cfg.cache_quota_gb,
        "ingests": state.ingests[:10],
        "follows": state.follows,
        "update_interval_hours": state.cfg.update_interval_hours,
    }
