"""FastAPI:配置/状态页 + 登录(手机号→码) + 手动入库测试。"""
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from .. import state, service, tg, control, follows, updater, library, logbuf, selfcheck
from ..config import DEFAULTS, normalize_stream_base

TEMPLATES = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def _lan_ip(request=None):
    """取「别人能访问到本机」的地址。
    优先用浏览器访问本页所用的 host —— 用户既然能打开配置页,那个地址就一定是通的。
    容器里 socket 探测只会探到 Docker 内网 IP(如 172.20.0.2),照着填 stream_base
    飞牛和播放器都到不了,所以只在拿不到 host 时才退回去用它。"""
    host = (request.url.hostname if request is not None else None) or ""
    if host and host not in ("127.0.0.1", "localhost", "::1"):
        return host
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.5.5.5", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "本机IP"


def _render(request, name, ctx):
    """兼容新老 starlette:1.x 只认 (request, name, ctx),0.2x(安卓端)只认 (name, {request 在 ctx 里})。"""
    try:
        return TEMPLATES.TemplateResponse(request, name, ctx)
    except (TypeError, ValueError):
        return TEMPLATES.TemplateResponse(name, dict(request=request, **ctx))


def create_app():
    logbuf.install()          # desktop/安卓不走 app.main,在这兜底
    if state.cfg is not None:
        try:
            selfcheck.run_once()
        except Exception as e:
            print("[自检] 跳过:", repr(e), flush=True)
    app = FastAPI(title="飞影")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, err: str = ""):
        return _render(request, "index.html",
                       {"cfg": state.cfg.public_dict(), "st": service.status(),
                        "lan_ip": _lan_ip(request), "err": err,
                        "tv_host": selfcheck.host_hint(state.cfg.media_dir, "FEIYING_HOST_TV"),
                        "movie_host": selfcheck.host_hint(state.cfg.movie_dir, "FEIYING_HOST_MOVIES")})

    @app.post("/save")
    async def save(
        source: str = Form(""), vmess: str = Form(""), proxy_url: str = Form(""),
        deepseek_key: str = Form(""),
        deepseek_base: str = Form("https://api.deepseek.com"),
        deepseek_model: str = Form("deepseek-chat"),
        media_dir: str = Form("/media/tv"), movie_dir: str = Form("/media/movies"),
        stream_base: str = Form(""),
        stream_port: int = Form(8890), cache_quota_gb: int = Form(18),
        prefetch_workers: int = Form(4), dl_sem: int = Form(5),
        api_id: int = Form(DEFAULTS["api_id"]), api_hash: str = Form(DEFAULTS["api_hash"]),
    ):
        stream_base, _err = normalize_stream_base(stream_base)   # 只填 IP:端口自动补 http://
        # 粘贴 key/地址常带首尾空白,带进 HTTP header 会直接 LocalProtocolError
        kw = dict(source=source.strip(), vmess=vmess.strip(), proxy_url=proxy_url.strip(),
                  deepseek_base=deepseek_base.strip(),
                  deepseek_model=deepseek_model.strip(),
                  media_dir=media_dir.strip(), movie_dir=movie_dir.strip(),
                  stream_base=stream_base,
                  stream_port=stream_port, cache_quota_gb=cache_quota_gb,
                  prefetch_workers=prefetch_workers, dl_sem=dl_sem,
                  api_id=api_id, api_hash=api_hash.strip())
        deepseek_key = deepseek_key.strip()
        if deepseek_key and not deepseek_key.endswith("..."):   # 打码占位不覆盖
            kw["deepseek_key"] = deepseek_key
        state.cfg.set(**kw)
        selfcheck.run()          # 配置变了,自检结论跟着更新
        await service.reload_after_config()
        if _err and not stream_base:      # 填的东西没法用(如填了目录),回首页说清楚原因
            from urllib.parse import quote
            return RedirectResponse("/?err=" + quote(_err), status_code=303)
        return RedirectResponse("/", status_code=303)

    @app.post("/login/send")
    async def login_send(phone: str = Form(...)):
        state.cfg.set(phone=phone)
        try:
            await service.connect_client()
            await tg.send_code(phone)
            return JSONResponse({"ok": True, "msg": "验证码已发到你的 Telegram App"})
        except Exception as e:
            return JSONResponse({"ok": False, "msg": repr(e)})

    @app.post("/login/verify")
    async def login_verify(code: str = Form(...), password: str = Form("")):
        try:
            r = await tg.sign_in(code, password or None)
            if r == "NEED_2FA":
                return JSONResponse({"ok": False, "need_2fa": True, "msg": "该号开了两步验证,请填密码"})
            await service.start_services()
            return JSONResponse({"ok": True, "msg": "登录成功: " + str(r)})
        except Exception as e:
            return JSONResponse({"ok": False, "msg": repr(e)})

    @app.get("/status.json")
    async def status_json():
        return JSONResponse(service.status())

    @app.post("/unfollow")
    async def unfollow(show: str = Form(...)):
        follows.remove(show)
        return JSONResponse({"ok": True})

    @app.post("/check_now")
    async def check_now():
        if not await tg.is_authorized():
            return JSONResponse({"ok": False, "msg": "未登录"})
        import asyncio
        asyncio.create_task(updater.check_all())
        return JSONResponse({"ok": True, "msg": "已触发追更检查(后台进行,有更新会出现在下方入库记录)"})

    @app.post("/ingest")
    async def do_ingest(name: str = Form(...)):
        if not await tg.is_authorized():
            return JSONResponse({"ok": False, "msg": "未登录"})
        rec = await control.ingest(name)
        return JSONResponse({"ok": rec["status"] == "done", **rec})

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        """fpk/安卓装的进不去 docker logs,日志得能在网页上看。"""
        return _render(request, "logs.html", {"st": service.status()})

    @app.get("/logs.json")
    async def logs_json(n: int = 400):
        return JSONResponse({"lines": logbuf.tail(max(1, min(n, 800)))})

    @app.get("/tv", response_class=HTMLResponse)
    async def tv_page(request: Request):
        """电视大屏页:只留 搜索+媒体库,大焦点遥控导航;完整配置走局域网网页。"""
        return _render(request, "tv.html",
                       {"items": library.items(), "st": service.status(),
                        "lan_ip": _lan_ip(request), "web_port": request.url.port or 80})

    @app.get("/library", response_class=HTMLResponse)
    async def library_page(request: Request):
        return _render(request, "library.html",
                       {"items": library.items(), "desktop": state.player is not None,
                        "stream_base": (state.cfg.stream_base or
                                        "http://127.0.0.1:%d" % state.cfg.stream_port).rstrip("/")})

    @app.post("/library/remove")
    async def library_remove(id: str = Form(...)):
        library.remove(id)
        return JSONResponse({"ok": True})

    @app.post("/play")
    async def play(id: str = Form(...), ep: int = Form(0)):
        """desktop 版专用:调内嵌播放器播缓存流。NAS 版没有注入 player,直接拒绝。"""
        if state.player is None:
            return JSONResponse({"ok": False, "msg": "仅桌面版支持播放"})
        it = next((x for x in library.items() if x["id"] == id), None)
        if not it:
            return JSONResponse({"ok": False, "msg": "库里没有这条"})
        base = "http://127.0.0.1:%d" % state.cfg.stream_port
        if it["type"] == "movie":
            ext = os.path.splitext(it.get("filename", "") or "")[1] or ".mp4"
            url = "%s/%s/%d/movie%s" % (base, it["channel"], it["mid"], ext)
            title = it["title"]
        else:
            e = next((x for x in it["episodes"] if x["ep"] == ep), None)
            if not e:
                return JSONResponse({"ok": False, "msg": "没有第 %d 集" % ep})
            ext = os.path.splitext(e.get("filename", "") or "")[1] or ".mp4"
            url = "%s/%s/%d/ep%02d%s" % (base, it["channel"], e["mid"], ep, ext)
            title = "%s E%02d" % (it["title"], ep)
        try:
            state.player(url, title)
            return JSONResponse({"ok": True, "msg": "已调起播放器"})
        except Exception as e:
            return JSONResponse({"ok": False, "msg": repr(e)})

    return app
