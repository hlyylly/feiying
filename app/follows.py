"""追更列表持久化(data/follows.json)。"""
import json, os, time
from .config import DATA_DIR
from . import state

FOLLOWS_PATH = os.path.join(DATA_DIR, "follows.json")


def load():
    try:
        state.follows = json.load(open(FOLLOWS_PATH, encoding="utf-8"))
    except Exception:
        state.follows = []


def save():
    try:
        tmp = FOLLOWS_PATH + ".tmp"
        json.dump(state.follows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, FOLLOWS_PATH)
    except Exception:
        pass


def add(show, season=1):
    if not any(f["show"] == show for f in state.follows):
        state.follows.append({"show": show, "season": season, "ts": int(time.time()),
                              "last": 0, "last_count": 0})
        save()
        print("[follows] +追更", show, flush=True)


def remove(show):
    state.follows[:] = [f for f in state.follows if f["show"] != show]
    save()
