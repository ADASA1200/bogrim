"""בדיקות ליומן החיבורים (connlog.py)."""
from rdesk import config, connlog


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(connlog, "LOG_FILE", tmp_path / "connections.json")


def test_empty_log_is_empty_list(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    assert connlog.recent() == []


def test_start_and_end_entry(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    connlog.start_entry("v1a2b3c4d5e6", "interactive", {"control": True})
    entries = connlog.recent()
    assert len(entries) == 1
    assert entries[0]["peer"] == "v1a2b3c4d5e6"
    assert entries[0]["endedAt"] is None

    connlog.end_last("v1a2b3c4d5e6")
    entries = connlog.recent()
    assert entries[0]["endedAt"] is not None


def test_recent_returns_newest_first(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    connlog.start_entry("111", "interactive", {})
    connlog.start_entry("222", "trusted", {})
    entries = connlog.recent()
    assert [e["peer"] for e in entries] == ["222", "111"]


def test_recent_respects_limit(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    for i in range(5):
        connlog.start_entry(str(i), "interactive", {})
    assert len(connlog.recent(limit=2)) == 2


def test_clear(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    connlog.start_entry("111", "interactive", {})
    connlog.clear()
    assert connlog.recent() == []


def test_max_entries_cap(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(connlog, "MAX_ENTRIES", 3)
    for i in range(5):
        connlog.start_entry(str(i), "interactive", {})
    entries = connlog.recent(limit=100)
    assert len(entries) == 3
    assert [e["peer"] for e in entries] == ["4", "3", "2"]
