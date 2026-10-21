import hmac
import logging
import re
import time

from flask import Flask, Response, request

import actions
import agent
import config
from state import STORE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("server")
app = Flask(__name__)

_fail_times: list[float] = []


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def tts_safe(text: str, limit: int | None = None) -> str:
    """בתשובת ימות '.' ו-'-' מפרידים הודעות, '=' ו-'&' מפרידים הגדרות."""
    t = re.sub(r"[*_`#]", " ", text or "")
    t = t.replace("&", " ו").replace("=", " ").replace("-", " ").replace(".", ",")
    t = re.sub(r"\s+", " ", t).strip()
    limit = limit or config.MAX_REPLY_CHARS
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0]
    return t


def _text(body: str) -> Response:
    return Response(body, content_type="text/plain; charset=utf-8")


def _locked_out() -> bool:
    cutoff = time.time() - config.LOCKOUT_WINDOW_SECONDS
    _fail_times[:] = [t for t in _fail_times if t > cutoff]
    return len(_fail_times) >= config.LOCKOUT_FAILS


def _end(text: str) -> Response:
    return _text(f"id_list_message=t-{tts_safe(text)}&go_to_folder=hangup")


def _ask(st, prefix: str, spec: str, prompt: str) -> Response:
    st.last_expect = st.expect
    st.seq += 1
    st.expect = f"{prefix}{st.seq}"
    body = f"read=t-{tts_safe(prompt)}={st.expect},{spec}"
    st.last_reply = body
    return _text(body)


def ask_pin(st, prompt: str) -> Response:
    return _ask(st, "P", ",8,4,10,NO", prompt)


def ask_chat(st, prompt: str) -> Response:
    return _ask(st, "Q", f",voice,,,,record,{config.SILENCE_SECONDS},{config.MAX_RECORD_SECONDS}", prompt)


@app.get("/healthz")
def healthz():
    return "ok"


@app.route("/yemot", methods=["GET", "POST"])
def yemot():
    p = request.values
    if not _eq(p.get("k", ""), config.URL_SECRET):
        return _end("אין הרשאה")
    call_id = p.get("ApiCallId", "")
    if not call_id:
        return _end("בקשה לא תקינה")

    if p.get("hangup") == "yes":
        STORE.drop(call_id)
        return _text("noop=hangup")

    if actions.normalize_phone(p.get("ApiPhone", "")) != config.OWNER_PHONE:
        log.warning("rejected caller ending ...%s", p.get("ApiPhone", "")[-3:])
        return _end("אין הרשאה")
    if _locked_out():
        return _end("המערכת נעולה זמנית")

    st = STORE.get(call_id)
    with st.lock:
        if st.stage == "start":
            st.stage = "pin"
            return ask_pin(st, "שלום, הקישו את הקוד האישי וסולמית")

        val = p.get(st.expect)
        if val is None and st.last_expect and p.get(st.last_expect) is not None and st.last_reply:
            return _text(st.last_reply)   # בקשה חוזרת, מחזירים את אותה תשובה
        val = (val or "").strip()

        if st.stage == "pin":
            if val and _eq(val, config.PIN):
                st.stage = "chat"
                return ask_chat(st, "שלום, במה אפשר לעזור?")
            st.pin_fails += 1
            _fail_times.append(time.time())
            if st.pin_fails >= config.PIN_ATTEMPTS_PER_CALL or _locked_out():
                return _end("הקוד שגוי, להתראות")
            return ask_pin(st, "הקוד שגוי, נסו שוב")

        if not val:
            st.silent += 1
            if st.silent >= 3:
                return _end("להתראות")
            return ask_chat(st, "לא שמעתי, אפשר לחזור על זה")
        st.silent = 0
        try:
            reply, ended = agent.chat(st, val)
        except Exception:
            log.exception("agent failed")
            return ask_chat(st, "הייתה תקלה, אפשר לנסות שוב")
        return _end(reply) if ended else ask_chat(st, reply)


def create_app():
    config.validate()
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8080)
