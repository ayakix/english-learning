"""1 日分の練習結果を Markdown にまとめる

Claude が journal と mistakes を仕上げるときの材料にする（CLAUDE.md 参照）。
session.json を直接読ませるより、要点だけに絞った方が転記の漏れや読み違いが少ない。
"""
from . import storage

MODE_JA = {"overlap": "シャドーイング", "repeat": "リピート"}


def _seg_label(seg: str) -> str:
    return "全文" if seg == "all" else "文%d" % (int(seg) + 1)


def render(date: str) -> str:
    """date は YYYY-MM-DD"""
    prefix = date.replace("-", "")
    sessions = [storage.load(i) for i in sorted(storage.all_ids()) if i.startswith(prefix)]
    sessions = [s for s in sessions if s.get("attempts") or s.get("recordings")]
    if not sessions:
        return "# Photo Shadowing %s\n\n練習の記録はありません。\n" % date

    out = ["# Photo Shadowing %s" % date, ""]
    for s in sessions:
        out += ["## %s（practice/shadowing/%s/%s/%s）" % (s["created"], s["id"][:4], s["id"][4:6], s["id"]), ""]
        for a in s.get("attempts", []):
            out.append("- 説明 %s（%s 点）：%s" % (a["time"], a.get("score", "-"), a["text"]))
        c = s.get("correction")
        if c:
            if c.get("corrections"):
                out += ["", "### 添削", ""]
                out += ["- %s → **%s**：%s" % (f["before"], f["after"], f["reason_ja"]) for f in c["corrections"]]
            if c.get("key_expressions"):
                out += ["", "### 使える表現", ""]
                out += ["- %s：%s" % (k["en"], k["ja"]) for k in c["key_expressions"]]
            out += ["", "### 理想の文章（%s）" % c.get("level", ""), "", c.get("ideal", "")]
        recs = [r for r in s.get("recordings", []) if r.get("evaluation")]
        if s.get("recordings"):
            out += ["", "### シャドーイング（録音 %d 回・評価 %d 回）" % (len(s["recordings"]), len(recs)), ""]
        for r in recs:
            ev = r["evaluation"]
            out.append("- #%d %s %s：総合 %s（発音 %s / 流暢さ %s / 抑揚 %s / 再現度 %s）" % (
                r["n"], _seg_label(r["seg"]), MODE_JA.get(r.get("mode"), r.get("mode")), ev["overall"],
                ev["pronunciation"], ev["fluency"], ev["intonation"], ev["completeness"]))
            for w in ev.get("word_issues", []):
                out.append("  - **%s**：%s（コツ：%s）" % (w["word"], w["problem_ja"], w["tip_ja"]))
        out.append("")
    return "\n".join(out)
