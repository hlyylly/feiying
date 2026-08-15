"""追更:定时对追更列表里的剧重新发现,只补新增集,结果记进 Web 首页的入库记录。"""
import asyncio, glob, os, re, time
from . import state, finder, strm, follows, library, prepare


def existing_eps(show, season=1):
    d = os.path.join(state.cfg.media_dir, show, "Season %02d" % season)
    eps = set()
    for f in glob.glob(os.path.join(d, "*.strm")):
        m = re.search(r"S\d+E(\d+)", os.path.basename(f))
        if m:
            eps.add(int(m.group(1)))
    return eps | library.series_eps(show, season)   # desktop 版没有 .strm,以库索引为准


async def check_one(show, season=1):
    """返回新增集数。"""
    disc = await finder.discover(show)
    if not disc or disc.get("type") != "series":
        return 0
    avail = set(finder.available_eps(disc))
    have = existing_eps(show, season)
    new = sorted(avail - have)
    if not new:
        return 0
    res = await finder.materialize(disc, eps=set(new))
    if not res or not res.get("episodes"):
        return 0
    sea = res.get("season", season)
    library.add_series(show, res["channel"], res["episodes"], sea)
    bad, _ = await prepare.check_and_route(show, sea, res["channel"], res["episodes"])
    if bad:                       # 坏交错片源:不发 .strm,后台转封装好再出现
        n, d = len(res["episodes"]), "后台准备中"
    else:
        n, d = strm.write_strm(show, res["channel"], res["episodes"], sea, clear=False)
    eps = sorted(e["ep"] for e in res["episodes"])
    print("[updater] 《%s》+%d集 %s" % (show, n, eps), flush=True)
    state.add_ingest({"name": show, "show": show, "count": n, "status": "done",
                      "msg": "追更 %d 集: %s" % (n, ",".join("E%02d" % e for e in eps)),
                      "ts": int(time.time())})
    return n


async def check_all():
    for f in list(state.follows):
        try:
            added = await check_one(f["show"], f.get("season", 1))
            f["last"] = int(time.time())
            f["last_count"] = added
        except Exception as e:
            print("[updater] %s 检查出错 %r" % (f.get("show"), repr(e)), flush=True)
    follows.save()


async def loop():
    while True:
        await asyncio.sleep(max(1, state.cfg.update_interval_hours) * 3600)
        if not state.follows or not state.cfg.session:
            continue
        print("[updater] 开始追更检查,%d 部" % len(state.follows), flush=True)
        await check_all()
