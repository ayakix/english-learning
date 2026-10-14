"""1 問ずつ付ける ○（言えた）・×（言えなかった）の記録（Versant と単語で共通）

1 日・1 モードで 1 つの session にまとめる。範囲を 2 つやった日も同じ session に足す。
session は最初に ○/× を付けたときに作る（タブを開いただけで空の記録ができないように）。
"""
import time

from . import storage


def today_session(skill: str, mode: str) -> dict | None:
    today = time.strftime("%Y-%m-%d")
    return next((s for s in storage.load_all(skill) if s["created"][:10] == today and s.get("mode") == mode), None)


def get(skill: str, mode: str) -> dict:
    s = today_session(skill, mode)
    return {"marks": {i: m["ok"] for i, m in s["marks"].items()} if s else {}}


def put(skill: str, mode: str, title: str, item_id: str, ok: bool, scored: bool = True, **extra) -> dict:
    """extra は例題ごとに残したい情報（復唱のレベルなど）。scored=False なら点数を付けない"""
    with storage.lock:
        s = today_session(skill, mode) or storage.new_session(skill, title=title, mode=mode, marks={})
        s["marks"][item_id] = {"ok": ok, **extra}
        marks = s["marks"].values()
        n_ok = sum(1 for m in marks if m["ok"])
        s["result"] = {"score": round(n_ok / len(marks) * 100) if scored else None,
                       "details": {"ok": n_ok, "total": len(marks)}}
        storage.save(s)
    return {"marks": {i: m["ok"] for i, m in s["marks"].items()}}
