"""入库管线:片名/自然语言描述 → AI 识别 → 搜索 → 写 .strm + 库索引。
入口只有 Web(/ingest),不监听 Telegram 任何会话。"""
import time
from . import state, finder, strm, ai, follows, library


async def ingest(text):
    """text=片名/自然语言描述。返回记录 dict(msg 为给前端看的一句话结果)。"""
    rec = {"name": text, "show": text, "count": 0, "status": "running",
           "msg": "", "ts": int(time.time())}
    state.add_ingest(rec)
    try:
        film = await ai.normalize(text)
        rec["show"] = film
        result = await finder.find(film)
        if not result:
            rec["status"] = "no_result"
            rec["msg"] = "没搜到《%s》的资源" % film
            return rec
        if result.get("type") == "movie":
            yr = (" %d" % result["year"]) if result.get("year") else ""
            rec["show"] = result.get("title") or film
            if result.get("parts"):
                n, d = strm.write_movie_parts(rec["show"], result.get("year"),
                                              result["channel"], result["parts"])
                library.add_movie_parts(rec["show"], result.get("year"),
                                        result["channel"], result["parts"])
                rec["msg"] = "电影《%s%s》已入库(%d 段),去飞牛刷新即可" % (rec["show"], yr, n)
            else:
                n, d = strm.write_movie(rec["show"], result.get("year"), result["channel"],
                                        result["mid"], result.get("filename", ""))
                library.add_movie(rec["show"], result.get("year"), result["channel"],
                                  result["mid"], result.get("filename", ""))
                rec["msg"] = "电影《%s%s》已入库,去飞牛刷新即可" % (rec["show"], yr)
            rec["count"] = n
            rec["status"] = "done"
            return rec
        if not result.get("episodes"):
            rec["status"] = "no_result"
            rec["msg"] = "没搜到《%s》的成套剧集" % film
            return rec
        season = result.get("season", 1)
        n, d = strm.write_strm(film, result["channel"], result["episodes"], season)
        library.add_series(film, result["channel"], result["episodes"], season)
        follows.add(film, season)    # 剧集自动加入追更
        rec["count"] = n
        rec["status"] = "done"
        rec["msg"] = "剧集《%s》已入库 %d 集(已加入追更),去飞牛刷新即可" % (film, n)
        return rec
    except Exception as e:
        rec["status"] = "error"
        rec["msg"] = "出错: %r" % e
        print("[control] ingest err", repr(e), flush=True)
        return rec
