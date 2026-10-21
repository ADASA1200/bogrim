import os

os.environ.update(YEMOT_TOKEN="0771234567:x", OWNER_PHONE="0501234567", PIN="1234",
                  URL_SECRET="s" * 20, ANTHROPIC_API_KEY="x", CONTACTS_FILE="/nonexistent")

import pytest

import actions
import agent
import server
import state
import yemot_client

K = "s" * 20


@pytest.fixture(autouse=True)
def fresh():
    server._fail_times.clear()
    state.STORE._calls.clear()


def post(client, **kw):
    base = {"k": K, "ApiCallId": "c1", "ApiPhone": "0501234567"}
    base.update(kw)
    return client.post("/yemot", data=base).get_data(as_text=True)


def test_full_flow(monkeypatch):
    monkeypatch.setattr(agent, "chat", lambda st, text: (f"שמעתי {text}", False))
    c = server.app.test_client()
    r = post(c)
    assert r.startswith("read=t-") and "=P1,,8,4,10,NO" in r
    r = post(c, P1="1234")
    assert "=Q2," in r and ",voice,,,,record,3,30" in r
    r = post(c, P1="1234", Q2="מה השעה")
    assert "שמעתי מה השעה" in r and "=Q3," in r
    # בקשה חוזרת של אותו תור מחזירה את אותה תשובה
    assert post(c, P1="1234", Q2="מה השעה") == r


def test_wrong_pin_locks_call():
    c = server.app.test_client()
    post(c)
    assert "=P2," in post(c, P1="0000")
    assert "=P3," in post(c, P1="0000", P2="1111")
    r = post(c, P1="0000", P2="1111", P3="2222")
    assert r.endswith("go_to_folder=hangup")


def test_global_lockout():
    c = server.app.test_client()
    for i in range(5):
        post(c, ApiCallId=f"x{i}")
        post(c, ApiCallId=f"x{i}", P1="0")
    assert "נעולה" in post(c, ApiCallId="new")


def test_rejects_other_caller_and_bad_secret():
    c = server.app.test_client()
    assert "אין הרשאה" in post(c, ApiPhone="0509999999")
    assert "אין הרשאה" in post(c, k="wrong")


def test_hangup_drops_state():
    c = server.app.test_client()
    post(c)
    assert "c1" in state.STORE._calls
    assert post(c, hangup="yes") == "noop=hangup"
    assert "c1" not in state.STORE._calls


def test_silence_ends_call(monkeypatch):
    c = server.app.test_client()
    post(c)
    post(c, P1="1234")
    assert "=Q3," in post(c, P1="1234", Q2="")
    assert "=Q4," in post(c, P1="1234", Q2="", Q3="")
    assert post(c, P1="1234", Q2="", Q3="", Q4="").endswith("go_to_folder=hangup")


def test_tts_safe():
    s = server.tts_safe("שלום. עולם-יפה = ב&ג\n*מודגש*")
    assert "." not in s and "-" not in s and "=" not in s and "&" not in s and "*" not in s


def test_confirmation_classifier():
    cls = actions.classify_confirmation
    assert cls("כן") == "yes" and cls("כן תשלח") == "yes" and cls("Digits-1") == "yes"
    assert cls("לא") == "no" and cls("לא לא לשלוח") == "no" and cls("Digits-2") == "no"
    assert cls("אולי מחר") == "other" and cls("כנראה") == "other"


def test_phone_helpers():
    assert actions.normalize_phone("+972-50-123-4567") == "0501234567"
    assert actions.normalize_phone("972501234567") == "0501234567"
    assert actions.valid_phone("0501234567") and not actions.valid_phone("123")


def test_pending_requires_yes(monkeypatch):
    sent = []
    monkeypatch.setattr(yemot_client, "send_sms", lambda p, m: sent.append((p, m)))
    st = state.CallState("t")
    assert "ממתין" in actions.stage_sms(st, "0521112222", "היי")
    assert "בוטלה" in actions.resolve_pending(st, "אולי")
    assert sent == []
    actions.stage_sms(st, "0521112222", "היי")
    assert "נשלחה" in actions.resolve_pending(st, "כן")
    assert sent == [("0521112222", "היי")]
    assert actions.resolve_pending(st, "כן") is None   # לא מתבצע פעמיים


def test_bridge_dials_owner_first(monkeypatch):
    calls = []
    monkeypatch.setattr(yemot_client, "bridge_call", lambda a, b: calls.append((a, b)))
    st = state.CallState("t")
    actions.stage_bridge(st, "0521112222")
    actions.resolve_pending(st, "כן")
    assert calls == [("0501234567", "0521112222")]


def test_trim_keeps_tool_pairs():
    msgs = []
    for i in range(20):
        msgs += [{"role": "user", "content": f"u{i}"},
                 {"role": "assistant", "content": [{"type": "tool_use", "id": str(i), "name": "n", "input": {}}]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": str(i), "content": "ok"}]},
                 {"role": "assistant", "content": "t"}]
    out = agent._trim(msgs)
    assert out[0]["role"] == "user" and isinstance(out[0]["content"], str)


class _B:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeClient:
    """מחזיר קודם tool_use ל-send_sms ואז טקסט."""
    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        if self.calls == 1:
            return _B(stop_reason="tool_use", content=[
                _B(type="tool_use", id="t1", name="send_sms", input={"to": "0521112222", "message": "היי"})])
        return _B(stop_reason="end_turn", content=[_B(type="text", text="לשלוח היי? אמור כן")])


def test_agent_tool_loop(monkeypatch):
    monkeypatch.setattr(agent, "_client", _FakeClient())
    st = state.CallState("t")
    text, ended = agent.chat(st, "שלח הודעה")
    assert "כן" in text and not ended
    assert st.pending and st.pending["phone"] == "0521112222"
    assert st.history[-2]["content"][0]["type"] == "tool_result"
