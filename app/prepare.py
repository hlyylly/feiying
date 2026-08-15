"""坏交错片源的预处理。

有些压制版把音频和视频各自成块地写(同一时刻能隔几百 MB)。这种片子走 .strm+HTTP
时播放器每跳一次就要重建一次 TCP,吞吐喂不饱码率,看两秒卡一下;而放本地文件毫无问题
(寻道免费)。所以入库时先只取 moov 判一下,坏的就不发 .strm,改成后台下满 + 转封装成
媒体库里的真 mp4,好一集出现一集。正常片源(实测占绝大多数)完全不走这条路。
"""
import asyncio, os, subprocess
from . import state, mp4probe, library
from .config import CACHE_DIR

GAP_LIMIT = 32 * 1024 * 1024      # 同一时刻音视频超过这么远就算坏交错
_ALIGN = 4096                     # TG 取文件要求偏移按 4096 对齐
_queue = None
_worker = None
status = {}                       # (show, season) -> 给前端看的一句话


async def _fetch(msg, off, n):
    """从 TG 直接取一小段,不落缓存(判交错只要几 MB,不值得建整个稀疏文件)。"""
    base = (off // _ALIGN) * _ALIGN
    skip = off - base
    need = skip + n
    buf = bytearray()
    async for chunk in state.client.iter_download(msg, offset=base, request_size=256 * 1024):
        buf += chunk
        if len(buf) >= need:
            break
    return bytes(buf[skip:need])


async def probe(msg):
    """只取 moov 判交错,返回最大间隔字节数;判不了返回 -1。"""
    size = msg.file.size
    head = await _fetch(msg, 0, 4096)
    r = mp4probe.moov_range(head, size)
    if not r:
        return -1
    off, ln = r
    if ln is None:                                  # moov 在 mdat 后面,去那儿读头
        hb = mp4probe.box_header(await _fetch(msg, off, 16))
        if not hb or hb[0] != b"moov":
            return -1
        ln = hb[1]
    if ln > 64 * 1024 * 1024:                       # moov 大得离谱,不折腾
        return -1
    moov = head[off:off + ln] if off + ln <= len(head) else await _fetch(msg, off, ln)
    try:
        return mp4probe.interleave_gap(moov)
    except Exception as e:
        print("[prepare] 解析 moov 失败", repr(e), flush=True)
        return -1


async def _cache_fully(ch, mid, msg):
    """把整集下满(复用缓存层的预取)。"""
    c = state.cache.get_cacher((ch, mid), msg.file.size, msg, chain=False)
    c.demand = 0
    idle = 0
    last = -1
    while c.cached_blocks() < c.nblocks:
        c.start_prefetch()                       # 预取任务万一挂了这里会重新拉起
        await asyncio.sleep(3)
        got = c.cached_blocks()
        idle = idle + 1 if got == last else 0
        last = got
        if idle > 100:                           # 5 分钟一点没动:放弃
            return False
    return True


async def _remux(src, dst):
    """无损转封装:重排成正常交错,顺带把 moov 挪到文件头。"""
    tmp = dst + ".part"
    p = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-v", "error", "-i", src, "-c", "copy",
        "-movflags", "+faststart", "-f", "mp4", tmp,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _, err = await p.communicate()
    if p.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
        print("[prepare] 转封装失败", err[-300:].decode("utf-8", "ignore"), flush=True)
        try: os.remove(tmp)
        except OSError: pass
        return False
    os.replace(tmp, dst)
    try:
        os.chmod(dst, 0o664)
    except OSError:
        pass
    return True


async def _do_one(show, season, ch, ep, mid):
    """下满一集 → 转封装进媒体库 → 删掉缓存里的原始块(库里已有成品,留着白占地)。"""
    try:
        msg = await state.cache.get_msg(ch, mid)
        if not msg or not msg.file:
            return False
        if not await _cache_fully(ch, mid, msg):
            print("[prepare] %s E%02d 下载卡住,跳过" % (show, ep), flush=True)
            return False
        src = os.path.join(CACHE_DIR, "%s_%d.bin" % (ch, mid))
        d = os.path.join(state.cfg.media_dir, show, "Season %02d" % season)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, "%s - S%02dE%02d.mp4" % (show, season, ep))
        if not await _remux(src, dst):
            return False
        strm_path = dst[:-4] + ".strm"
        if os.path.exists(strm_path):
            try: os.remove(strm_path)          # 同一集别在库里出现两次
            except OSError: pass
        for p in (src, src[:-4] + ".bm"):
            try: os.remove(p)
            except OSError: pass
        state.cache.cachers.pop((ch, mid), None)
        print("[prepare] %s E%02d 已重新封装入库" % (show, ep), flush=True)
        return True
    except Exception as e:
        print("[prepare] %s E%02d 预处理出错 %r" % (show, ep, e), flush=True)
        return False


async def _run():
    while True:
        show, season, ch, eps = await _queue.get()
        key = (show, season)
        done = 0
        for i, e in enumerate(eps):
            status[key] = "正在准备第 %d/%d 集(这版片源要重新封装才不卡)" % (i + 1, len(eps))
            if await _do_one(show, season, ch, e["ep"], e["mid"]):
                done += 1
        status[key] = "已准备好 %d/%d 集" % (done, len(eps))
        print("[prepare] 《%s》完成 %d/%d 集" % (show, done, len(eps)), flush=True)


def enqueue(show, season, channel, episodes):
    """排队后台准备。第一集排最前,她最可能先点它。"""
    global _queue, _worker
    if _queue is None:
        _queue = asyncio.Queue()
    if _worker is None or _worker.done():
        _worker = asyncio.create_task(_run())
    eps = sorted(episodes, key=lambda e: e["ep"])
    status[(show, season)] = "排队中(%d 集)" % len(eps)
    _queue.put_nowait((show, season, channel, eps))


async def check_and_route(show, season, channel, episodes):
    """入库时调用。返回 (是否坏片源, 最大间隔字节)。
    坏的话这里会把后台准备排上队,调用方就别再写 .strm 了。"""
    try:
        first = sorted(episodes, key=lambda e: e["ep"])[0]
        msg = await state.cache.get_msg(channel, first["mid"])
        if not msg or not msg.file:
            return False, -1
        gap = await probe(msg)
    except Exception as e:
        print("[prepare] 探测失败,按正常片源走", repr(e), flush=True)
        return False, -1
    if gap > GAP_LIMIT:
        print("[prepare] 《%s》音视频最远隔 %d MB,判为坏交错,转后台预处理"
              % (show, gap // 1048576), flush=True)
        enqueue(show, season, channel, episodes)
        return True, gap
    print("[prepare] 《%s》交错正常(最大 %.1f MB),照常入库"
          % (show, max(gap, 0) / 1048576.0), flush=True)
    return False, gap
