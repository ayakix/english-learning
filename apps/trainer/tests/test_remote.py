import json
import time

from fastapi.testclient import TestClient

from trainer import activity, server, summary

client = TestClient(server.app)
REMOTE = {"Cf-Access-Authenticated-User-Email": "x@example.com"}


def test_noindex_header():
    r = client.get("/api/config")
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_activity_ignored_without_header(practice_dir):
    r = client.post("/api/activity")
    assert r.status_code == 204
    assert not (practice_dir / "activity").exists()


def test_activity_recorded_once_per_minute(practice_dir):
    assert client.post("/api/activity", headers=REMOTE).status_code == 204
    client.post("/api/activity", headers=REMOTE)
    today = time.strftime("%Y-%m-%d")
    p = practice_dir / "activity" / today[:4] / today[5:7] / ("%s.json" % today)
    data = json.loads(p.read_text())
    # 同じ分に 2 回届いても 1 件だけ（ミリ秒単位の境目をまたいだ場合は 2 件になりうる）
    assert data["date"] == today and 1 <= len(data["minutes"]) <= 2


def _write(practice_dir, date, minutes):
    p = practice_dir / "activity" / date[:4] / date[5:7] / ("%s.json" % date)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"date": date, "minutes": minutes}))


def test_sessions_split_by_gap(practice_dir):
    _write(practice_dir, "2026-10-09", ["10:00", "10:01", "10:02", "10:20"])
    assert activity.sessions("2026-10-09") == [
        {"start": "10:00", "end": "10:03", "minutes": 3},
        {"start": "10:20", "end": "10:21", "minutes": 1},
    ]


def test_sessions_gap_boundary(practice_dir):
    # 間がちょうど 10 分なら同じセッション
    _write(practice_dir, "2026-10-09", ["10:00", "10:10"])
    assert activity.sessions("2026-10-09") == [{"start": "10:00", "end": "10:11", "minutes": 11}]


def test_summary_shows_remote_sessions(practice_dir):
    _write(practice_dir, "2026-10-09", ["08:15", "08:16"])
    out = summary.render("2026-10-09")
    assert "## 外からの練習" in out and "08:15–08:17（2 分）" in out
    assert "練習の記録はありません" not in out
