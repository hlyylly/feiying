"""块缓存流播代理 —— 移植自本会话验证过的 raw_stream.py。
原生 asyncio HTTP(避开 aiohttp 对飞牛重复 User-Agent 报400);4MB块位图缓存 + .bm持久化;
多连接预取(环形扫描,别超5并发否则TG flood-wait);命中本地pread秒回,miss telethon兜底;
当前集下满自动滚动预取下一集;LRU 配额淘汰。用全局共享 client(state.client)。"""
import asyncio, os, re, time
from . import state
from .config import CACHE_DIR

BLOCK = 4 * 1024 * 1024
CHAIN_COOLDOWN = 300      # 同一集多久内不重复查下一集(秒)


def _name(ch, mid):
    return "%s_%d.bin" % (ch, mid)


def _parse_name(n):
    ch, mid = n[:-4].rsplit("_", 1)
    return (ch, int(mid))


class Cacher:
    def __init__(self, srv, key, size, msg, chain):
        self.srv = srv
        self.ch, self.mid = key
        self.size = size
        self.msg = msg
        self.chain = chain
        self.nblocks = (size + BLOCK - 1) // BLOCK
        self.path = os.path.join(CACHE_DIR, _name(self.ch, self.mid))
        self.bmpath = self.path[:-4] + ".bm"
        self.bitmap = bytearray(self.nblocks)
        self.locks = {}
        self.demand = 0
        self.prefetch_task = None
        self._ensure_file()
        self._load_bitmap()

    def _ensure_file(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) != self.size:
            with open(self.path, "wb") as f:
                f.truncate(self.size)
            if os.path.exists(self.bmpath):
                try: os.remove(self.bmpath)
                except OSError: pass

    def _load_bitmap(self):
        try:
            d = open(self.bmpath, "rb").read()
            if len(d) == self.nblocks:
                self.bitmap = bytearray(d)
        except OSError:
            pass

    def _save_bitmap(self):
        try:
            tmp = self.bmpath + ".t"
            with open(tmp, "wb") as f:
                f.write(self.bitmap)
            os.replace(tmp, self.bmpath)
        except OSError:
            pass

    def cached_blocks(self):
        return sum(self.bitmap)

    def _read_block(self, blk):
        off = blk * BLOCK
        limit = min(BLOCK, self.size - off)
        with open(self.path, "rb") as f:
            f.seek(off)
            return f.read(limit)

    def _write_block(self, blk, data):
        with open(self.path, "r+b") as f:
            f.seek(blk * BLOCK)
            f.write(data)

    async def _download(self, off, limit):
        async with self.srv.dl_sem:
            buf = bytearray()
            async for chunk in state.client.iter_download(self.msg, offset=off, request_size=512 * 1024):
                buf += chunk
                if len(buf) >= limit:
                    break
            return bytes(buf[:limit])

    async def get_block(self, blk):
        if self.bitmap[blk]:
            try: os.utime(self.path, None)
            except OSError: pass
            return self._read_block(blk)
        ev = self.locks.get(blk)
        if ev is not None:
            await ev.wait()
            return self._read_block(blk)
        ev = asyncio.Event()
        self.locks[blk] = ev
        try:
            off = blk * BLOCK
            limit = min(BLOCK, self.size - off)
            data = await self._download(off, limit)
            self._write_block(blk, data)
            self.bitmap[blk] = 1
            self._save_bitmap()
            return data
        finally:
            ev.set()
            self.locks.pop(blk, None)

    def _next_missing(self):
        # 环形扫描:从 demand 绕一圈,找第一个未下未flight块;返回None仅当整集下满
        n = self.nblocks
        for k in range(n):
            i = self.demand + k
            if i >= n:
                i -= n
            if not self.bitmap[i] and i not in self.locks:
                return i
        return None

    def start_prefetch(self):
        if self.prefetch_task is None or self.prefetch_task.done():
            self.prefetch_task = asyncio.create_task(self._prefetch_loop())

    async def _prefetch_loop(self):
        got = 0
        async def worker():
            nonlocal got
            while True:
                blk = self._next_missing()
                if blk is None:
                    return
                try:
                    await self.get_block(blk)
                    got += 1
                except Exception as e:
                    print("[cache] prefetch blk err", self.mid, blk, repr(e), flush=True)
                    await asyncio.sleep(1)
        await asyncio.gather(*[worker() for _ in range(self.srv.workers)])
        if not got:
            return    # 本来就下满了:不刷日志,更不能再去查下一集(每次都是一个TG请求)
        print("[cache] prefetch done %s %d %d/%d" % (self.ch, self.mid, self.cached_blocks(), self.nblocks), flush=True)
        if self.chain:
            await self.srv.prefetch_next_episode(self.ch, self.mid)


class CacheServer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.workers = max(1, min(5, cfg.prefetch_workers))   # 上限5,别触发flood-wait
        self.quota = cfg.cache_quota_gb * 1024 ** 3
        self.port = cfg.stream_port
        self.dl_sem = None
        self.msgcache = {}
        self._chain_at = {}
        self.cachers = {}
        self.server = None

    async def start(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.dl_sem = asyncio.Semaphore(self.cfg.dl_sem)
        self.server = await asyncio.start_server(self._handle, "0.0.0.0", self.port)
        print("[cache] stream(cache) server on :%d" % self.port, flush=True)

    async def get_msg(self, ch, mid):
        key = (ch, mid)
        if key not in self.msgcache:
            ent = await state.client.get_entity(ch)
            self.msgcache[key] = await state.client.get_messages(ent, ids=mid)
        return self.msgcache[key]

    def enforce_quota(self, keep_path=None):
        files, total = [], 0
        for n in os.listdir(CACHE_DIR):
            if not n.endswith(".bin"):
                continue
            p = os.path.join(CACHE_DIR, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            # Windows 无 st_blocks,退化用表观大小(NTFS 稀疏文件会高估,宁多删不超配额)
            sz = getattr(st, "st_blocks", 0) * 512 or st.st_size
            files.append((st.st_atime, p, sz, n))
            total += sz
        files.sort()
        for atime, p, sz, n in files:
            if total < self.quota:
                break
            if p == keep_path:
                continue
            try:
                key = _parse_name(n)
            except Exception:
                key = None
            c = self.cachers.get(key)
            if c and c.prefetch_task and not c.prefetch_task.done():
                continue
            try:
                os.remove(p)
                bm = p[:-4] + ".bm"
                if os.path.exists(bm):
                    os.remove(bm)
                total -= sz
                if key:
                    self.cachers.pop(key, None)
                print("[cache] LRU evict", n, flush=True)
            except OSError:
                pass

    def get_cacher(self, key, size, msg, chain):
        c = self.cachers.get(key)
        if c is None:
            c = Cacher(self, key, size, msg, chain)
            self.cachers[key] = c
            self.enforce_quota(keep_path=c.path)
        elif chain and not c.chain:
            c.chain = True
            if c.prefetch_task and c.prefetch_task.done() and c.cached_blocks() == c.nblocks:
                asyncio.create_task(self.prefetch_next_episode(c.ch, c.mid))
        return c

    async def resume_incomplete(self, limit=2):
        """断点续缓:启动时找出没下完的缓存(位图有0),按最近使用优先恢复预取。
        最多 limit 部,避免开机就挤满带宽;正在看的请求随时可插队(demand 优先)。"""
        try:
            cand = []
            for n in os.listdir(CACHE_DIR):
                if not n.endswith(".bin"):
                    continue
                p = os.path.join(CACHE_DIR, n)
                try:
                    bits = open(p[:-4] + ".bm", "rb").read()
                    st = os.stat(p)
                except OSError:
                    continue              # 没位图=从没开始下,不算断点
                if not bits or all(bits):  # 全1=已下完
                    continue
                cand.append((max(st.st_atime, st.st_mtime), n))
            cand.sort(reverse=True)
            for _, n in cand[:limit]:
                try:
                    ch, mid = _parse_name(n)
                    msg = await self.get_msg(ch, mid)
                    if not msg or not msg.file:
                        continue
                    c = self.get_cacher((ch, mid), msg.file.size, msg, chain=False)
                    c.start_prefetch()
                    print("[cache] 续缓 %s %d/%d" % (n, c.cached_blocks(), c.nblocks), flush=True)
                except Exception as e:
                    print("[cache] 续缓失败", n, repr(e), flush=True)
        except Exception as e:
            print("[cache] resume err", repr(e), flush=True)

    async def prefetch_next_episode(self, ch, mid):
        # 查下一集要发一个 TG 请求,和下载块共用同一条 telethon 连接。
        # 同一集短时间内只查一次,否则播放器每来一个 range 就问一次,把下载挤住。
        now = time.monotonic()
        if now - self._chain_at.get((ch, mid), 0.0) < CHAIN_COOLDOWN:
            return
        self._chain_at[(ch, mid)] = now
        try:
            ent = await state.client.get_entity(ch)
            async for m in state.client.iter_messages(ent, min_id=mid, reverse=True, limit=12):
                if m.id <= mid:
                    continue
                if m.file and (m.file.mime_type or "").startswith("video"):
                    key = (ch, m.id)
                    self.msgcache[key] = m
                    c = self.get_cacher(key, m.file.size, m, chain=False)
                    c.demand = 0
                    c.start_prefetch()
                    print("[cache] prefetch NEXT ep", ch, m.id, flush=True)
                    return
            print("[cache] no next ep after", ch, mid, flush=True)
        except Exception as e:
            print("[cache] next ep err", repr(e), flush=True)

    def _hdr(self, status, extra, keep=False):
        lines = ["HTTP/1.1 " + status,
                 "Accept-Ranges: bytes",
                 "Connection: " + ("keep-alive" if keep else "close")] + extra
        return ("\r\n".join(lines) + "\r\n\r\n").encode("latin1")

    async def _handle(self, reader, writer):
        """一条连接上可以连续处理多个请求。
        播放器是按小段取片的,每段都新建 TCP 的话每次都要重走慢启动
        (实测电视每秒开 110 条连接,cwnd 一直卡在 10 出不去),于是边看边卡。"""
        try:
            while await self._one_request(reader, writer):
                pass
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError, ConnectionError):
            pass
        except Exception as e:
            print("[cache] handle err", repr(e), flush=True)
        try:
            writer.close()
        except Exception:
            pass

    async def _one_request(self, reader, writer):
        """处理一个请求。返回 True 表示这条连接还能继续复用。"""
        line = await reader.readline()
        if not line:
            return False
        parts = line.decode("latin1").strip().split(" ")
        if len(parts) < 2:
            return False
        method, path = parts[0], parts[1]
        rng, cli_close = None, False
        while True:
            h = await reader.readline()
            if h == b"":
                return False                      # 请求还没读完对端就断了
            if h in (b"\r\n", b"\n"):
                break
            hl = h.decode("latin1", "ignore").strip()
            low = hl.lower()
            if low.startswith("range:"):
                rng = hl.split(":", 1)[1].strip()
            elif low.startswith("connection:") and "close" in low:
                cli_close = True

        async def fail(status):
            writer.write(self._hdr(status, ["Content-Length: 0"]))
            await writer.drain()
            return False

        m = re.match(r"/([A-Za-z0-9_]+)/(\d+)", path)
        if not m:
            return await fail("404 Not Found")
        ch, mid = m.group(1), int(m.group(2))
        try:
            msg = await self.get_msg(ch, mid)
        except Exception:
            return await fail("502 Bad Gateway")
        if not msg or not msg.file:
            return await fail("404 Not Found")

        size = msg.file.size
        ctype = msg.file.mime_type or "video/mp4"
        start, end, status = 0, size - 1, "200 OK"
        if rng:
            mm = re.match(r"bytes=(\d+)-(\d*)", rng)
            if mm:
                start = int(mm.group(1))
                if mm.group(2):
                    end = min(int(mm.group(2)), size - 1)
                status = "206 Partial Content"
        if start >= size:
            return await fail("416 Range Not Satisfiable")

        keep = not cli_close
        length = end - start + 1
        extra = ["Content-Type: " + ctype, "Content-Length: " + str(length)]
        if status.startswith("206"):
            extra.append("Content-Range: bytes %d-%d/%d" % (start, end, size))
        writer.write(self._hdr(status, extra, keep=keep))
        await writer.drain()
        if method == "HEAD":
            return keep

        c = self.get_cacher((ch, mid), size, msg, chain=True)
        c.demand = start // BLOCK
        c.start_prefetch()
        for blk in range(start // BLOCK, end // BLOCK + 1):
            if writer.is_closing():
                # 客户端走了:write 不报错、drain 立刻返回,再循环下去会把整部片子空读一遍。
                # 此时 body 没发全,连接已经不同步,不能再复用。
                return False
            data = await c.get_block(blk)
            blkoff = blk * BLOCK
            s_in = max(start, blkoff) - blkoff
            e_in = min(end, blkoff + len(data) - 1) - blkoff
            if e_in >= s_in:
                writer.write(data[s_in:e_in + 1])
                await writer.drain()
        return keep

    def cache_usage_gb(self):
        total = 0
        try:
            for n in os.listdir(CACHE_DIR):
                if n.endswith(".bin"):
                    try:
                        st = os.stat(os.path.join(CACHE_DIR, n))
                        total += getattr(st, "st_blocks", 0) * 512 or st.st_size
                    except OSError:
                        pass
        except OSError:
            pass
        return round(total / 1024 ** 3, 2)
