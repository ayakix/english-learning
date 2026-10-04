"""発音：リンキング（音のつながり）の例題

例題（フレーズ・聞こえ方・例文）は Claude が書き、content/linking/items.json に置く。
このモジュールは、ElevenLabs での音声づくりと、画面へのデータ・音声の配信だけを行う。

保存先：content/linking/
  items.json         … 型の説明・例題・声・音声の区間（git 管理する）
  <id>/model_*.mp3   … フレーズと例文の音声（git 管理外）
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

STOCK_DIR = REPO_ROOT / "content" / "linking"
ITEMS = STOCK_DIR / "items.json"

router = APIRouter(prefix="/api/linking")


def load() -> dict:
    return json.loads(ITEMS.read_text(encoding="utf-8")) if ITEMS.exists() else {"types": [], "items": []}


def save(data: dict) -> None:
    ITEMS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def item_dir(item: dict) -> Path:
    return STOCK_DIR / item["id"]


def has_audio(item: dict) -> bool:
    return all(item.get(k) and (item_dir(item) / item[k]["file"]).exists() for k in ("tts", "tts_sentence"))


def us_voices() -> list[dict]:
    # t の弾音化など、アメリカ英語の特徴が例どおりに出るよう米国の声だけを使う
    return [v for v in load_topics()["voices"] if v.get("accent") == "US"]


def build_one(item: dict, voices: list[dict]) -> dict:
    """フレーズと例文の音声を作って item を更新して返す。作成済みのものは飛ばす"""
    # 声は ID から決まる乱数で選ぶ（作り直しても同じ声になるように）
    voice = random.Random(item["id"]).choice(voices)
    item["voice"] = {"name": voice["name"], "id": voice["id"]}
    d = item_dir(item)
    d.mkdir(parents=True, exist_ok=True)
    item["tts"] = elevenlabs.synthesize(d, item["text"], voice["id"], previous=item.get("tts"))
    item["tts_sentence"] = elevenlabs.synthesize(d, item["sentence_text"], voice["id"], previous=item.get("tts_sentence"))
    return item


def build_all() -> None:
    data = load()
    voices = us_voices()
    todo = [it for it in data["items"] if not has_audio(it)]

    def one(it):
        try:
            build_one(it, voices)
            print("%s %s %s" % (it["id"], it["voice"]["name"], it["text"]), flush=True)
        except Exception as e:  # 1 件の失敗で全体を止めない（同じコマンドを流し直せば残りだけ作る）
            print("%s 失敗: %s" % (it["id"], str(e)[:200]), flush=True)

    with ThreadPoolExecutor(TTS_WORKERS) as ex:
        list(ex.map(one, todo))
    save(data)
    print("完了 %d / %d" % (sum(1 for it in data["items"] if has_audio(it)), len(data["items"])))


@router.get("")
def get_linking():
    """型と例題を返す。音声がまだ無い例題は再生できないので除く"""
    data = load()
    keep = ("id", "type", "phrase", "text", "kana", "sentence", "sentence_text", "voice")
    items = [{**{k: it[k] for k in keep if k in it}, "audio": it["tts"]["file"],
              "audio_sentence": it["tts_sentence"]["file"]} for it in data["items"] if has_audio(it)]
    return {"types": data["types"], "items": items}


@router.get("/audio/{item_id}/{name}")
def get_audio(item_id: str, name: str):
    # パスの組み立てに使うので、ID とファイル名は items.json にあるものだけ受け付ける
    it = next((it for it in load()["items"] if it["id"] == item_id), None)
    if not it or name not in {(it.get(k) or {}).get("file") for k in ("tts", "tts_sentence")}:
        raise ApiError("not found", 404)
    p = item_dir(it) / name
    if not p.exists():
        raise ApiError("not found", 404)
    return FileResponse(p, headers={"Cache-Control": "max-age=86400"})
