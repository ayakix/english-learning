"""コマンドライン

  photo-shadowing                 サーバーを起動してブラウザを開く
  photo-shadowing serve --no-browser
  photo-shadowing summary [YYYY-MM-DD]   その日の練習結果を Markdown で出力
"""
import argparse
import threading
import time
import webbrowser

from .config import WEB_DIST, settings


def serve(open_browser: bool) -> None:
    import uvicorn

    url = "http://localhost:%d" % settings.port
    ok = lambda v: "OK" if v else "未設定"
    print("=" * 56)
    print("  Photo Shadowing  →  %s" % url)
    print("  Gemini: %s / ElevenLabs: %s / Unsplash: %s" % (
        ok(settings.gemini_key), ok(settings.eleven_key), "OK" if settings.unsplash_key else "未設定(代替写真)"))
    print("  練習ログ: %s" % settings.practice_dir)
    if not WEB_DIST.exists():
        print("  ※ web/dist がありません。先に `npm run build`（web/）を実行してください")
    print("  終了するには Ctrl+C")
    print("=" * 56)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("photo_shadowing.server:app", host="127.0.0.1", port=settings.port, log_level="warning")


def main() -> None:
    p = argparse.ArgumentParser(prog="photo-shadowing")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="サーバーを起動する（既定）")
    s.add_argument("--no-browser", action="store_true")
    m = sub.add_parser("summary", help="その日の練習結果を Markdown で出力する")
    m.add_argument("date", nargs="?", default=time.strftime("%Y-%m-%d"))
    args = p.parse_args()

    if args.cmd == "summary":
        from . import summary

        print(summary.render(args.date))
    else:
        serve(open_browser=not getattr(args, "no_browser", False))


if __name__ == "__main__":
    main()
