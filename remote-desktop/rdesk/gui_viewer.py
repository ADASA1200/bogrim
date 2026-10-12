"""חלון הצופה (tkinter): מתחבר למארח, מציג את המסך ושולח עכבר ומקלדת."""
from __future__ import annotations

import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from . import config, protocol as P, strings as S, theme
from .aio import AsyncRunner
from .viewer import ViewerClient

# keysym של tkinter -> שם מקש בפרוטוקול
KEYSYM = {
    "Return": "enter", "KP_Enter": "enter", "Tab": "tab", "space": "space",
    "BackSpace": "backspace", "Delete": "delete", "Escape": "esc", "Home": "home",
    "End": "end", "Prior": "page_up", "Next": "page_down", "Up": "up", "Down": "down",
    "Left": "left", "Right": "right", "Insert": "insert",
    "Shift_L": "shift", "Shift_R": "shift", "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt", "Super_L": "cmd", "Super_R": "cmd", "Win_L": "cmd",
    "Caps_Lock": "caps_lock", "Menu": "menu", "Print": "print_screen", "Pause": "pause",
    "Num_Lock": "num_lock", "Scroll_Lock": "scroll_lock",
    **{f"F{i}": f"f{i}" for i in range(1, 25)},
}
PUNCT = {
    "slash": "/", "backslash": "\\", "period": ".", "comma": ",", "semicolon": ";",
    "apostrophe": "'", "bracketleft": "[", "bracketright": "]", "minus": "-",
    "equal": "=", "grave": "`", "plus": "+", "underscore": "_", "colon": ":",
    "quotedbl": '"', "less": "<", "greater": ">", "question": "?", "bar": "|",
    "braceleft": "{", "braceright": "}", "asciitilde": "~", "exclam": "!", "at": "@",
    "numbersign": "#", "dollar": "$", "percent": "%", "asciicircum": "^",
    "ampersand": "&", "asterisk": "*", "parenleft": "(", "parenright": ")",
}
R = S.rtl
BUTTON = {1: "left", 2: "middle", 3: "right"}
CTRL_ALT = 0x4 | 0x20000 | 0x8   # Control, Alt (Windows), Mod1


def key_name(ev) -> str | None:
    ks = ev.keysym
    if ks in KEYSYM:
        return KEYSYM[ks]
    if ev.state & CTRL_ALT:                   # בשילוב Ctrl/Alt event.char הוא תו בקרה
        return PUNCT.get(ks, ks.lower() if len(ks) == 1 else None)
    if ev.char and ev.char.isprintable():     # כולל עברית וכל פריסת מקלדת
        return ev.char
    return PUNCT.get(ks, ks if len(ks) == 1 else None)


class ViewerApp:
    def __init__(self, server: str | None = None, runner: AsyncRunner | None = None,
                 master=None, preset: tuple[str, str] | None = None) -> None:
        """master: חלון האב כשהצופה נפתח מתוך האפליקציה הראשית; preset: (מזהה, סיסמה)."""
        self.cfg = config.load()
        self.server = config.server_url(server)
        self.runner = runner or AsyncRunner()
        self.events: queue.Queue = queue.Queue()
        self.client: ViewerClient | None = None
        self.master = master
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        theme.apply(self.root)   # לא עושה כלום אם master is not None (Toplevel יורש מה-root)
        self.root.title(R(S.V_TITLE))
        self.root.geometry("460x360")
        self._last_move = 0.0
        self._photo = None
        self._shown_seq = -1
        self._rect = (0, 0, 1, 1)        # x0, y0, w, h של התמונה בתוך הקנבס
        self._build_connect()
        self.root.after(30, self._tick)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        if preset:
            self.id_cb.set(P.format_id(preset[0]))
            self.pw.insert(0, preset[1])
            self.root.after(200, self._connect)

    # ---------------------------------------------------------- מסך חיבור
    def _build_connect(self) -> None:
        self.cf = ttk.Frame(self.root, padding=16)
        self.cf.pack(fill="both", expand=True)
        self.cf.columnconfigure(0, weight=1)
        ttk.Label(self.cf, text=R(S.V_HEADER), font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 10))
        ttk.Label(self.cf, text=R(S.V_ID)).grid(row=1, column=1, sticky="e")
        self.id_cb = ttk.Combobox(self.cf, values=self.cfg.get("recent", []), width=26, justify="right")
        self.id_cb.grid(row=1, column=0, pady=4, sticky="e")
        ttk.Label(self.cf, text=R(S.V_PASSWORD)).grid(row=2, column=1, sticky="e")
        self.pw = ttk.Entry(self.cf, show="•", width=28, justify="right")
        self.pw.grid(row=2, column=0, pady=4, sticky="e")
        ttk.Label(self.cf, text=R(S.V_PW_HINT), foreground="gray", justify="right",
                  wraplength=400).grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Label(self.cf, text=R(S.V_SERVER)).grid(row=4, column=1, sticky="e")
        self.srv = ttk.Entry(self.cf, width=28)
        self.srv.insert(0, self.cfg.get("server", self.server))
        self.srv.grid(row=4, column=0, pady=4, sticky="e")
        self.btn = ttk.Button(self.cf, text=R(S.V_CONNECT), command=self._connect)
        self.btn.grid(row=5, column=0, columnspan=2, pady=10)
        self.msg = ttk.Label(self.cf, text="", foreground="gray", wraplength=400, justify="right")
        self.msg.grid(row=6, column=0, columnspan=2)
        self.id_cb.bind("<Return>", lambda e: self._connect())
        self.pw.bind("<Return>", lambda e: self._connect())

    def _connect(self) -> None:
        host_id, pw, srv = self.id_cb.get(), self.pw.get(), self.srv.get().strip()
        if not P.clean_id(host_id):
            self.msg.configure(text=R(S.V_NEED_FIELDS), foreground="red")
            return
        self.btn.state(["disabled"])
        self.msg.configure(text=R(S.V_CONNECTING if pw else S.V_WAIT_APPROVAL), foreground="gray")
        self.client = ViewerClient(
            srv, on_event=lambda k, **kw: self.events.put((k, kw)))

        def done(fut):
            exc = fut.exception()
            self.events.put(("connect_failed" if exc else "connect_ok",
                             {"exc": exc, "id": host_id, "srv": srv}))
        self.runner.submit(self.client.connect(host_id, pw), done)

    # ------------------------------------------------------------ סשן
    def _build_session(self) -> None:
        self.cf.pack_forget()
        self.root.geometry("1100x700")
        bar = ttk.Frame(self.root)
        bar.pack(fill="x")
        self.bar = bar
        self.view_only = tk.BooleanVar(value=not self.client.perms.control)
        ttk.Checkbutton(bar, text=R(S.V_VIEW_ONLY), variable=self.view_only).pack(side="left", padx=4)
        if len(self.client.monitors) > 1:
            self.mon = ttk.Combobox(bar, state="readonly", width=16, values=[
                R(S.V_MONITOR.format(i=m['index'], w=m['width'], h=m['height'])) for m in self.client.monitors])
            self.mon.current(0)
            self.mon.bind("<<ComboboxSelected>>", self._on_monitor)
            self.mon.pack(side="left", padx=4)
        ttk.Label(bar, text=R(S.V_QUALITY)).pack(side="left")
        self.q = ttk.Combobox(bar, state="readonly", width=10,
                              values=[R(S.V_Q_HIGH), R(S.V_Q_MID), R(S.V_Q_LOW)])
        self.q.current(0)
        self.q.bind("<<ComboboxSelected>>", self._on_quality)
        self.q.pack(side="left", padx=4)
        ttk.Button(bar, text=R(S.V_SEND_FILE), command=self._send_file).pack(side="left", padx=4)
        ttk.Button(bar, text=R(S.V_CHAT), command=self._toggle_chat).pack(side="left", padx=4)
        ttk.Button(bar, text=R(S.V_FULLSCREEN), command=self._fullscreen).pack(side="left", padx=4)
        ttk.Button(bar, text=R(S.V_DISCONNECT), command=self._disconnect).pack(side="right", padx=4)
        self.info = ttk.Label(bar, text="", foreground="gray")
        self.info.pack(side="right", padx=8)
        self.code = ttk.Label(bar, text=R(S.V_CODE.format(code=self.client.code)), foreground="gray")
        self.code.pack(side="right", padx=8)

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<Motion>", lambda e: self._mouse("mm", e))
        for n, name in BUTTON.items():
            c.bind(f"<ButtonPress-{n}>", lambda e, b=name: (c.focus_set(), self._mouse("md", e, b)))
            c.bind(f"<ButtonRelease-{n}>", lambda e, b=name: self._mouse("mu", e, b))
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Button-4>", lambda e: self._send({"t": "ms", "dx": 0, "dy": 1}))
        c.bind("<Button-5>", lambda e: self._send({"t": "ms", "dx": 0, "dy": -1}))
        c.bind("<KeyPress>", lambda e: self._key("kd", e))
        c.bind("<KeyRelease>", lambda e: self._key("ku", e))
        c.bind("<Tab>", lambda e: "break")
        c.focus_set()
        self.chat_win = None
        self._frames = 0
        self._t0 = time.time()

    def _send(self, ev: dict) -> None:
        if not self.view_only.get() and self.client and self.client.connected:
            self.runner.call(self.client.send_input, ev)

    def _norm(self, e):
        x0, y0, w, h = self._rect
        return (min(1.0, max(0.0, (e.x - x0) / max(1, w))),
                min(1.0, max(0.0, (e.y - y0) / max(1, h))))

    def _mouse(self, t: str, e, b: str | None = None) -> None:
        now = time.monotonic()
        if t == "mm" and now - self._last_move < 0.016:     # ~60 אירועים בשנייה
            return
        self._last_move = now
        x, y = self._norm(e)
        ev = {"t": t, "x": round(x, 5), "y": round(y, 5)}
        if b:
            ev["b"] = b
        self._send(ev)

    def _wheel(self, e) -> None:
        step = 1 if e.delta > 0 else -1
        self._send({"t": "ms", "dx": 0, "dy": step * max(1, abs(e.delta) // 120)})

    def _key(self, t: str, e):
        name = key_name(e)
        if name:
            self._send({"t": t, "k": name})
        return "break"

    def _on_monitor(self, _e=None) -> None:
        idx = self.client.monitors[self.mon.current()]["index"]
        self.runner.call(self.client.set_monitor, idx)

    def _on_quality(self, _e=None) -> None:
        fps, scale = {0: (24, 1.0), 1: (15, 0.7), 2: (8, 0.5)}[self.q.current()]
        self.runner.call(self.client.set_quality, fps, scale)

    def _send_file(self) -> None:
        path = filedialog.askopenfilename()
        if path:
            self.runner.submit(self.client.send_file(path))

    def _fullscreen(self) -> None:
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def _toggle_chat(self) -> None:
        if self.chat_win and self.chat_win.winfo_exists():
            self.chat_win.destroy(); return
        w = self.chat_win = tk.Toplevel(self.root)
        theme.style_toplevel(w)
        w.title(R(S.V_CHAT_TITLE)); w.geometry("300x360")
        self.chat_log = scrolledtext.ScrolledText(w, state="disabled", height=14)
        theme.style_classic(self.chat_log)
        self.chat_log.pack(fill="both", expand=True)
        ent = ttk.Entry(w, justify="right"); ent.pack(fill="x")

        def send(_e=None):
            t = ent.get().strip()
            if t:
                self.runner.call(self.client.send_chat, t)
                self._chat_line(S.V_ME + t); ent.delete(0, "end")
        ent.bind("<Return>", send)

    def _chat_line(self, line: str) -> None:
        if self.chat_win and self.chat_win.winfo_exists():
            self.chat_log.configure(state="normal")
            self.chat_log.insert("end", R(line) + "\n"); self.chat_log.see("end")
            self.chat_log.configure(state="disabled")

    def _disconnect(self) -> None:
        if self.client:
            self.runner.submit(self.client.disconnect())

    def _quit(self) -> None:
        try:
            if self.client:
                self.runner.submit(self.client.disconnect()).result(2)
        except Exception:
            pass
        self.root.destroy()

    # ------------------------------------------------------- ציור וידאו
    def _tick(self) -> None:
        try:
            while True:
                self._handle(*self.events.get_nowait())
        except queue.Empty:
            pass
        c = self.client
        if (c and c.connected and hasattr(self, "canvas") and c.latest_frame is not None
                and c.frame_seq != self._shown_seq):
            self._shown_seq = c.frame_seq
            self._draw(c.latest_frame)
        self.root.after(30, self._tick)

    def _draw(self, arr) -> None:
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        h, w = arr.shape[:2]
        k = min(cw / w, ch / h)
        nw, nh = max(1, int(w * k)), max(1, int(h * k))
        img = Image.fromarray(arr).resize((nw, nh), Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(img)
        x0, y0 = (cw - nw) // 2, (ch - nh) // 2
        self._rect = (x0, y0, nw, nh)
        self.canvas.delete("all")
        self.canvas.create_image(x0, y0, anchor="nw", image=self._photo)
        self._frames += 1
        if self._frames % 30 == 0:
            fps = self._frames / max(0.001, time.time() - self._t0)
            self.info.configure(text=f"{w}x{h} · {fps:.0f} FPS")

    def _handle(self, kind: str, kw: dict) -> None:
        if kind == "connect_ok":
            recent = [kw["id"]] + [r for r in self.cfg.get("recent", []) if r != kw["id"]]
            self.cfg.update(recent=recent[:10], server=kw["srv"])
            config.save(self.cfg)
            self._build_session()
        elif kind == "connect_failed":
            exc = kw["exc"]
            self.msg.configure(
                text=R(S.V_FAILED + S.reason(str(exc) or type(exc).__name__)), foreground="red")
            self.btn.state(["!disabled"])
        elif kind == "chat":
            self._chat_line(S.V_HOST + kw["text"])
        elif kind == "perms":
            if not kw["perms"]["control"]:
                self.view_only.set(True)
        elif kind == "closed":
            messagebox.showinfo(S.V_CLOSED_TITLE, R(S.V_CLOSED + S.reason(kw.get("reason"))))
            self.root.destroy()
        elif kind == "file_received":
            messagebox.showinfo(S.V_CLOSED_TITLE, R(S.V_FILE_IN) + kw["path"])
        elif kind == "file_error":
            messagebox.showwarning(S.V_CLOSED_TITLE, R(S.V_FILE_ERR + S.reason(kw.get("reason"))))

    def run(self) -> None:
        if self.master is None:
            self.root.mainloop()
