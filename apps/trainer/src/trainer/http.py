"""外部 API 呼び出しの共通処理"""
import httpx


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 500):
        super().__init__(msg)
        self.status = status


def request(method: str, url: str, *, headers=None, json=None, params=None, data=None, files=None,
            timeout: float = 90) -> httpx.Response:
    try:
        r = httpx.request(method, url, headers=headers, json=json, params=params, data=data, files=files,
                          timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as e:
        raise ApiError("接続エラー (%s): %s" % (url, e), 502)
    if r.status_code >= 400:
        raise ApiError("%s %s → HTTP %s: %s" % (method, url, r.status_code, r.text[:800]), r.status_code)
    return r
