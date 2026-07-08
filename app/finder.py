"""资源发现。支持三类源:
  ① 群/频道:按关键词搜历史,收直传视频文件;
  ② 搜索bot(如 @jisou):发片名,读回复里的 t.me/频道/msgid 链接,解析成视频;
  ③ 深链bot(如 Youxiu_bot):回复是 t.me/bot?start=TOKEN 深链列表(带描述标题),
     AI 按标题挑对的条目 → 逐个 /start 兑换 → bot 私聊发来视频文件。
汇总后交 AI 选集/判电影。含色情/垃圾过滤。"""
import asyncio, re
from telethon.tl.types import MessageEntityTextUrl, User
from . import state, ai

VIDEO_EXT = (".mp4", ".mkv", ".ts", ".avi", ".m2ts", ".mov")
LINK_RE = re.compile(r"https?://t\.me/([A-Za-z0-9_]+)/(\d+)")
DEEPLINK_RE = re.compile(r"https?://t\.me/([A-Za-z0-9_]+)\?start=([A-Za-z0-9_\-]+)")

BLOCK_RE = re.compile(
    r"(无码|有码|步兵|骑兵|番号|萝莉|人妻|少妇|熟女|御姐|偷拍|自拍|约炮|门事件|福利姬|"
    r"裸聊|情色|色情|成人|18禁|三级|做爱|口交|群交|露出|诱惑|прон|porn|xxxx|hentai|"
    r"\bjav\b|\bsex\b|nomask|no.?mask|onlyfans|女优|痴汉|巨乳|嫩模|反差|绿帽|乱伦|"
    r"制服诱惑|丝袜|情趣|调教|重口|里番)", re.I)


def _is_spam(text):
    return bool(BLOCK_RE.search(text or ""))


def _parse_entities(m):
    """从一条消息里抽 (t.me/频道/msgid 链接, 深链条目)。"""
    tme, deep = [], []
    for e, t in (m.get_entities_text() or []):
        if not isinstance(e, MessageEntityTextUrl):
            continue
        u = e.url
        mm = LINK_RE.match(u)
        if mm:
            tme.append((mm.group(1), int(mm.group(2))))
            continue
        dm = DEEPLINK_RE.match(u)
        if dm:
            deep.append({"bot": dm.group(1), "token": dm.group(2), "title": (t or "").strip()})
    return tme, deep


async def _from_entity(ent, src, film, limit):
    c = state.client
    direct, links = [], []
    async for m in c.iter_messages(ent, search=film, limit=limit):
        if m.file and (m.file.name or "").lower().endswith(VIDEO_EXT):
            direct.append({"mid": m.id, "channel": src, "filename": m.file.name, "size": m.file.size})
        if m.message:
            tme, _ = _parse_entities(m)
            links += tme
    return direct, links


def _next_button(m):
    """找回复里的「下一页」回调按钮。"""
    if not m.buttons:
        return None
    for row in m.buttons:
        for b in row:
            if getattr(b, "data", None) and re.search(r"下一?页|下页|➡|next", b.text or "", re.I):
                return b
    return None


def _core(film):
    return re.sub(r"[\s\d季集第部]", "", film or "")


def _page_info(m):
    mm = re.search(r"第\s*(\d+)\s*/\s*(\d+)\s*页", m.message or "")
    return (int(mm.group(1)), int(mm.group(2))) if mm else (None, None)


async def _from_bot(ent, film, max_pages=6):
    """给 bot 发片名,读回复;深链bot有翻页则自动翻页收全(点「下一页」回调→轮询到页码+1再收集)。
    返回 (t.me链接, 深链条目)。"""
    c = state.client
    await c.send_message(ent, film)
    await asyncio.sleep(9)
    msgs = await c.get_messages(ent, limit=1)
    if not msgs:
        return [], []
    m = msgs[0]
    tme, deep = _parse_entities(m)
    seen = set(d["token"] for d in deep)
    core = _core(film)

    def _matches(title):
        return bool(core) and all(ch in (title or "") for ch in core)

    cur, total = _page_info(m)
    pages = 1
    while pages < max_pages and total and cur and cur < total:
        btn = _next_button(m)
        if not btn:
            break
        try:
            await m.click(data=btn.data)
        except Exception as e:
            print("[finder] 翻页点击失败", repr(e), flush=True)
            break
        # 轮询到下一页(bot 可能编辑原消息、也可能发新消息 → 读最新消息按页码认)
        target, advanced = cur + 1, False
        for _ in range(8):
            await asyncio.sleep(1.2)
            try:
                latest = await c.get_messages(ent, limit=3)
            except Exception:
                break
            hit = next((x for x in latest if _page_info(x)[0] == target), None)
            if hit is not None:
                m = hit
                advanced = True
                break
        if not advanced:
            break
        cur = target
        _, deep2 = _parse_entities(m)
        new = [d for d in deep2 if d["token"] not in seen]
        for d in new:
            seen.add(d["token"])
        deep += new
        pages += 1
        if not any(_matches(d["title"]) for d in new):   # 本页已无本剧条目 → 停
            break
    if pages > 1:
        print("[finder] %s 深链翻了 %d 页,共 %d 条" % (film, pages, len(deep)), flush=True)
    return tme, deep


async def _resolve_links(links):
    c = state.client
    from collections import defaultdict
    bych = defaultdict(list)
    for ch, mid in links:
        if "jisou" in ch.lower() or "bot" in ch.lower():
            continue
        bych[ch].append(mid)
    out = []
    for ch, mids in bych.items():
        lo, hi = min(mids) - 15, max(mids) + 60
        try:
            ent = await c.get_entity(ch)
            msgs = await c.get_messages(ent, ids=list(range(lo, hi + 1)))
        except Exception as e:
            print("[finder] 解析链接频道失败", ch, repr(e), flush=True)
            continue
        for m in msgs:
            if m and m.file and (m.file.name or "").lower().endswith(VIDEO_EXT):
                out.append({"mid": m.id, "channel": ch, "filename": m.file.name, "size": m.file.size})
    return out


async def _redeem(botname, token):
    """给深链bot发 /start TOKEN,取回它新发来的视频消息(只要msgid,不下载)。"""
    c = state.client
    ent = await c.get_entity(botname)
    try:
        before = (await c.get_messages(ent, limit=1))[0].id
    except Exception:
        before = 0
    await c.send_message(ent, "/start " + token)
    for _ in range(4):
        await asyncio.sleep(3)
        for m in await c.get_messages(ent, limit=8):
            if m.id > before and m.file and (m.file.mime_type or "").startswith("video"):
                return {"mid": m.id, "channel": botname,
                        "filename": m.file.name or "video.mp4", "size": m.file.size}
    return None


async def _collect(film, limit=80):
    """从所有源收集 (直传视频候选, t.me链接, 深链条目)。"""
    c = state.client
    candidates, all_links, all_deep = [], [], []
    for src in state.cfg.sources():
        try:
            ent = await c.get_entity(src)
        except Exception as e:
            print("[finder] 无法解析源", src, repr(e), flush=True)
            continue
        if isinstance(ent, User) and getattr(ent, "bot", False):
            tme, deep = await _from_bot(ent, film)
            all_links += tme
            all_deep += deep
        else:
            direct, links = await _from_entity(ent, src, film, limit)
            candidates += direct
            all_links += links
    return candidates, all_links, all_deep


async def _discover_deeplinks(film, deeplinks):
    """深链bot:AI按标题挑 → 返回分集清单(带token,**不兑换**)。"""
    core = _core(film)
    items = [d for d in deeplinks
             if not _is_spam(d["title"]) and (not core or all(ch in d["title"] for ch in core))]
    if not items:
        return None
    pick = await ai.pick_deeplink(film, items)
    if not pick or pick.get("type") == "none" or not pick.get("picks"):
        return None
    bot, picks = None, []
    for p in pick["picks"]:
        i = p.get("i")
        if i is None or i < 0 or i >= len(items):
            continue
        it = items[i]
        bot = bot or it["bot"]
        picks.append({"ep": p["ep"], "token": it["token"], "title": it["title"]})
    if not picks:
        return None
    return {"kind": "deeplink", "type": pick["type"], "title": pick.get("title") or film,
            "year": pick.get("year"), "season": pick.get("season", 1), "bot": bot, "picks": picks}


async def discover(film, limit=80):
    """搜索+判定,返回可获取的分集清单(深链不兑换)。追更用它做增量对比。"""
    candidates, all_links, all_deep = await _collect(film, limit)
    if all_deep:
        print("[finder] 片名=%s 深链条目=%d" % (film, len(all_deep)), flush=True)
        d = await _discover_deeplinks(film, all_deep)
        if d:
            return d
    if all_links:
        candidates += await _resolve_links(all_links)
    seen, uniq, blocked = set(), [], 0
    for c2 in candidates:
        k = (c2["channel"], c2["mid"])
        if k in seen:
            continue
        seen.add(k)
        if _is_spam(c2.get("filename", "")) or _is_spam(c2.get("channel", "")):
            blocked += 1
            continue
        uniq.append(c2)
    print("[finder] 片名=%s 候选=%d (过滤色情/垃圾 %d)" % (film, len(uniq), blocked), flush=True)
    res = await ai.analyze(film, uniq)
    if res:
        res["kind"] = "direct"
    return res


def available_eps(discovery):
    """discovery 里可获取的集号(仅剧集)。"""
    if not discovery or discovery.get("type") != "series":
        return []
    if discovery.get("kind") == "deeplink":
        return sorted(p["ep"] for p in discovery.get("picks", []))
    return sorted(e["ep"] for e in discovery.get("episodes", []))


async def materialize(discovery, eps=None):
    """把 discovery 变成可写结果;深链按需兑换(eps=None全部,否则只兑换这些集)。"""
    if discovery.get("kind") == "direct":
        r = dict(discovery)
        if eps is not None and r.get("type") == "series":
            r["episodes"] = [e for e in r.get("episodes", []) if e["ep"] in eps]
        return r
    picks = discovery["picks"]
    if eps is not None:
        picks = [p for p in picks if p["ep"] in eps]
    parts = []
    for p in picks:
        f = await _redeem(discovery["bot"], p["token"])
        if f:
            f["ep"] = p["ep"]
            parts.append(f)
    if not parts:
        return None
    parts.sort(key=lambda x: x["ep"])
    channel = parts[0]["channel"]
    if discovery["type"] == "series":
        return {"type": "series", "channel": channel, "season": discovery.get("season", 1),
                "episodes": [{"mid": p["mid"], "ep": p["ep"], "filename": p["filename"]} for p in parts]}
    if len(parts) == 1:
        return {"type": "movie", "channel": channel, "mid": parts[0]["mid"],
                "filename": parts[0]["filename"], "title": discovery.get("title") or "", "year": discovery.get("year")}
    return {"type": "movie", "channel": channel, "title": discovery.get("title") or "",
            "year": discovery.get("year"),
            "parts": [{"mid": p["mid"], "ep": p["ep"], "filename": p["filename"]} for p in parts]}


async def find(film, limit=80):
    """一次性入库:发现 + 全部兑换。"""
    d = await discover(film, limit)
    if not d:
        return None
    return await materialize(d)
