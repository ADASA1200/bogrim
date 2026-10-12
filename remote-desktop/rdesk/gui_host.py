"""חלון המארח (tkinter): מזהה, סיסמה, אישור חיבורים והרשאות בזמן סשן."""
from __future__ import annotations

import asyncio
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import config, protocol as P
from .aio import AsyncRunner
from .host import HostService

APPROVAL_TIMEOUT = 30


class HostApp:
    def __init__(self, server: str, runner: AsyncRunner | None = None) -> None:
        self.cfg = config.load()
        self.runner = runner or AsyncRunner()
        self.id, self.password = config.host_identity(self.cfg)
        self.events: queue.Queue = queue.Queue()
        self.service = HostService(
            server, self.id, self.password,
            approval=self._approval, on_event=lambda k, **kw: self.events.put((k, kw)))
        self.root = tk.Tk()
        self.root.title("RDesk - מארח")
        self.root.geometry("420x520")
        self._build()
        self.runner.submit(self.service.run())
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------------------------------------------------------------- UI
    def _build(self) -> None:
        r = self.root
        top = ttk.LabelFrame(r, text="המחשב הזה")
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="המזהה שלך:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.id_lbl = ttk.Label(top, text=P.format_id(self.id), font=("Segoe UI", 20, "bold"))
        self.id_lbl.grid(row=0, column=1, padx=6)
        ttk.Button(top, text="העתק", command=lambda: self._copy(self.id)).grid(row=0, column=2)
        ttk.Label(top, text="סיסמה:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.pw_var = tk.StringVar(value=self.password)
        ttk.Entry(top, textvariable=self.pw_var, state="readonly", width=16,
                  font=("Consolas", 13)).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Button(top, text="העתק", command=lambda: self._copy(self.password)).grid(row=1, column=2)
        self.status = ttk.Label(top, text="⏳ מתחבר לשרת...", foreground="gray")
        self.status.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=4)

        self.unattended = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            r, text="גישה ללא נוכחות (אל תבקש אישור בכל חיבור)",
            variable=self.unattended).pack(anchor="w", padx=12)

        self.sess = ttk.LabelFrame(r, text="סשן פעיל")
        self.sess.pack(fill="both", expand=True, padx=10, pady=8)
        self.sess_lbl = ttk.Label(self.sess, text="אין חיבור פעיל")
        self.sess_lbl.pack(anchor="w", padx=6, pady=4)
        row = ttk.Frame(self.sess); row.pack(fill="x", padx=6)
        self.p_control = tk.BooleanVar(); self.p_clip = tk.BooleanVar(); self.p_files = tk.BooleanVar()
        for text, var, key in (("שליטה", self.p_control, "control"),
                               ("לוח", self.p_clip, "clipboard"),
                               ("קבצים", self.p_files, "files")):
            ttk.Checkbutton(row, text=text, variable=var,
                            command=lambda k=key, v=var: self.service.set_permissions(**{k: v.get()})
                            ).pack(side="left", padx=4)
        row2 = ttk.Frame(self.sess); row2.pack(fill="x", padx=6, pady=4)
        ttk.Button(row2, text="שלח קובץ", command=self._send_file).pack(side="left")
        self.btn_disc = ttk.Button(row2, text="נתק", command=self._disconnect)
        self.btn_disc.pack(side="right")
        self.chat = scrolledtext.ScrolledText(self.sess, height=8, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=6, pady=4)
        self.entry = ttk.Entry(self.sess)
        self.entry.pack(fill="x", padx=6, pady=(0, 6))
        self.entry.bind("<Return>", self._send_chat)

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear(); self.root.clipboard_append(text)

    def _log(self, line: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", line + "\n"); self.chat.see("end")
        self.chat.configure(state="disabled")

    def _send_chat(self, _e=None) -> None:
        text = self.entry.get().strip()
        if text:
            self.runner.call(self.service.send_chat, text)
            self._log("אני: " + text); self.entry.delete(0, "end")

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

    # ------------------------------------------------------- אישור חיבור
    async def _approval(self, info: dict):
        if self.unattended.get():
            return P.Permissions()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.events.put(("ask", {"info": info, "fut": fut, "loop": asyncio.get_running_loop()}))
        try:
            return await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            return None

    def _ask_dialog(self, fut, loop) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("בקשת חיבור")
        dlg.attributes("-topmost", True)
        dlg.grab_set()
        ttk.Label(dlg, text="מישהו מבקש להתחבר למחשב שלך.\nלאפשר?",
                  font=("Segoe UI", 12)).pack(padx=20, pady=12)
        c, cl, fi = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        ttk.Checkbutton(dlg, text="אפשר שליטה (עכבר ומקלדת)", variable=c).pack(anchor="w", padx=20)
        ttk.Checkbutton(dlg, text="אפשר סנכרון לוח", variable=cl).pack(anchor="w", padx=20)
        ttk.Checkbutton(dlg, text="אפשר העברת קבצים", variable=fi).pack(anchor="w", padx=20)
        done = {"v": False}

        def finish(result):
            if done["v"]:
                return
            done["v"] = True
            loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(result))
            dlg.destroy()

        row = ttk.Frame(dlg); row.pack(pady=12)
        ttk.Button(row, text="אשר", command=lambda: finish(P.Permissions(
            control=c.get(), clipboard=cl.get(), files=fi.get(), chat=True))).pack(side="left", padx=8)
        ttk.Button(row, text="דחה", command=lambda: finish(None)).pack(side="left", padx=8)
        dlg.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        dlg.after(APPROVAL_TIMEOUT * 1000, lambda: finish(None))

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
                self.status.configure(text="🟢 מחובר לשרת - מוכן לקבל חיבורים", foreground="green")
            else:
                self.status.configure(text="🔴 אין חיבור לשרת, מנסה שוב...", foreground="red")
        elif kind == "session_start":
            p = kw["perms"]
            self.p_control.set(p["control"]); self.p_clip.set(p["clipboard"]); self.p_files.set(p["files"])
            self.sess_lbl.configure(text="🔴 מישהו מחובר למחשב שלך כרגע", foreground="red")
            self.root.title("RDesk - ⚠ סשן פעיל")
            self.root.attributes("-topmost", True)
        elif kind == "session_end":
            self.sess_lbl.configure(text="אין חיבור פעיל", foreground="")
            self.root.title("RDesk - מארח")
            self.root.attributes("-topmost", False)
        elif kind == "chat":
            self._log("צופה: " + kw["text"])
        elif kind == "alert":
            messagebox.showwarning("אבטחה", kw["text"])
        elif kind == "file_received":
            self._log("📥 התקבל קובץ: " + kw["path"])
        elif kind == "file_error":
            self._log("⚠ שגיאת קובץ: " + str(kw.get("reason")))
        elif kind == "file_sent":
            self._log("📤 נשלח: " + kw["name"])

    def run(self) -> None:
        self.root.mainloop()
