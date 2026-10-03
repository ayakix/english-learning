"""スピーキングテスト用のストック（写真・模範解答・手本音声）

写真は Unsplash から Claude が選び、模範解答も Claude が書く（TOEIC Speaking の写真描写の解答例に合わせ、
60〜80 語・現在進行形で場所 → 中心の人物 → 周り → 背景 の順に描写する）。
このモジュールは、写真の取得と ElevenLabs での手本音声づくりだけを行う。

保存先：content/speaking/
  items.json      … 写真の取得元・クレジット・模範解答・声・手本音声の区間（git 管理する）
  <id>/photo.jpg  … 写真（ライセンスと容量の理由で git 管理外。URL から取り直せる）
  <id>/model_*.mp3 … 手本音声（git 管理外）
"""
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import elevenlabs, http, photos
from .config import REPO_ROOT, settings
from .stock import TTS_WORKERS, load_topics

STOCK_DIR = REPO_ROOT / "content" / "speaking"
ITEMS = STOCK_DIR / "items.json"


def load_items() -> list[dict]:
    return json.loads(ITEMS.read_text(encoding="utf-8")) if ITEMS.exists() else []


def save_items(items: list[dict]) -> None:
    ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def item_dir(item: dict) -> Path:
    return STOCK_DIR / item["id"]


def ensure_photo(item: dict) -> Path:
    p = item_dir(item) / "photo.jpg"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        photos.download(item["photo"]["url"], p)
    return p


def ensure_audio(item: dict) -> bool:
    tts = item.get("tts")
    return bool(tts) and (item_dir(item) / tts["file"]).exists()


def build_one(item: dict, voices: list[dict]) -> dict:
    """写真を取得し、手本音声を作って item を更新して返す。作成済みの部分は飛ばす"""
    ensure_photo(item)
    if not item.get("download_tracked") and item.get("download_location") and settings.unsplash_key:
        # Unsplash API ガイドライン：写真を使うときに download エンドポイントを呼ぶ
        try:
            http.request("GET", item["download_location"],
                         headers={"Authorization": "Client-ID " + settings.unsplash_key}, timeout=10)
            item["download_tracked"] = True
        except http.ApiError:
            pass
    if not ensure_audio(item):
        # 声は ID から決まる乱数で選ぶ（作り直しても同じ声になるように）
        voice = random.Random(item["id"]).choice(voices)
        item["voice"] = {"name": voice["name"], "id": voice["id"]}
        item["tts"] = elevenlabs.synthesize(item_dir(item), item["answer"], voice["id"], previous=item.get("tts"))
    return item


def build_all() -> None:
    items = load_items()
    voices = load_topics()["voices"]
    todo = [it for it in items if not ensure_audio(it) or not (item_dir(it) / "photo.jpg").exists()]

    def one(it):
        try:
            build_one(it, voices)
            print("%s %s %s" % (it["id"], it["voice"]["name"], it["photo"]["credit"]["name"]), flush=True)
        except Exception as e:  # 1 件の失敗で全体を止めない（同じコマンドを流し直せば残りだけ作る）
            print("%s 失敗: %s" % (it["id"], str(e)[:200]), flush=True)

    with ThreadPoolExecutor(TTS_WORKERS) as ex:
        list(ex.map(one, todo))
    save_items(items)
    print("完了 %d / %d" % (sum(1 for it in items if ensure_audio(it)), len(items)))
