"""設定とパス

API キーは french-learning と同じく、リポジトリ直下の .env に一本化する。
アプリごとに .env を持つと、スクリプトなど他のツールとキーが二重管理になるため。
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_DIR.parents[1]
WEB_DIST = APP_DIR / "web" / "dist"

load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_key: str
    eleven_key: str
    unsplash_key: str
    gemini_model: str
    eleven_model: str
    eleven_voice: str
    port: int
    # 練習ログはアプリのコードと分けて、journal と並ぶ学習記録として扱う（技能ごとのサブディレクトリを持つ）
    practice_dir: Path


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        gemini_key=env("GEMINI_API_KEY", ""),
        eleven_key=env("ELEVENLABS_API_KEY", ""),
        unsplash_key=env("UNSPLASH_ACCESS_KEY", ""),
        gemini_model=env("GEMINI_MODEL") or "gemini-flash-latest",
        eleven_model=env("ELEVENLABS_MODEL") or "eleven_multilingual_v2",
        eleven_voice=env("ELEVENLABS_VOICE_ID", ""),
        port=int(env("PORT") or 8765),
        practice_dir=Path(env("PRACTICE_DIR") or REPO_ROOT / "practice"),
    )


settings = load_settings()
