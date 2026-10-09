"""外から（Cloudflare Access 経由で）練習した時間の記録

外から練習すると Claude Code のセッションが無く、journal に start / end が残らない。
そこで画面が使われている間だけ 1 分ごとに通知してもらい、その時刻の並びからセッションを組み立てる。
手元の練習は Claude Code のセッションで数えているので、外からの通知だけを記録する（二重計上を避ける）。

保存先は practice_dir/activity/YYYY/MM/YYYY-MM-DD.json。技能ではなく進捗の集計対象でもないので、
storage.SKILLS には入れない。
"""
import json
import time
from pathlib import Path

from . import storage

# Access を通ったリクエストにだけ Cloudflare が付けるヘッダー。サーバーは 127.0.0.1 にしか
# bind していないので、これが付いて届くのは tunnel 経由（＝外から）のリクエストだけ
REMOTE_HEADER = "cf-access-authenticated-user-email"

# 通知の間がこれより空いたら別のセッションとみなす（スキマ時間の練習は細切れになるため）
GAP_MINUTES = 10


def _path(date: str) -> Path:
    # conftest がテストで差し替えるのは storage.settings なので、保存先はそこから取る
    return storage.settings.practice_dir / "activity" / date[:4] / date[5:7] / ("%s.json" % date)


def load(date: str) -> list[str]:
    p = _path(date)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("minutes", [])
    except json.JSONDecodeError:
        return []


def record(now: float | None = None) -> None:
    t = time.localtime(now)
    date, minute = time.strftime("%Y-%m-%d", t), time.strftime("%H:%M", t)
    with storage.lock:
        minutes = load(date)
        if minute in minutes:
            return
        minutes = sorted(minutes + [minute])
        p = _path(date)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"date": date, "minutes": minutes}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(p)


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(n: int) -> str:
    return "%02d:%02d" % divmod(n, 60)


def sessions(date: str) -> list[dict]:
    """通知の時刻を並べ、間が GAP_MINUTES を超えたら区切る。end は最後の通知 + 1 分"""
    out: list[dict] = []
    for m in sorted(_to_min(x) for x in load(date)):
        if out and m - out[-1]["_last"] <= GAP_MINUTES:
            out[-1]["_last"] = m
        else:
            out.append({"_start": m, "_last": m})
    return [{"start": _to_hhmm(s["_start"]), "end": _to_hhmm(s["_last"] + 1),
             "minutes": s["_last"] + 1 - s["_start"]} for s in out]
