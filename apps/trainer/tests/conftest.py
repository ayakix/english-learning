import dataclasses

import pytest

from trainer import config, storage


@pytest.fixture(autouse=True)
def practice_dir(tmp_path, monkeypatch):
    """本物の練習ログを汚さないよう、テストごとに一時ディレクトリへ向ける"""
    s = dataclasses.replace(config.settings, practice_dir=tmp_path)
    monkeypatch.setattr(storage, "settings", s)
    return tmp_path
