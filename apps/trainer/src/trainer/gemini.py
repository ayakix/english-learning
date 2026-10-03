"""Gemini の呼び出し（各技能のプロンプトは技能ごとのモジュールに置く）

音声や画像を直接入力できるため、文字起こし・添削・発音評価・教材生成をまとめて Gemini に任せている。
"""
import base64
import json
import re

from . import http
from .config import settings
from .http import ApiError

API = "https://generativelanguage.googleapis.com/v1beta"

# 実際に使えたモデル名。存在しないモデル名を指定されたときのフォールバック先を覚えておく
_model_cache: dict[str, str | None] = {"name": None}

LEVELS = {
    "B1": "CEFR B1 (simple, clear sentences, common vocabulary)",
    "B2": "CEFR B2 (natural, varied sentences, some idiomatic phrases)",
    "C1": "CEFR C1 (sophisticated, vivid, natively fluent)",
}


def level_desc(level: str) -> str:
    return LEVELS.get(level, LEVELS["B2"])


def current_model() -> str:
    return _model_cache["name"] or settings.gemini_model


def _pick_fallback_model() -> str | None:
    raw = http.request("GET", API + "/models", headers={"x-goog-api-key": settings.gemini_key},
                       params={"pageSize": 200}).json()
    names = [m["name"].split("/")[-1] for m in raw.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [n for n in names if "flash" in n and "lite" not in n and "image" not in n
             and "tts" not in n and "live" not in n and "audio" not in n]

    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (float(m.group(1)) if m else 0, "preview" not in n and "exp" not in n)

    flash.sort(key=ver, reverse=True)
    return flash[0] if flash else (names[0] if names else None)


def generate(parts: list, schema: dict | None = None, temperature: float = 0.4):
    if not settings.gemini_key:
        raise ApiError("GEMINI_API_KEY が .env に設定されていません", 400)
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature}}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    model = current_model()
    for attempt in range(2):
        try:
            res = http.request("POST", "%s/models/%s:generateContent" % (API, model),
                               headers={"x-goog-api-key": settings.gemini_key}, json=body, timeout=120).json()
            _model_cache["name"] = model
            break
        except ApiError as e:
            if e.status == 404 and attempt == 0:
                fb = _pick_fallback_model()
                if fb and fb != model:
                    print("[gemini] model %s not found → %s を使用" % (model, fb))
                    model = fb
                    continue
            raise
    try:
        cparts = res["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise ApiError("Gemini から応答がありません: " + json.dumps(res)[:500], 502)
    text = "".join(p.get("text", "") for p in cparts if not p.get("thought"))
    if schema:
        t = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
        return json.loads(t)
    return text.strip()


def inline(mime: str, data: bytes) -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}}


def S(t, **kw):
    """responseSchema を短く書くためのヘルパー"""
    d = {"type": t}
    d.update(kw)
    return d
