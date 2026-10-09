"""4 技能のスコアの推移を集計する

AI の採点は日によってぶれるので、1 回ごとの値ではなく週の平均で傾向を見る。
"""
import datetime as dt
from collections import defaultdict

from . import storage

SKILL_JA = {"speaking": "スピーキング", "listening": "リスニング", "writing": "ライティング", "reading": "リーディング", "lesson": "教材"}


def points() -> list[dict]:
    """スコアのある練習を古い順に並べる"""
    out = []
    for skill in storage.SKILLS:
        for s in storage.load_all(skill):
            r = s.get("result") or {}
            if r.get("score") is not None:
                out.append({"date": s["created"][:10], "skill": skill, "id": s["id"],
                            "score": r["score"], "details": r.get("details", {})})
    return sorted(out, key=lambda p: p["id"])


def week_start(date: str) -> str:
    d = dt.date.fromisoformat(date)
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def weekly(pts: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in pts:
        groups[(week_start(p["date"]), p["skill"])].append(p)
    out = []
    for (week, skill), ps in sorted(groups.items()):
        row = {"week": week, "skill": skill, "count": len(ps), "avg": round(sum(p["score"] for p in ps) / len(ps))}
        # リーディングは正答率だけでなく速さも伸ばしたいので、WPM も平均する
        wpms = [p["details"].get("wpm") for p in ps if p["details"].get("wpm")]
        if skill == "reading" and wpms:
            row["wpm"] = round(sum(wpms) / len(wpms))
        out.append(row)
    return out


def render() -> str:
    rows = weekly(points())
    if not rows:
        return "# 進捗\n\nまだスコアがありません。\n"
    weeks = sorted({r["week"] for r in rows})
    cell = {(r["week"], r["skill"]): r for r in rows}
    out = ["# 進捗（週ごとの平均スコア・回数）", "",
           "| 週 | " + " | ".join(SKILL_JA[s] for s in storage.SKILLS) + " |",
           "|---|" + "---|" * len(storage.SKILLS)]
    for w in weeks:
        cols = []
        for s in storage.SKILLS:
            r = cell.get((w, s))
            if not r:
                cols.append("-")
                continue
            extra = " / %d wpm" % r["wpm"] if r.get("wpm") else ""
            cols.append("%d（%d 回%s）" % (r["avg"], r["count"], extra))
        out.append("| %s〜 | %s |" % (w, " | ".join(cols)))
    return "\n".join(out) + "\n"
