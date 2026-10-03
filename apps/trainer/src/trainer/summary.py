"""1 日分の練習結果を Markdown にまとめる

Claude が journal と mistakes を仕上げるときの材料にする（CLAUDE.md 参照）。
session.json を直接読ませるより、要点だけに絞った方が転記の漏れや読み違いが少ない。
"""
from . import storage
from .progress import SKILL_JA

MODE_JA = {"overlap": "シャドーイング", "repeat": "リピート"}


def _seg_label(seg: str) -> str:
    return "全文" if seg == "all" else "文%d" % (int(seg) + 1)


def _corrections(cs: list[dict]) -> list[str]:
    return ["- %s → **%s**：%s" % (f["before"], f["after"], f["reason_ja"]) for f in cs]


def _expressions(ks: list[dict]) -> list[str]:
    return ["- %s：%s" % (k["en"], k["ja"]) for k in ks]


def _speaking(s: dict) -> list[str]:
    out = ["- 説明 %s（%s 点）：%s" % (a["time"], a.get("score", "-"), a["text"]) for a in s.get("attempts", [])]
    c = s.get("correction")
    if c:
        if c.get("corrections"):
            out += ["", "#### 添削", ""] + _corrections(c["corrections"])
        if c.get("key_expressions"):
            out += ["", "#### 使える表現", ""] + _expressions(c["key_expressions"])
        out += ["", "#### 理想の文章（%s）" % c.get("level", ""), "", c.get("ideal", "")]
    recs = [r for r in s.get("recordings", []) if r.get("evaluation")]
    if s.get("recordings"):
        out += ["", "#### シャドーイング（録音 %d 回・評価 %d 回）" % (len(s["recordings"]), len(recs)), ""]
    for r in recs:
        ev = r["evaluation"]
        out.append("- #%d %s %s：総合 %s（発音 %s / 流暢さ %s / 抑揚 %s / 再現度 %s）" % (
            r["n"], _seg_label(r["seg"]), MODE_JA.get(r.get("mode"), r.get("mode")), ev["overall"],
            ev["pronunciation"], ev["fluency"], ev["intonation"], ev["completeness"]))
        for w in ev.get("word_issues", []):
            out.append("  - **%s**：%s（コツ：%s）" % (w["word"], w["problem_ja"], w["tip_ja"]))
    return out


def _listening(s: dict) -> list[str]:
    out = []
    for it in s["items"]:
        if it.get("answer") is None:
            continue
        out.append("- 正確さ %d%%（聞き直し %d 回）：%s" % (round(it["accuracy"] * 100), it.get("replays", 0), it["text"]))
        miss = [d for d in it["diff"] if d["status"] != "ok"]
        if miss:
            out.append("  - 書き取り：%s" % it["answer"])
            out.append("  - 聞き取れなかった語：%s" % ", ".join(
                "%s→%s" % (d["t"] or "(なし)", d.get("heard", "(なし)")) for d in miss))
            out.append("  - ポイント：%s" % it["points_ja"])
    return out


def _writing(s: dict) -> list[str]:
    out = ["- お題：%s" % s["task"]["task"]]
    for sub in s["submissions"]:
        g = sub["grade"]
        out += ["", "#### 提出 %s（総合 %s・%s / 課題 %s・文法 %s・語彙 %s・構成 %s / %d 語）" % (
            sub["time"], g["overall"], g["cefr"], g["task"], g["grammar"], g["vocabulary"], g["coherence"],
            sub["words"]), "", sub["text"]]
        if g.get("corrections"):
            out += [""] + _corrections(g["corrections"])
    last = s["submissions"][-1]["grade"] if s["submissions"] else None
    if last and last.get("key_expressions"):
        out += ["", "#### 使える表現", ""] + _expressions(last["key_expressions"])
    return out


def _reading(s: dict) -> list[str]:
    sub = s.get("submission")
    if not sub:
        return ["- 未提出"]
    out = ["- 正解 %d / %d・%s wpm（%d 語を %d 秒）" % (
        sub["correct"], len(s["questions"]), sub["wpm"], s["words"], sub["reading_seconds"])]
    for q, a in zip(s["questions"], sub["answers"]):
        if q["answer"] != a:
            out.append("  - 不正解：%s（正解：%s）— %s" % (q["q"], q["options"][q["answer"]], q["explanation_ja"]))
    return out


def _wrong(qs: list[dict], answers: list[int]) -> list[str]:
    return ["  - 不正解：%s（正解：%s）— %s" % (q["q"], q["options"][q["answer"]], q["explanation_ja"])
            for q, a in zip(qs, answers) if q["answer"] != a]


def _voa(s: dict) -> list[str]:
    src, lis, rd = s["source"], s["listening"], s["reading"]
    # AI 教材には URL が無いので、取得元の名前を出す
    title = "[%s](%s)" % (src["title"], src["url"]) if src.get("url") else "%s（%s）" % (src["title"], src["site"])
    out = ["- 記事：%s（%d 語・音声 %d 秒・%s wpm）" % (title, s["words"], s["duration"], s.get("audio_wpm") or "-")]
    if lis["answers"] is not None:
        out.append("- 聞く：正解 %d / %d（全体を %d 回再生）" % (lis["correct"], len(lis["questions"]), lis["plays"]))
        out += _wrong(lis["questions"], lis["answers"])
    for d in s["dictation"]:
        if d["answer"] is None:
            continue
        out.append("- 書き取り 正確さ %d%%（%d 回再生）：%s" % (round(d["accuracy"] * 100), d["plays"], d["text"]))
        miss = [x for x in d["diff"] if x["status"] != "ok"]
        if miss:
            out.append("  - 書き取り：%s" % d["answer"])
            out.append("  - 聞き取れなかった語：%s" % ", ".join(
                "%s→%s" % (x["t"] or "(なし)", x.get("heard", "(なし)")) for x in miss))
            out.append("  - ポイント：%s" % d["points_ja"])
    if rd["answers"] is not None:
        out.append("- 読む：正解 %d / %d・%s wpm（%d 秒）" % (rd["correct"], len(rd["questions"]), rd["wpm"],
                                                     rd["reading_seconds"]))
        out += _wrong(rd["questions"], rd["answers"])
    return out


RENDER = {"speaking": _speaking, "listening": _listening, "writing": _writing, "reading": _reading, "voa": _voa}


def render(date: str) -> str:
    """date は YYYY-MM-DD"""
    prefix = date.replace("-", "")
    out = ["# 練習の記録 %s" % date, ""]
    found = False
    for skill in storage.SKILLS:
        # スピーキングは添削だけでシャドーイングの評価が無い日もあるので、説明の提出があれば載せる
        sessions = [s for s in reversed(storage.load_all(skill)) if s["id"].startswith(prefix) and (
            (s.get("result") or {}).get("score") is not None or s.get("attempts")
            # VOA は「聞く」だけ終えた日も載せる（スコアは書き取りまで終えないと出ないため）
            or (skill == "voa" and (s.get("result") or {}).get("details")))]
        if not sessions:
            continue
        found = True
        out += ["## %s" % SKILL_JA[skill], ""]
        for s in sessions:
            score = s["result"]["score"]
            out += ["### %s %s（%s 点・practice/%s/%s/%s/%s）" % (
                s["created"][11:], s.get("title", ""), "-" if score is None else score, skill, s["id"][:4], s["id"][4:6], s["id"]),
                ""]
            out += RENDER[skill](s) + [""]
    if not found:
        out.append("練習の記録はありません。")
    return "\n".join(out) + "\n"
