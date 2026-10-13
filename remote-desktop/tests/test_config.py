"""בדיקות לפרופילי הרשאה שמורים (אמון תמידי למזהה ספציפי) ב-config.py."""
from rdesk import config, protocol as P


def test_get_trusted_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load()
    assert config.get_trusted(cfg, "123456789") is None


def test_set_and_get_trusted_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load()
    perms = P.Permissions(control=True, clipboard=False, files=True, chat=True)
    config.set_trusted(cfg, "v1a2b3c4d5e6", perms)

    reloaded = config.load()
    got = config.get_trusted(reloaded, "v1a2b3c4d5e6")
    assert got == perms
    assert list(config.list_trusted(reloaded).keys()) == ["v1a2b3c4d5e6"]


def test_remove_trusted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load()
    config.set_trusted(cfg, "v1a2b3c4d5e6", P.Permissions())
    config.remove_trusted(cfg, "v1a2b3c4d5e6")

    reloaded = config.load()
    assert config.get_trusted(reloaded, "v1a2b3c4d5e6") is None
    assert config.list_trusted(reloaded) == {}
