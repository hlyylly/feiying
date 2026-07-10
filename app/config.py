"""配置读写。所有配置落地 DATA_DIR/config.json，单实例单账号。"""
import json, os

DATA_DIR = os.environ.get("FEIYING_DATA", "/data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

# api_id/hash 默认用公共的 TDesktop 值(my.telegram.org 建应用常失败),用户可覆盖
DEFAULTS = {
    "api_id": 2040,
    "api_hash": "b18441a1ff607e10a989891a5462e627",
    "phone": "",
    "session": "",            # telethon StringSession,登录后写入
    "source": "",             # 种子群/频道 username,多个用逗号分隔
    "vmess": "",              # vmess:// 或 vless:// 分享链接
    "proxy_url": "",          # 外部代理 socks5://host:port 或 http://host:port,填了则不起内置 xray;和 vmess 都留空=直连
    "deepseek_key": "",
    "deepseek_base": "https://api.deepseek.com",
    "deepseek_model": "deepseek-chat",
    "media_dir": "/media/tv",     # 剧集 .strm 输出根(容器内挂载)
    "movie_dir": "/media/movies", # 电影 .strm 输出根
    "stream_base": "",        # 飞牛访问缓存流服务的地址,如 http://192.168.3.8:8890
    "stream_port": 8890,
    "cache_quota_gb": 18,     # LRU 配额
    "prefetch_workers": 4,    # 预取并发,别调高(>5 触发 TG flood-wait)
    "dl_sem": 5,              # 全局下载并发上限
    "update_interval_hours": 12,  # 追更检查间隔(小时)
}


class Config:
    def __init__(self, data=None):
        self._d = dict(DEFAULTS)
        if data:
            self._d.update({k: v for k, v in data.items() if k in DEFAULTS})

    @classmethod
    def load(cls):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        if os.path.exists(CONFIG_PATH):
            try:
                return cls(json.load(open(CONFIG_PATH, encoding="utf-8")))
            except Exception:
                pass
        return cls()

    def save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        json.dump(self._d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)

    def __getattr__(self, k):
        try:
            return self.__dict__["_d"][k]
        except KeyError:
            raise AttributeError(k)

    def set(self, **kw):
        for k, v in kw.items():
            if k in DEFAULTS:
                self._d[k] = v
        self.save()

    def sources(self):
        return [s.strip().lstrip("@") for s in (self.source or "").split(",") if s.strip()]

    def public_dict(self):
        """给 Web 用,隐藏敏感值。"""
        d = dict(self._d)
        d["session"] = "已登录" if d["session"] else ""
        if d["deepseek_key"]:
            d["deepseek_key"] = d["deepseek_key"][:6] + "..."
        return d
