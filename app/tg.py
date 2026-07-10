"""telethon 用户 client 管理 + 登录流程。全局单 client(单账号,复用现有 signin/send 逻辑)。"""
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from . import state, proxy as proxymod


def make_client(cfg):
    return TelegramClient(
        StringSession(cfg.session or None), cfg.api_id, cfg.api_hash,
        proxy=proxymod.telethon_proxy(cfg))


async def connect():
    """(重新)建立并连接全局 client。需先起代理。"""
    if state.client is not None:
        try:
            await state.client.disconnect()
        except Exception:
            pass
    c = make_client(state.cfg)
    await c.connect()
    state.client = c
    return c


async def is_authorized():
    return state.client is not None and await state.client.is_user_authorized()


async def send_code(phone):
    sent = await state.client.send_code_request(phone)
    state.login_state = {"phone": phone, "phone_code_hash": sent.phone_code_hash}
    return sent


async def sign_in(code, password=None):
    """返回 'NEED_2FA' 需要二步密码,否则返回登录用户名。"""
    c, ls = state.client, state.login_state
    try:
        await c.sign_in(ls["phone"], code, phone_code_hash=ls["phone_code_hash"])
    except SessionPasswordNeededError:
        if not password:
            return "NEED_2FA"
        await c.sign_in(password=password)
    me = await c.get_me()
    state.cfg.set(session=c.session.save(), phone=ls["phone"])
    return me.first_name
