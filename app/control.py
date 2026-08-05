"""入库管线:片名/自然语言描述 → AI 识别 → 搜索 → 写 .strm + 库索引。
入口只有 Web(/ingest),不监听 Telegram 任何会话。"""
import time
from . import state, finder, strm, ai, follows, library


def _end(rec, status, msg):
    """收尾:记结果 + 落一行日志。成功路径也要打印 —— 不然日志页上只能看到
    搜索过程,最关键的「到底入没入库」反而查不到。"""
    rec["status"], rec["msg"] = status, msg
    print("[control] 《%s》%s" % (rec["show"], msg), flush=True)
    return rec


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
            return _end(rec, "no_result", "没搜到资源(搜索过程见上面几行)")
        if result.get("type") == "movie":
            yr = (" %d" % result["year"]) if result.get("year") else ""
            rec["show"] = result.get("title") or film
            if result.get("parts"):
                n, d = strm.write_movie_parts(rec["show"], result.get("year"),
                                              result["channel"], result["parts"])
                library.add_movie_parts(rec["show"], result.get("year"),
                                        result["channel"], result["parts"])
                msg = "电影%s 已入库(%d 段) → %s,去飞牛刷新即可" % (yr, n, d)
            else:
                n, d = strm.write_movie(rec["show"], result.get("year"), result["channel"],
                                        result["mid"], result.get("filename", ""))
                library.add_movie(rec["show"], result.get("year"), result["channel"],
                                  result["mid"], result.get("filename", ""))
                msg = "电影%s 已入库 → %s,去飞牛刷新即可" % (yr, d)
            rec["count"] = n
            return _end(rec, "done", msg)
        if not result.get("episodes"):
            return _end(rec, "no_result", "没搜到成套剧集")
        season = result.get("season", 1)
        n, d = strm.write_strm(film, result["channel"], result["episodes"], season)
        library.add_series(film, result["channel"], result["episodes"], season)
        follows.add(film, season)    # 剧集自动加入追更
        rec["count"] = n
        return _end(rec, "done", "已入库 %d 集(已加入追更) → %s,去飞牛刷新即可" % (n, d))
    except Exception as e:
        print("[control] ingest 出错", repr(e), flush=True)
        return _end(rec, "error", "出错: %r" % e)
