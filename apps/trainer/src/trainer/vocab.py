"""身近なものの単語：英→日・日→英で意味が分かるか・言えるかを確かめ、○/× を記録する

即答で「意味は分かるのに英語が出てこない（yolk・crib）」「単語を知らない（neat）」とつまずいたので作った。
例題は Claude が content/drills/vocab/items.json に書く。音声は単語だけを ElevenLabs で作る
（綴りから読み方を覚え違えないように発音を確かめるため。例文まで作るほどではない）。
置き場所・音声の作り方・配信は drills.py の種類の 1 つ（vocab）として共通にしている。
"""
import json

from fastapi import APIRouter
from pydantic import BaseModel

from . import drills, marks, storage
from .http import ApiError

SKILL = "vocab"
# 向きごとに記録を分ける（日→英の方が難しいので、混ぜると正答率の意味がぼやける）
MODES = {"en-ja": "単語 英→日", "ja-en": "単語 日→英"}

router = APIRouter(prefix="/api/vocab")


def items_by_id() -> dict[str, dict]:
    return {it["id"]: it for it in drills.load(SKILL)["items"]}


def _check_mode(mode: str) -> None:
    if mode not in MODES:
        raise ApiError("unknown mode: " + mode, 404)


@router.get("")
def get_vocab():
    """単語を返す。音声がまだ無い単語も、意味の確認には使えるので除かず、audio_file を空にする"""
    data = drills.load(SKILL)
    return {"themes": data.get("themes", []), "items": [_with_audio(it) for it in data["items"]]}


def _with_audio(it: dict) -> dict:
    return {**it, "audio_file": it["audio"]["main"].get("file") if drills.has_audio(SKILL, it) else None}


def _review_ids() -> dict:
    """手で足した復習対象（content/drills/vocab/review.json）。無ければ空"""
    p = drills.STOCK_DIR / SKILL / "review.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"ids": []}


@router.get("/review/{mode}")
def get_review(mode: str):
    """振り返りの単語を返す。

    Versant の振り返りは Claude が review.json を書き換えるが、単語は 1 日 20 語超で × も多く、手で写すのは追いつかない。
    そこで、その向きで最後に付けた記録が × の語を自動で集める（○ を付ければ次に開いたとき外れる）。
    加えて「意味は合っていたが音が怪しい」など、× でなくても見返したい語は review.json の ids で足せる。
    """
    _check_mode(mode)
    # 新しい順なので、先に出てきた記録がその語の最新。date は × を付けた日（画面で「10/21 ×」と出す）
    latest: dict[str, tuple[bool, str]] = {}
    for s in storage.load_all(SKILL):
        if s.get("mode") != mode:
            continue
        for i, m in s["marks"].items():
            latest.setdefault(i, (m["ok"], s["created"][:10]))
    manual = _review_ids()
    items = []
    for it in drills.load(SKILL)["items"]:
        ok_date = latest.get(it["id"])
        if ok_date and not ok_date[0]:
            items.append({**_with_audio(it), "reason": ok_date[1] + " ×"})
        elif it["id"] in manual["ids"]:
            items.append({**_with_audio(it), "reason": "復習"})
    return {"updated": manual.get("updated"), "items": items}


@router.get("/marks/{mode}")
def get_marks(mode: str):
    _check_mode(mode)
    return marks.get(SKILL, mode)


class MarkBody(BaseModel):
    ok: bool


@router.put("/marks/{mode}/{item_id}")
def put_mark(mode: str, item_id: str, body: MarkBody):
    _check_mode(mode)
    if item_id not in items_by_id():
        raise ApiError("単語が見つかりません", 404)
    return marks.put(SKILL, mode, MODES[mode], item_id, body.ok)
