"""教材の取得元（VOA など）

取得元ごとに 1 モジュールにし、記事（本文・音声・クレジット・ライセンス）を同じ形で返す。
後から ELLLO などを足すときに、問題を作る側（voa.py など）を変えずに済むようにするため。

記事の形：
  url, title, published, paragraphs: [{"text", "heading": bool}], glossary: [{"word", "definition"}],
  credit, license, commit_text: bool, audio_url
commit_text が False の取得元（著作権のある教材）は、本文を session.json に入れない想定。
"""
