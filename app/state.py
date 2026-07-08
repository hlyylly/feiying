"""共享运行时状态(单进程单实例)。各模块通过它拿 client/config/proxy 等。"""

cfg = None            # config.Config 实例
client = None         # telethon 用户 client(全局唯一,单账号)
proxy = None          # proxy.XrayProxy 实例
cache = None          # cache_server.CacheServer 实例
login_state = {}      # 登录中间态: {phone, phone_code_hash}
ingests = []          # 最近入库记录 [{name, show, count, status, ts}]
follows = []          # 追更列表 [{show, season, ts, last, last_count}]


def add_ingest(rec):
    ingests.insert(0, rec)
    del ingests[30:]
