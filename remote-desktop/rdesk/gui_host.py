"""חלון המארח (tkinter, עברית): מזהה, גישה ללא נוכחות, אישור חיבורים והרשאות."""
from __future__ import annotations

import asyncio
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import config, protocol as P, strings as S
from .aio import AsyncRunner
from .host import HostService

APPROVAL_TIMEOUT = 30
R = S.rtl


class HostApp:
    def __init__(self, server: str, runner: AsyncRunner | None = None) -> None:
        self.cfg = config.load()
        self.runner = runner or AsyncRunner()
        self.id = config.host_identity(self.cfg)
        key, uperms = config.get_unattended(self.cfg)
        self.events: queue.Queue = queue.Queue()
        self.service = HostService(
            server, self.id, approval=self._approval,
            on_event=lambda k, **kw: self.events.put((k, kw)),
            unattended_key=key, unattended_perms=uperms)
        self.root = tk.Tk()
        self.root.title(R(S.H_TITLE))
        self.root.geometry("460x680")
        self._build(key is not None, uperms)
        self.runner.submit(self.service.run())
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------------------------------------------------------------- UI
    def _build(self, unatt_on: bool, up: P.Permissions) -> None:
        r = self.root
        top = ttk.LabelFrame(r, text=R(S.H_MY_PC))
        top.pack(fill="x", padx=10, pady=8)
        row = ttk.Frame(top); row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text=R(S.H_YOUR_ID)).pack(side="right")
        self.id_lbl = ttk.Label(row, text=P.format_id(self.id), font=("Segoe UI", 22, "bold"))
        self.id_lbl.pack(side="right", padx=10)
        ttk.Button(row, text=R(S.H_COPY), command=lambda: self._copy(self.id)).pack(side="left")
        self.status = ttk.Label(top, text=R(S.H_CONNECTING), foreground="gray")
        self.status.pack(anchor="e", padx=6)
        ttk.Label(top, text=R(S.H_TEMP_NOTE), foreground="gray",
                  wraplength=400, justify="right").pack(anchor="e", padx=6, pady=(0, 6))

        # ---- גישה ללא נוכחות ----
        ub = ttk.LabelFrame(r, text=R(S.H_UNATT_BOX))
        ub.pack(fill="x", padx=10, pady=4)
        self.u_on = tk.BooleanVar(value=unatt_on)
        ttk.Checkbutton(ub, text=R(S.H_UNATT_ENABLE), variable=self.u_on).pack(anchor="e", padx=6, pady=2)
        prow = ttk.Frame(ub); prow.pack(fill="x", padx=6)
        ttk.Label(prow, text=R(S.H_UNATT_PW)).pack(side="right")
        self.u_pw = ttk.Entry(prow, show="•", width=22)
        self.u_pw.pack(side="right", padx=6)
        ttk.Label(ub, text=R(S.H_UNATT_PW_HINT), foreground="gray").pack(anchor="e", padx=6)
        self.u_control = tk.BooleanVar(value=up.control)
        self.u_clip = tk.BooleanVar(value=up.clipboard)
        self.u_files = tk.BooleanVar(value=up.files)
        prm = ttk.Frame(ub); prm.pack(fill="x", padx=6, pady=2)
        for text, var in ((S.H_PERM_FILES, self.u_files), (S.H_PERM_CLIP, self.u_clip),
                          (S.H_PERM_CONTROL, self.u_control)):
            ttk.Checkbutton(prm, text=R(text), variable=var).pack(side="right", padx=4)
        ttk.Button(ub, text=R(S.H_UNATT_SAVE), command=self._save_unattended).pack(anchor="w", padx=6, pady=6)

        # ---- סשן פעיל ----
        self.sess = ttk.LabelFrame(r, text=R(S.H_SESSION_BOX))
        self.sess.pack(fill="both", expand=True, padx=10, pady=8)
        self.sess_lbl = ttk.Label(self.sess, text=R(S.H_NO_SESSION))
        self.sess_lbl.pack(anchor="e", padx=6, pady=2)
        self.code_lbl = ttk.Label(self.sess, text="", foreground="gray")
        self.code_lbl.pack(anchor="e", padx=6)
        row = ttk.Frame(self.sess); row.pack(fill="x", padx=6)
        self.p_control = tk.BooleanVar(); self.p_clip = tk.BooleanVar(); self.p_files = tk.BooleanVar()
        for text, var, key in ((S.H_PERM_FILES, self.p_files, "files"),
                               (S.H_PERM_CLIP, self.p_clip, "clipboard"),
                               (S.H_PERM_CONTROL, self.p_control, "control")):
            ttk.Checkbutton(row, text=R(text), variable=var,
                            command=lambda k=key, v=var: self.runner.call(
                                lambda: self.service.set_permissions(**{k: v.get()}))
                            ).pack(side="right", padx=4)
        row2 = ttk.Frame(self.sess); row2.pack(fill="x", padx=6, pady=4)
        ttk.Button(row2, text=R(S.H_SEND_FILE), command=self._send_file).pack(side="right")
        ttk.Button(row2, text=R(S.H_DISCONNECT), command=self._disconnect).pack(side="left")
        self.chat = scrolledtext.ScrolledText(self.sess, height=7, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=6, pady=4)
        self.entry = ttk.Entry(self.sess, justify="right")
        self.entry.pack(fill="x", padx=6, pady=(0, 6))
        self.entry.bind("<Return>", self._send_chat)

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear(); self.root.clipboard_append(text)

    def _log(self, line: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", R(line) + "\n"); self.chat.see("end")
        self.chat.configure(state="disabled")

    def _send_chat(self, _e=None) -> None:
        text = self.entry.get().strip()
        if text:
            self.runner.call(self.service.send_chat, text)
            self._log(S.H_ME + text); self.entry.delete(0, "end")

    def _send_file(self) -> None:
        path = filedialog.askopenfilename()
        if path:
            self.runner.submit(self.service.send_file(path))

    def _disconnect(self) -> None:
        self.runner.submit(self.service.disconnect())

    def _quit(self) -> None:
        try:
            self.runner.submit(self.service.stop()).result(3)
        except Exception:
            pass
        self.root.destroy()

    # ---------------------------------------------------- גישה ללא נוכחות
    def _save_unattended(self) -> None:
        had_key = config.get_unattended(self.cfg)[0] is not None
        if not self.u_on.get():
            config.clear_unattended(self.cfg)
            self.runner.call(self.service.set_unattended, None)
            self.u_pw.delete(0, "end")
            messagebox.showinfo(S.APP, R(S.H_UNATT_SAVED))
            return
        pw = self.u_pw.get()
        if pw and len(pw) < config.MIN_UNATTENDED_LEN:
            messagebox.showwarning(S.APP, R(S.H_UNATT_TOO_SHORT)); return
        if not pw and not had_key:
            messagebox.showwarning(S.APP, R(S.H_UNATT_NEED_PW)); return
        if pw and not messagebox.askyesno(R(S.H_UNATT_CONFIRM_TITLE), R(S.H_UNATT_CONFIRM)):
            return
        perms = P.Permissions(control=self.u_control.get(), clipboard=self.u_clip.get(),
                              files=self.u_files.get(), chat=True)
        key = config.set_unattended(self.cfg, pw or None, perms)
        self.runner.call(self.service.set_unattended, key, perms)
        self.u_pw.delete(0, "end")
        messagebox.showinfo(S.APP, R(S.H_UNATT_SAVED))

    # ------------------------------------------------------- אישור חיבור
    async def _approval(self, info: dict):
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.events.put(("ask", {"info": info, "fut": fut, "loop": asyncio.get_running_loop()}))
        try:
            return await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            return None

    def _ask_dialog(self, fut, loop) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title(R(S.H_ASK_TITLE))
        dlg.attributes("-topmost", True)
        dlg.geometry(f"+{self.root.winfo_rootx() + 40}+{self.root.winfo_rooty() + 60}")
        dlg.grab_set()
        ttk.Label(dlg, text=R(S.H_ASK_TEXT), font=("Segoe UI", 12), justify="center").pack(padx=20, pady=12)
        c, cl, fi = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        for text, var in ((S.H_ASK_CONTROL, c), (S.H_ASK_CLIP, cl), (S.H_ASK_FILES, fi)):
            ttk.Checkbutton(dlg, text=R(text), variable=var).pack(anchor="e", padx=20)
        done = {"v": False}

        def finish(result):
            if done["v"]:
                return
            done["v"] = True
            loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(result))
            dlg.destroy()

        row = ttk.Frame(dlg); row.pack(pady=12)
        ttk.Button(row, text=R(S.H_ASK_OK), command=lambda: finish(P.Permissions(
            control=c.get(), clipboard=cl.get(), files=fi.get(), chat=True))).pack(side="left", padx=8)
        ttk.Button(row, text=R(S.H_ASK_NO), command=lambda: finish(None)).pack(side="left", padx=8)
        dlg.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        dlg.after(APPROVAL_TIMEOUT * 1000, lambda: finish(None))
        dlg.bell()

    # ------------------------------------------------------------ אירועים
    def _poll(self) -> None:
        try:
            while True:
                kind, kw = self.events.get_nowait()
                self._handle(kind, kw)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle(self, kind: str, kw: dict) -> None:
        if kind == "ask":
            self._ask_dialog(kw["fut"], kw["loop"])
        elif kind == "status":
            if kw.get("online"):
                self.status.configure(text=R(S.H_ONLINE), foreground="green")
            else:
                self.status.configure(text=R(S.H_OFFLINE), foreground="red")
        elif kind == "error":
            self.status.configure(text=R(S.reason(kw.get("reason"))), foreground="red")
        elif kind == "session_start":
            p = kw["perms"]
            self.p_control.set(p["control"]); self.p_clip.set(p["clipboard"]); self.p_files.set(p["files"])
            text = S.H_SESSION_ON_UNATT if kw.get("mode") == "unattended" else S.H_SESSION_ON
            self.sess_lbl.configure(text=R(text), foreground="red")
            self.code_lbl.configure(text=R(S.H_CODE.format(code=kw.get("code", ""))))
            self.root.title(R(S.H_TITLE_ACTIVE))
            self.root.attributes("-topmost", True)
        elif kind == "session_end":
            self.sess_lbl.configure(text=R(S.H_NO_SESSION), foreground="")
            self.code_lbl.configure(text="")
            self.root.title(R(S.H_TITLE))
            self.root.attributes("-topmost", False)
        elif kind == "chat":
            self._log(S.H_VIEWER + kw["text"])
        elif kind == "alert":
            messagebox.showwarning(R(S.H_ALERT_TITLE), R(S.H_ALERT_SPAM if kw.get("reason") == "spam" else S.H_ALERT_BLOCKED))
        elif kind == "file_received":
            self._log(S.H_FILE_IN + kw["path"])
        elif kind == "file_error":
            self._log(S.H_FILE_ERR + S.reason(kw.get("reason")))
        elif kind == "file_sent":
            self._log(S.H_FILE_OUT + kw["name"])

    def run(self) -> None:
        self.root.mainloop()
