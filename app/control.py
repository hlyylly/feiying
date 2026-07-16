"""收藏夹(Saved Messages)监听:用户发片名 → 入库管线 → 回编同一条消息显示进度。"""
import time
from telethon import events
from . import state, finder, strm, ai, follows, library

PROGRESS_MARKS = ("🔍", "✅", "❌", "⏳")
_handler = None


def register():
    """在当前 state.client 上(重新)注册收藏夹监听,幂等。"""
    global _handler
    c = state.client
    if _handler is not None:
        try:
            c.remove_event_handler(_handler)
        except Exception:
            pass

    @c.on(events.NewMessage(chats="me"))
    async def handler(ev):
        txt = (ev.raw_text or "").strip()
        if not txt or txt.startswith(PROGRESS_MARKS):
            return
        await ingest(txt, ev.message)

    _handler = handler


async def ingest(text, msg=None):
    """text=片名/自然语言描述。msg 若给则编辑它展示进度。返回记录 dict。"""
    async def show(s):
        if msg is not None:
            try:
                await msg.edit(s)
            except Exception:
                pass

    rec = {"name": text, "show": text, "count": 0, "status": "running", "ts": int(time.time())}
    state.add_ingest(rec)
    try:
        await show("🔍 正在识别片名…")
        film = await ai.normalize(text)
        rec["show"] = film
        await show("🔍 搜索《%s》…" % film)
        result = await finder.find(film)
        if not result:
            rec["status"] = "no_result"
            await show("❌ 没搜到《%s》的资源" % film)
            return rec
        if result.get("type") == "movie":
            yr = (" %d" % result["year"]) if result.get("year") else ""
            rec["show"] = result.get("title") or film
            if result.get("parts"):
                n, d = strm.write_movie_parts(rec["show"], result.get("year"),
                                              result["channel"], result["parts"])
                library.add_movie_parts(rec["show"], result.get("year"),
                                        result["channel"], result["parts"])
                await show("🎬 电影《%s%s》已入库(%d 段),去飞牛刷新即可" % (rec["show"], yr, n))
            else:
                n, d = strm.write_movie(rec["show"], result.get("year"), result["channel"],
                                        result["mid"], result.get("filename", ""))
                library.add_movie(rec["show"], result.get("year"), result["channel"],
                                  result["mid"], result.get("filename", ""))
                await show("🎬 电影《%s%s》已入库,去飞牛刷新即可" % (rec["show"], yr))
            rec["count"] = n
            rec["status"] = "done"
            return rec
        if not result.get("episodes"):
            rec["status"] = "no_result"
            await show("❌ 没搜到《%s》的成套剧集" % film)
            return rec
        season = result.get("season", 1)
        n, d = strm.write_strm(film, result["channel"], result["episodes"], season)
        library.add_series(film, result["channel"], result["episodes"], season)
        follows.add(film, season)    # 剧集自动加入追更
        rec["count"] = n
        rec["status"] = "done"
        await show("✅ 剧集《%s》已入库 %d 集(已加入追更),去飞牛刷新即可" % (film, n))
        return rec
    except Exception as e:
        rec["status"] = "error"
        await show("❌ 出错: %r" % e)
        print("[control] ingest err", repr(e), flush=True)
        return rec
