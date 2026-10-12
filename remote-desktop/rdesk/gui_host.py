"""חלון המארח (tkinter, עברית): מזהה, גישה ללא נוכחות, אישור חיבורים והרשאות."""
from __future__ import annotations

import asyncio
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import config, embedded as E, protocol as P, strings as S
from .aio import AsyncRunner
from .host import HostService
from .gui_viewer import ViewerApp

APPROVAL_TIMEOUT = 30
R = S.rtl


class HostApp:
    def __init__(self, server: str | None = None, runner: AsyncRunner | None = None) -> None:
        self.cfg = config.load()
        server = config.server_url(server)
        self.server = server
        self.runner = runner or AsyncRunner()
        self.id = config.host_identity(self.cfg)
        key, uperms = config.get_unattended(self.cfg)
        self.events: queue.Queue = queue.Queue()
        self.embedded: E.EmbeddedServer | None = None
        emb_on, emb_port = config.get_embedded(self.cfg)
        self.embedded_enabled, self.embedded_port = emb_on, emb_port
        # "המחשב הזה כשרת": המארח נרשם מול שרת מוטבע משלו (127.0.0.1), לא מול
        # שדה "שרת" הכללי - זה נשאר לחיבור יוצא למחשב אחר (ראו _connect_remote).
        host_server = f"ws://127.0.0.1:{emb_port}" if emb_on else server
        self.service = HostService(
            host_server, self.id, approval=self._approval,
            on_event=lambda k, **kw: self.events.put((k, kw)),
            unattended_key=key, unattended_perms=uperms)
        self.root = tk.Tk()
        self.root.title(R(S.H_TITLE))
        self.root.geometry("480x720")
        self._build(key is not None, uperms, emb_on, emb_port)
        self.runner.submit(self._start_and_run(emb_on, emb_port))
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------------------------------------------------------------- UI
    def _build(self, unatt_on: bool, up: P.Permissions, emb_on: bool, emb_port: int) -> None:
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True)
        r, st = ttk.Frame(nb), ttk.Frame(nb)
        nb.add(r, text=R(S.H_TAB_MAIN))
        nb.add(st, text=R(S.H_TAB_SETTINGS))
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

        if emb_on:
            self._build_embedded_status(r, emb_port)

        # ---- התחברות למחשב אחר ----
        cb = ttk.LabelFrame(r, text=R(S.H_CONNECT_BOX))
        cb.pack(fill="x", padx=10, pady=4)
        row = ttk.Frame(cb); row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text=R(S.V_ID)).pack(side="right")
        self.c_id = ttk.Combobox(row, values=self.cfg.get("recent", []), width=20, justify="right")
        self.c_id.pack(side="right", padx=6)
        self.c_id.bind("<Return>", lambda e: self._connect_remote())
        ttk.Button(row, text=R(S.V_CONNECT), command=self._connect_remote).pack(side="left")
        row = ttk.Frame(cb); row.pack(fill="x", padx=6)
        ttk.Label(row, text=R(S.V_PASSWORD)).pack(side="right")
        self.c_pw = ttk.Entry(row, show="•", width=22, justify="right")
        self.c_pw.pack(side="right", padx=6)
        self.c_pw.bind("<Return>", lambda e: self._connect_remote())
        ttk.Label(cb, text=R(S.V_PW_HINT), foreground="gray", justify="right",
                  wraplength=420).pack(anchor="e", padx=6, pady=(2, 6))

        # ---- גישה ללא נוכחות (בלשונית ההגדרות) ----
        ub = ttk.LabelFrame(st, text=R(S.H_UNATT_BOX))
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
        ttk.Label(ub, text=R(S.H_UNATT_WARN), foreground="gray", justify="right",
                  wraplength=420).pack(anchor="e", padx=6, pady=(0, 6))

        sb = ttk.LabelFrame(st, text=R(S.H_SERVER_BOX))
        sb.pack(fill="x", padx=10, pady=8)
        srow = ttk.Frame(sb); srow.pack(fill="x", padx=6, pady=6)
        ttk.Label(srow, text=R(S.H_SERVER_LABEL)).pack(side="right")
        self.srv = ttk.Entry(srow, width=30)
        self.srv.insert(0, self.server)
        self.srv.pack(side="right", padx=6)
        ttk.Button(srow, text=R(S.H_SERVER_SAVE), command=self._save_server).pack(side="left")

        # ---- המחשב הזה כשרת (בלי שרת נפרד) ----
        eb = ttk.LabelFrame(st, text=R(S.H_EMBED_BOX))
        eb.pack(fill="x", padx=10, pady=4)
        self.e_on = tk.BooleanVar(value=emb_on)
        ttk.Checkbutton(eb, text=R(S.H_EMBED_ENABLE), variable=self.e_on).pack(anchor="e", padx=6, pady=2)
        erow = ttk.Frame(eb); erow.pack(fill="x", padx=6)
        ttk.Label(erow, text=R(S.H_EMBED_PORT)).pack(side="right")
        self.e_port = ttk.Entry(erow, width=8, justify="right")
        self.e_port.insert(0, str(emb_port))
        self.e_port.pack(side="right", padx=6)
        ttk.Label(eb, text=R(S.H_EMBED_HELP), foreground="gray", justify="right",
                  wraplength=420).pack(anchor="e", padx=6, pady=(4, 2))
        ttk.Button(eb, text=R(S.H_EMBED_SAVE), command=self._save_embedded).pack(anchor="w", padx=6, pady=6)

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

    def _build_embedded_status(self, parent, port: int) -> None:
        box = ttk.LabelFrame(parent, text=R(S.H_EMBED_BOX))
        box.pack(fill="x", padx=10, pady=4)
        self.e_status_lbl = ttk.Label(box, text=R(S.H_EMBED_STARTING), foreground="gray")
        self.e_status_lbl.pack(anchor="e", padx=6, pady=2)
        lrow = ttk.Frame(box); lrow.pack(fill="x", padx=6)
        self.e_lan_lbl = ttk.Label(lrow, text="", foreground="gray")
        self.e_lan_lbl.pack(side="right")
        ttk.Button(lrow, text=R(S.H_EMBED_COPY_LAN),
                  command=lambda: self._copy(self._embed_url(self.embedded and self.embedded.lan_ip))
                  ).pack(side="left", padx=4)
        prow = ttk.Frame(box); prow.pack(fill="x", padx=6, pady=(0, 6))
        self.e_pub_lbl = ttk.Label(prow, text="", foreground="gray")
        self.e_pub_lbl.pack(side="right")
        ttk.Button(prow, text=R(S.H_EMBED_COPY_PUBLIC),
                  command=lambda: self._copy(self._embed_url(self.embedded and self.embedded.public_ip))
                  ).pack(side="left", padx=4)

    def _embed_url(self, ip: str | None) -> str:
        if not ip or not self.embedded:
            return ""
        return f"ws://{ip}:{self.embedded.port}"

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
        if self.embedded is not None:
            try:
                self.runner.submit(self.embedded.close()).result(2)
            except Exception:
                pass
        self.root.destroy()

    def _connect_remote(self) -> None:
        rid = P.clean_id(self.c_id.get())
        if not rid:
            messagebox.showwarning(S.APP, R(S.V_NEED_FIELDS)); return
        if rid == self.id:
            messagebox.showwarning(S.APP, R(S.H_SELF)); return
        ViewerApp(self.server, runner=self.runner, master=self.root,
                  preset=(rid, self.c_pw.get()))
        self.c_pw.delete(0, "end")
        self.cfg = config.load()
        self.c_id.configure(values=self.cfg.get("recent", []))

    def _save_server(self) -> None:
        self.cfg = config.load()
        self.cfg["server"] = self.srv.get().strip()
        config.save(self.cfg)
        messagebox.showinfo(S.APP, R(S.H_SERVER_SAVED))

    # ------------------------------------------------- המחשב הזה כשרת
    def _save_embedded(self) -> None:
        try:
            port = int(self.e_port.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning(S.APP, R(S.H_EMBED_BAD_PORT)); return
        self.cfg = config.load()
        config.set_embedded(self.cfg, self.e_on.get(), port)
        messagebox.showinfo(S.APP, R(S.H_EMBED_SAVED))

    async def _start_and_run(self, emb_on: bool, emb_port: int) -> None:
        """מפעיל קודם את השרת המוטבע (אם צריך) ורק אז את לולאת המארח - כדי
        שניסיון ההתחברות הראשון לא ייתקל ב"אין שרת" עוד לפני שהוא עלה."""
        if emb_on:
            try:
                self.embedded = await E.start(emb_port)
            except OSError as e:
                self.events.put(("embedded_error", {"reason": str(e)}))
            else:
                self.events.put(("embedded_ready", {}))
                asyncio.ensure_future(self._fill_public_ip())
        await self.service.run()

    async def _fill_public_ip(self) -> None:
        if self.embedded is not None:
            await self.embedded.fill_public_ip()
            self.events.put(("embedded_public", {}))

    # ---------------------------------------------------- גישה ללא נוכחות
    def _save_unattended(self) -> None:
        self.cfg = config.load()      # הצופה עשוי היה לעדכן את הקובץ (רשימת אחרונים)
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
        elif kind == "embedded_ready":
            self.e_status_lbl.configure(text=R(S.H_EMBED_RUNNING.format(port=self.embedded.port)), foreground="green")
            lan = self.embedded.lan_ip
            self.e_lan_lbl.configure(text=R(S.H_EMBED_LAN.format(ip=lan or "?", port=self.embedded.port)))
        elif kind == "embedded_public":
            pub = self.embedded.public_ip if self.embedded else None
            if pub:
                self.e_pub_lbl.configure(text=R(S.H_EMBED_PUBLIC.format(ip=pub, port=self.embedded.port)))
            else:
                self.e_pub_lbl.configure(text=R(S.H_EMBED_NO_PUBLIC))
        elif kind == "embedded_error":
            messagebox.showwarning(S.APP, R(f"לא ניתן להפעיל את השרת המוטבע: {S.reason(kw.get('reason'))}"))

    def run(self) -> None:
        self.root.mainloop()
