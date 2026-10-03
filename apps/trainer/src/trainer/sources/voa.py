"""VOA Learning English から記事を取得する

使うのは VOA の記者が書いた記事だけ。米政府の職員が職務で作ったものはパブリックドメインなので、
本文を公開リポジトリの session.json に残せる。
AP・ロイター・AFP の記事を VOA が書き直したものは通信社の著作権が残るため、末尾のクレジットで除く。
"""
import html
import random
import re

from .. import http
from ..http import ApiError

BASE = "https://learningenglish.voanews.com"
NAME = "VOA Learning English"
LICENSE = "public-domain"

# セクション（一覧ページの ID）。VOA 独自の記事の割合が高い順（2026-10 に抜き取りで確認）
ZONES = {
    "words": ("987", "Words and Their Stories"),
    "health": ("955", "Health & Lifestyle"),
    "arts": ("986", "Arts & Culture"),
    "stories": ("1581", "American Stories"),
    "science": ("1579", "Science & Technology"),
}
# 一覧は 100 ページほどで打ち切られる
MAX_PAGE = 100

WIRE_RE = re.compile(r"Associated Press|\bAP\b|Reuters|AFP|Agence France|news reports|other sources", re.I)
VOA_RE = re.compile(r"for (VOA )?Learning English|VOA News", re.I)
CREDIT_RE = re.compile(r"\b(wrote|reported|adapted)\b.*\b(Learning English|story)\b", re.I)
AUDIO_RE = re.compile(r"https://voa-audio[^\"&\s]+?_hq\.mp3")
# 音声プレーヤーの代替テキストなど、本文ではない段落
NOISE = {"No media source currently available"}
HEADERS = {"User-Agent": "Mozilla/5.0 (english-learning trainer)"}


def _get(url: str) -> str:
    return http.request("GET", url, headers=HEADERS, timeout=30).text


def _text(fragment: str) -> str:
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())
    # <strong>graduation</strong>, のようにタグの直後に句読点が来ると空白が入るので詰める
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def is_original(credit: str) -> bool:
    """クレジットが VOA の記者で、通信社の名前を含まないか"""
    return bool(credit) and bool(VOA_RE.search(credit)) and not WIRE_RE.search(credit)


def parse(url: str, page: str) -> dict | None:
    """記事ページ → 記事。本文・音声・クレジットのどれかが取れなければ None"""
    start = page.find('<div class="wsw"')
    audio = AUDIO_RE.search(page)
    if start < 0 or not audio:
        return None
    body = page[start:]
    # 「Words in This Story」（VOA が付けている語彙の説明）の前までが本文
    gloss_at = body.find("Words in This Story")
    main, gloss = (body[:gloss_at], body[gloss_at:]) if gloss_at >= 0 else (body, "")

    paragraphs, credit = [], ""
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", main, re.S):
        raw, text = m.group(1), _text(m.group(1))
        if not text or text in NOISE or set(text) <= set("_-–— "):
            continue
        if CREDIT_RE.search(text) and len(text) < 300:
            credit = text
            break
        # <strong> だけの段落は小見出し（音声では読まれない）
        heading = bool(re.fullmatch(r"\s*<strong>.*</strong>\s*", raw, re.S))
        paragraphs.append({"text": text, "heading": heading})

    glossary = []
    if gloss:
        end = gloss.find("</div>")
        for m in re.finditer(r"<p[^>]*>\s*<strong>(.*?)</strong>(.*?)</p>", gloss[:end], re.S):
            word, definition = _text(m.group(1)), _text(m.group(2)).lstrip("–—- ")
            if word:
                glossary.append({"word": word, "definition": definition})

    title = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    date = re.search(r'"datePublished":"(\d{4}-\d{2}-\d{2})', page)
    if not paragraphs or not credit:
        return None
    return {"url": url, "title": _text(title.group(1)) if title else "", "published": date.group(1) if date else "",
            "paragraphs": paragraphs, "glossary": glossary, "credit": credit, "license": LICENSE,
            "commit_text": True, "site": NAME, "audio_url": audio.group(0)}


def find_article(zone: str, exclude: set[str], min_words: int = 200, max_words: int = 1000,
                 tries: int = 12) -> dict:
    """セクションからランダムに、VOA 独自・音声あり・未使用の記事を 1 本選ぶ"""
    keys = list(ZONES) if zone not in ZONES else [zone]
    checked = 0
    for _ in range(4):
        zid = ZONES[random.choice(keys)][0]
        listing = _get("%s/z/%s?p=%d" % (BASE, zid, random.randrange(MAX_PAGE)))
        urls = [u for u in sorted(set(re.findall(r'href="(/a/[a-z0-9-]+/\d+\.html)"', listing)))
                if BASE + u not in exclude]
        random.shuffle(urls)
        for path in urls:
            if checked >= tries:
                break
            checked += 1
            try:
                a = parse(BASE + path, _get(BASE + path))
            except ApiError:
                continue
            if not a or not is_original(a["credit"]):
                continue
            words = sum(len(p["text"].split()) for p in a["paragraphs"] if not p["heading"])
            if min_words <= words <= max_words:
                return a
    raise ApiError("条件に合う VOA の記事が見つかりませんでした。もう一度試してください", 502)
