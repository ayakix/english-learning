"""練習用の写真を取得する

写真は git に入れないため、取得元の URL を session.json に残し、
clone し直した後でも同じ写真を取り直せるようにする。
"""
from pathlib import Path

from . import http
from .config import settings

UTM = "?utm_source=eigo_shadowing&utm_medium=referral"


def pick(query: str = "") -> dict:
    """写真を 1 枚選び、session.json に保存する photo 情報を返す"""
    if not settings.unsplash_key:
        # キー未設定時のフォールバック（Lorem Picsum）
        # ランダムな URL はリダイレクト先が毎回変わるため、リダイレクト後の固定 URL を保存する
        r = http.request("GET", "https://picsum.photos/1600/1067", timeout=60)
        return {"source": "picsum", "url": str(r.url), "credit": {
            "name": "Lorem Picsum", "profile": "https://picsum.photos", "link": "https://picsum.photos", "alt": ""}}

    params = {"orientation": "landscape", "content_filter": "high"}
    if query:
        params["query"] = query
    headers = {"Authorization": "Client-ID " + settings.unsplash_key, "Accept-Version": "v1"}
    p = http.request("GET", "https://api.unsplash.com/photos/random", headers=headers, params=params).json()
    # Unsplash API ガイドライン: 利用時に download エンドポイントを叩く
    try:
        dl = p.get("links", {}).get("download_location")
        if dl:
            http.request("GET", dl, headers=headers, timeout=10)
    except http.ApiError:
        pass
    user = p.get("user", {})
    return {"source": "unsplash", "url": p["urls"]["raw"] + "&w=1600&q=80&fm=jpg&fit=max", "credit": {
        "name": user.get("name", ""),
        "profile": user.get("links", {}).get("html", "") + UTM,
        "link": p.get("links", {}).get("html", "") + UTM,
        "alt": p.get("alt_description") or p.get("description") or "",
    }}


def download(url: str, dest: Path) -> None:
    dest.write_bytes(http.request("GET", url, timeout=60).content)
