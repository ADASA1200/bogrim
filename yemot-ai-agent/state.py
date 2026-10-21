import threading
import time
from dataclasses import dataclass, field


@dataclass
class CallState:
    call_id: str
    stage: str = "start"          # start -> pin -> chat
    seq: int = 0                  # מונה לשמות הפרמטרים שמבקשים מימות (P1, Q2 ...)
    expect: str = ""              # שם הפרמטר שממתינים לו עכשיו
    last_expect: str = ""
    last_reply: str = ""
    pin_fails: int = 0
    silent: int = 0
    history: list = field(default_factory=list)
    pending: dict | None = None   # פעולה שממתינה לאישור קולי
    ended: bool = False
    touched: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)


class Store:
    TTL = 60 * 60

    def __init__(self):
        self._calls: dict[str, CallState] = {}
        self._lock = threading.Lock()

    def get(self, call_id: str) -> CallState:
        now = time.time()
        with self._lock:
            for k in [k for k, s in self._calls.items() if now - s.touched > self.TTL]:
                del self._calls[k]
            st = self._calls.get(call_id)
            if st is None:
                st = self._calls[call_id] = CallState(call_id)
            st.touched = now
            return st

    def drop(self, call_id: str):
        with self._lock:
            self._calls.pop(call_id, None)


STORE = Store()
