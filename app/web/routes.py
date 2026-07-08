"""FastAPI:配置/状态页 + 登录(手机号→码) + 手动入库测试。"""
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from .. import state, service, tg, control, follows, updater
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
        source: str = Form(""), vmess: str = Form(""), deepseek_key: str = Form(""),
        deepseek_base: str = Form("https://api.deepseek.com"),
        deepseek_model: str = Form("deepseek-chat"),
        media_dir: str = Form("/media/tv"), movie_dir: str = Form("/media/movies"),
        stream_base: str = Form(""),
        stream_port: int = Form(8890), cache_quota_gb: int = Form(18),
        prefetch_workers: int = Form(4), dl_sem: int = Form(5),
        api_id: int = Form(DEFAULTS["api_id"]), api_hash: str = Form(DEFAULTS["api_hash"]),
    ):
        kw = dict(source=source, vmess=vmess, deepseek_base=deepseek_base,
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

    return app
