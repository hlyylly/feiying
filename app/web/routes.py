"""FastAPI:配置/状态页 + 登录(手机号→码) + 手动入库测试。"""
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from .. import state, service, tg, control, follows, updater, library
from ..config import DEFAULTS

TEMPLATES = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def create_app():
    app = FastAPI(title="飞影")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "index.html", {"cfg": state.cfg.public_dict(), "st": service.status()})

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
        kw = dict(source=source, vmess=vmess, proxy_url=proxy_url.strip(),
                  deepseek_base=deepseek_base,
                  deepseek_model=deepseek_model, media_dir=media_dir, movie_dir=movie_dir,
                  stream_base=stream_base,
                  stream_port=stream_port, cache_quota_gb=cache_quota_gb,
                  prefetch_workers=prefetch_workers, dl_sem=dl_sem, api_id=api_id, api_hash=api_hash)
        if deepseek_key and not deepseek_key.endswith("..."):   # 打码占位不覆盖
            kw["deepseek_key"] = deepseek_key
        state.cfg.set(**kw)
        await service.reload_after_config()
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
        return JSONResponse({"ok": True, "msg": "已触发追更检查(后台进行,有更新会发到收藏夹)"})

    @app.post("/ingest")
    async def do_ingest(name: str = Form(...)):
        if not await tg.is_authorized():
            return JSONResponse({"ok": False, "msg": "未登录"})
        rec = await control.ingest(name)
        return JSONResponse({"ok": rec["status"] == "done", **rec})

    @app.get("/library", response_class=HTMLResponse)
    async def library_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "library.html",
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
