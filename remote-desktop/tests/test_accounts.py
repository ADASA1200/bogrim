"""בדיקות ל-accounts.py: חשבון + פנקס כתובות משותף בצד שרת האיתות."""
import pytest

from rdesk.accounts import AccountStore


@pytest.fixture
def store(tmp_path):
    return AccountStore(tmp_path / "accounts.json")


def test_register_and_verify(store):
    store.register("alice", "a-long-enough-password")
    assert store.verify("alice", "a-long-enough-password")
    assert not store.verify("alice", "wrong-password")
    assert not store.verify("bob", "a-long-enough-password")


def test_register_rejects_short_password(store):
    with pytest.raises(ValueError, match="password_too_short"):
        store.register("alice", "short")


def test_register_rejects_bad_username(store):
    for bad in ("", "a", "has space", "has/slash"):
        with pytest.raises(ValueError, match="bad_username"):
            store.register(bad, "a-long-enough-password")


def test_register_rejects_duplicate_username(store):
    store.register("alice", "a-long-enough-password")
    with pytest.raises(ValueError, match="username_taken"):
        store.register("alice", "another-long-password")


def test_contacts_round_trip(store):
    store.register("alice", "a-long-enough-password")
    assert store.get_contacts("alice") == []
    store.set_contacts("alice", [{"id": "123-456-789", "label": "אמא"}, {"id": "999888777", "label": "עבודה"}])
    assert store.get_contacts("alice") == [
        {"id": "123456789", "label": "אמא"},
        {"id": "999888777", "label": "עבודה"},
    ]


def test_contacts_persist_across_instances(tmp_path):
    path = tmp_path / "accounts.json"
    AccountStore(path).register("alice", "a-long-enough-password")
    store2 = AccountStore(path)
    store2.set_contacts("alice", [{"id": "111222333", "label": "x"}])

    store3 = AccountStore(path)
    assert store3.verify("alice", "a-long-enough-password")
    assert store3.get_contacts("alice") == [{"id": "111222333", "label": "x"}]


def test_set_contacts_unknown_account_raises(store):
    with pytest.raises(ValueError, match="no_such_account"):
        store.set_contacts("ghost", [])


def test_password_hash_uses_per_account_salt(tmp_path):
    path = tmp_path / "accounts.json"
    s = AccountStore(path)
    s.register("alice", "same-password-123")
    s.register("bob", "same-password-123")
    import json
    data = json.loads(path.read_text("utf-8"))
    assert data["alice"]["salt"] != data["bob"]["salt"]
    assert data["alice"]["hash"] != data["bob"]["hash"]
