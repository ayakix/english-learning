"""音声つきドリル（復唱・即答・ミニマルペア）のストック

例題は Claude が書き、content/drills/<種類>/items.json に置く。どの種類も
item["audio"] に {枠: {"text"}} を持ち、このモジュールが枠ごとに ElevenLabs で音声を作って file を書き足す。
（復唱・即答は枠 "main" の 1 つ、ミニマルペアは 2 語の "a" と "b"）

保存先：content/drills/<種類>/
  items.json        … 例題・声・音声のファイル名（git 管理する）
  <id>/model_*.mp3  … 音声（git 管理外）
"""
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from . import elevenlabs
from .config import REPO_ROOT
from .http import ApiError
from .stock import TTS_WORKERS, load_topics

STOCK_DIR = REPO_ROOT / "content" / "drills"
KINDS = ("repeats", "short-answers", "minimal-pairs")

router = APIRouter(prefix="/api/drills")


def items_path(kind: str) -> Path:
    if kind not in KINDS:
        raise ApiError("unknown drill: " + kind, 404)
    return STOCK_DIR / kind / "items.json"


def load(kind: str) -> dict:
    p = items_path(kind)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}


def save(kind: str, data: dict) -> None:
    items_path(kind).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def item_dir(kind: str, item: dict) -> Path:
    return STOCK_DIR / kind / item["id"]


def has_audio(kind: str, item: dict) -> bool:
    return all(a.get("file") and (item_dir(kind, item) / a["file"]).exists() for a in item["audio"].values())


def voices_for(data: dict) -> list[dict]:
    # ミニマルペアなど米国の発音にそろえたいものは "us"、聞き慣れを広げたいものは採用済みの声すべて
    voices = load_topics()["voices"]
    return [v for v in voices if v.get("accent") == "US"] if data.get("voices") == "us" else voices


def build_one(kind: str, item: dict, voices: list[dict]) -> dict:
    """枠ごとの音声を作って item を更新して返す。作成済みのものは飛ばす"""
    # 声は ID から決まる乱数で選ぶ（作り直しても同じ声になるように）
    voice = random.Random(kind + item["id"]).choice(voices)
    item["voice"] = {"name": voice["name"], "id": voice["id"]}
    d = item_dir(kind, item)
    d.mkdir(parents=True, exist_ok=True)
    for slot, a in item["audio"].items():
        tts = elevenlabs.synthesize(d, a["text"], voice["id"], previous=a if a.get("file") else None)
        item["audio"][slot] = {"text": a["text"], "file": tts["file"]}
    return item


def build_all(kinds: list[str] | None = None) -> None:
    for kind in kinds or KINDS:
        data = load(kind)
        voices = voices_for(data)
        todo = [it for it in data["items"] if not has_audio(kind, it)]

        def one(it):
            try:
                build_one(kind, it, voices)
                print("%s %s %s" % (it["id"], it["voice"]["name"], " / ".join(a["text"] for a in it["audio"].values())),
                      flush=True)
            except Exception as e:  # 1 件の失敗で全体を止めない（同じコマンドを流し直せば残りだけ作る）
                print("%s 失敗: %s" % (it["id"], str(e)[:200]), flush=True)

        with ThreadPoolExecutor(TTS_WORKERS) as ex:
            list(ex.map(one, todo))
        save(kind, data)
        print("%s 完了 %d / %d" % (kind, sum(1 for it in data["items"] if has_audio(kind, it)), len(data["items"])))


@router.get("/{kind}")
def get_drill(kind: str):
    """例題を返す。音声がまだ無い例題は再生できないので除く"""
    data = load(kind)
    return {**data, "items": [it for it in data["items"] if has_audio(kind, it)]}


@router.get("/{kind}/audio/{item_id}/{name}")
def get_audio(kind: str, item_id: str, name: str):
    # パスの組み立てに使うので、ID とファイル名は items.json にあるものだけ受け付ける
    it = next((it for it in load(kind)["items"] if it["id"] == item_id), None)
    if not it or name not in {a.get("file") for a in it["audio"].values()}:
        raise ApiError("not found", 404)
    p = item_dir(kind, it) / name
    if not p.exists():
        raise ApiError("not found", 404)
    return FileResponse(p, headers={"Cache-Control": "max-age=86400"})
