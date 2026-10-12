package com.rdesk.viewer

import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.KeyEvent
import android.view.PopupMenu
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.webrtc.VideoTrack
import java.io.File

class MainActivity : Activity(), ClientListener {

    companion object {
        private const val REQ_FILE = 42
        private const val PREF_SERVER = "server"
        private const val PREF_RECENT = "recent"
    }

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private lateinit var prefs: SharedPreferences
    private lateinit var root: FrameLayout
    private lateinit var clipboard: ClipboardManager

    // מסך חיבור
    private lateinit var connectScreen: View
    private lateinit var idInput: EditText
    private lateinit var passInput: EditText
    private lateinit var serverInput: EditText
    private lateinit var connectBtn: Button
    private lateinit var statusText: TextView
    private lateinit var recentBox: LinearLayout

    // סשן
    private var client: RDeskClient? = null
    private var sessionScreen: View? = null
    private var screenView: RemoteScreenView? = null
    private var keyCatcher: KeyCatcher? = null
    private var extraKeys: View? = null
    private var kbVisible = false
    @Volatile private var pendingTrack: VideoTrack? = null
    private val sticky = linkedSetOf<String>()
    private val stickyButtons = mutableMapOf<String, Button>()
    private val chatLog = StringBuilder()
    private var chatView: TextView? = null
    private var lastClip: String? = null
    private var info: ConnectionInfo? = null
    private val clipListener = ClipboardManager.OnPrimaryClipChangedListener {
        val t = currentClipText()
        if (t != null && t != lastClip) {
            lastClip = t
            client?.sendClipboard(t)
        }
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    // ------------------------------------------------------------------ מחזור חיים
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.layoutDirection = View.LAYOUT_DIRECTION_RTL     // ממשק עברי
        prefs = getSharedPreferences("rdesk", Context.MODE_PRIVATE)
        clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        root = FrameLayout(this)
        setContentView(root)
        buildConnectScreen()
        showConnect(null)
    }

    override fun onDestroy() {
        client?.disconnect()
        scope.cancel()
        super.onDestroy()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (sessionScreen != null) confirmDisconnect() else super.onBackPressed()
    }

    // ------------------------------------------------------------------ מסך חיבור
    private fun buildConnectScreen() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(40), dp(24), dp(24))
        }
        col.addView(TextView(this).apply {
            setText(R.string.connect_title)
            textSize = 24f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, 0, 0, dp(20))
        })
        idInput = field(R.string.hint_id, InputType.TYPE_CLASS_NUMBER).apply { textSize = 22f }
        passInput = field(R.string.hint_password, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        serverInput = field(R.string.hint_server, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI).apply {
            setText(prefs.getString(PREF_SERVER, BuildConfig.DEFAULT_SERVER))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.START
        }
        col.addView(idInput)
        col.addView(passInput)
        col.addView(TextView(this).apply {
            setText(R.string.pw_help)
            setTextColor(resources.getColor(R.color.muted, theme))
            textSize = 13f
            setPadding(dp(4), 0, dp(4), dp(12))
        })
        col.addView(serverInput)
        connectBtn = Button(this).apply {
            setText(R.string.btn_connect)
            textSize = 18f
            setOnClickListener { connect() }
        }
        col.addView(connectBtn, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)).apply { topMargin = dp(12) })
        statusText = TextView(this).apply { setPadding(0, dp(12), 0, dp(12)); textSize = 15f }
        col.addView(statusText)
        col.addView(TextView(this).apply {
            setText(R.string.recent)
            setTextColor(resources.getColor(R.color.muted, theme))
        })
        recentBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(recentBox)
        connectScreen = ScrollView(this).apply {
            isFillViewport = true
            addView(col)
        }
    }

    private fun field(hintRes: Int, type: Int) = EditText(this).apply {
        setHint(hintRes)
        inputType = type
        setSingleLine()
    }

    private fun showConnect(message: String?, isError: Boolean = true) {
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        root.removeAllViews()
        root.addView(connectScreen)
        connectBtn.isEnabled = true
        passInput.setText("")
        statusText.text = message ?: ""
        statusText.setTextColor(if (isError) resources.getColor(R.color.danger, theme) else Color.DKGRAY)
        refreshRecent()
    }

    private fun recentIds(): List<String> =
        (prefs.getString(PREF_RECENT, "") ?: "").split(",").filter { it.isNotBlank() }

    private fun saveRecent(id: String) {
        val l = (listOf(id) + recentIds().filter { it != id }).take(6)
        prefs.edit().putString(PREF_RECENT, l.joinToString(",")).apply()
    }

    private fun refreshRecent() {
        recentBox.removeAllViews()
        for (id in recentIds()) {
            recentBox.addView(Button(this).apply {
                text = Protocol.formatId(id)
                isAllCaps = false
                setOnClickListener { idInput.setText(id); passInput.requestFocus() }
            })
        }
    }

    private fun connect() {
        val id = Protocol.cleanId(idInput.text.toString())
        if (id.isEmpty()) {
            statusText.setTextColor(resources.getColor(R.color.danger, theme))
            statusText.setText(R.string.need_id)
            return
        }
        val pw = passInput.text.toString()
        val server = serverInput.text.toString().trim()
        prefs.edit().putString(PREF_SERVER, server).apply()
        connectBtn.isEnabled = false
        statusText.setTextColor(Color.DKGRAY)
        statusText.setText(if (pw.isEmpty()) R.string.waiting_approval else R.string.connecting)
        hideKeyboard(idInput)

        val c = RDeskClient(applicationContext, this, downloadDir())
        client = c
        scope.launch {
            try {
                val i = c.connect(server, id, pw)
                saveRecent(id)
                showSession(i)
            } catch (e: ConnectException) {
                client = null
                showConnect(getString(R.string.connect_failed, reasonText(e.message ?: "")))
            } catch (e: Exception) {
                client = null
                showConnect(getString(R.string.connect_failed, reasonText(e.message ?: "")))
            }
        }
    }

    private fun reasonText(code: String): String = when (code) {
        "bad password" -> getString(R.string.err_bad_password)
        "declined" -> getString(R.string.err_declined)
        "busy" -> getString(R.string.err_busy)
        "blocked" -> getString(R.string.err_blocked)
        "host not found / offline" -> getString(R.string.err_not_found)
        "host authentication failed" -> getString(R.string.err_auth)
        "timed out waiting for host" -> getString(R.string.err_timeout)
        "server unreachable" -> getString(R.string.err_server)
        "bad server" -> getString(R.string.err_bad_server)
        "host ended the session" -> getString(R.string.err_host_ended)
        "connection lost" -> getString(R.string.err_lost)
        "disconnected" -> getString(R.string.err_disconnected)
        else -> getString(R.string.err_generic, code)
    }

    private fun downloadDir(): File =
        getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS) ?: File(filesDir, "downloads")

    // ------------------------------------------------------------------ סשן
    private fun showSession(i: ConnectionInfo) {
        info = i
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        sticky.clear()

        val screen = RemoteScreenView(this) { ev -> client?.sendInput(ev) }
        screen.viewOnly = !i.perms.control
        screenView = screen
        pendingTrack?.let { screen.attach(it) }
        if (!i.perms.control) Toast.makeText(this, R.string.no_control, Toast.LENGTH_LONG).show()

        val catcher = KeyCatcher(this, ::typeText, ::pressKey)
        keyCatcher = catcher

        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(resources.getColor(R.color.bar, theme))
            setPadding(dp(12), dp(4), dp(4), dp(4))
        }
        val modeLabel = getString(if (i.mode == "unattended") R.string.mode_unattended else R.string.mode_interactive)
        bar.addView(TextView(this).apply {
            text = getString(R.string.security_code, i.code) + " · " + modeLabel
            setTextColor(Color.WHITE)
            textSize = 13f
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        val kbBtn = barButton(getString(R.string.keyboard)) { toggleKeyboard() }
        val menuBtn = barButton("⋮") { }
        menuBtn.setOnClickListener { showMenu(menuBtn) }
        bar.addView(kbBtn)
        bar.addView(menuBtn)

        val keys = buildExtraKeys()
        extraKeys = keys

        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)))
            addView(screen, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(keys)
            addView(catcher, LinearLayout.LayoutParams(1, 1))
        }
        sessionScreen = col
        root.removeAllViews()
        root.addView(col)
        clipboard.addPrimaryClipChangedListener(clipListener)
        lastClip = currentClipText()
    }

    private fun barButton(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        setTextColor(Color.WHITE)
        setBackgroundColor(Color.TRANSPARENT)
        minWidth = 0
        minimumWidth = 0
        setOnClickListener { onClick() }
    }

    private fun showMenu(anchor: View) {
        val screen = screenView ?: return
        val c = client ?: return
        val pm = PopupMenu(this, anchor)
        val m = pm.menu
        m.add(0, 1, 0, R.string.view_only).apply {
            isCheckable = true; isChecked = screen.viewOnly; isEnabled = c.perms.control
        }
        m.add(0, 2, 1, R.string.direct_touch).apply { isCheckable = true; isChecked = screen.directMode }
        if ((info?.monitors?.size ?: 0) > 1) m.add(0, 3, 2, R.string.choose_monitor)
        m.add(0, 4, 3, R.string.quality)
        m.add(0, 5, 4, R.string.chat)
        m.add(0, 6, 5, R.string.send_file).isEnabled = c.perms.files
        m.add(0, 7, 6, R.string.disconnect)
        pm.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                1 -> screen.viewOnly = !screen.viewOnly
                2 -> screen.directMode = !screen.directMode
                3 -> chooseMonitor()
                4 -> chooseQuality()
                5 -> showChat()
                6 -> pickFile()
                7 -> confirmDisconnect()
            }
            true
        }
        pm.show()
    }

    private fun chooseMonitor() {
        val mons = info?.monitors ?: return
        val names = mons.map { getString(R.string.monitor_item, it.index, it.width, it.height) }.toTypedArray()
        AlertDialog.Builder(this).setTitle(R.string.choose_monitor)
            .setItems(names) { _, which -> client?.setMonitor(mons[which].index) }
            .show()
    }

    private fun chooseQuality() {
        val names = arrayOf(getString(R.string.q_high), getString(R.string.q_mid), getString(R.string.q_low))
        AlertDialog.Builder(this).setTitle(R.string.quality)
            .setItems(names) { _, which ->
                when (which) {
                    0 -> client?.setQuality(24, 1.0)
                    1 -> client?.setQuality(15, 0.7)
                    else -> client?.setQuality(8, 0.5)
                }
            }.show()
    }

    private fun showChat() {
        val tv = TextView(this).apply { text = chatLog; setPadding(dp(8), dp(8), dp(8), dp(8)) }
        chatView = tv
        val sv = ScrollView(this).apply { addView(tv) }
        val input = EditText(this).apply {
            setHint(R.string.chat_hint)
            inputType = InputType.TYPE_CLASS_TEXT
            setSingleLine()
        }
        val ll = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(sv, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(220)))
            addView(input)
        }
        AlertDialog.Builder(this).setTitle(R.string.chat).setView(ll)
            .setPositiveButton(R.string.send) { _, _ ->
                val t = input.text.toString().trim()
                if (t.isNotEmpty()) {
                    client?.sendChat(t)
                    chatLog.append(getString(R.string.me_prefix)).append(t).append('\n')
                }
            }
            .setNegativeButton(R.string.close, null)
            .setOnDismissListener { chatView = null }
            .show()
    }

    private fun pickFile() {
        startActivityForResult(
            Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"),
            REQ_FILE,
        )
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri: Uri = data?.data ?: return
        if (requestCode != REQ_FILE || resultCode != RESULT_OK) return
        var name = "file"
        var size = -1L
        contentResolver.query(uri, null, null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val si = c.getColumnIndex(OpenableColumns.SIZE)
                if (ni >= 0) name = c.getString(ni) ?: name
                if (si >= 0 && !c.isNull(si)) size = c.getLong(si)
            }
        }
        if (size < 0) {
            Toast.makeText(this, R.string.file_unknown_size, Toast.LENGTH_LONG).show()
            return
        }
        val c = client ?: return
        scope.launch { c.sendFile(applicationContext, uri, name, size) }
    }

    private fun confirmDisconnect() {
        AlertDialog.Builder(this).setMessage(R.string.confirm_disconnect)
            .setPositiveButton(R.string.yes) { _, _ -> client?.disconnect() }
            .setNegativeButton(R.string.no, null)
            .show()
    }

    private fun endSession(reasonCode: String) {
        runCatching { clipboard.removePrimaryClipChangedListener(clipListener) }
        hideKeyboard(keyCatcher)
        screenView?.release()
        screenView = null
        keyCatcher = null
        sessionScreen = null
        extraKeys = null
        pendingTrack = null
        client = null
        info = null
        kbVisible = false
        showConnect(getString(R.string.session_closed, reasonText(reasonCode)), isError = false)
    }

    // ------------------------------------------------------------------ מקלדת
    private fun toggleKeyboard() {
        val k = keyCatcher ?: return
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        kbVisible = !kbVisible
        if (kbVisible) {
            k.requestFocus()
            imm.showSoftInput(k, 0)
        } else {
            imm.hideSoftInputFromWindow(k.windowToken, 0)
        }
        extraKeys?.visibility = if (kbVisible) View.VISIBLE else View.GONE
    }

    private fun hideKeyboard(v: View?) {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        v?.windowToken?.let { imm.hideSoftInputFromWindow(it, 0) }
    }

    private fun key(kind: String, name: String) {
        client?.sendInput(JSONObject().put("t", kind).put("k", name))
    }

    /** מקש מיוחד (Enter, חצים...) בלחיצה אחת, עם כל המקשים ה"דביקים" שנבחרו. */
    private fun pressKey(name: String, down: Boolean? = null) {
        if (down == null) {
            val mods = sticky.toList()
            mods.forEach { key("kd", it) }
            key("kd", name); key("ku", name)
            mods.reversed().forEach { key("ku", it) }
            clearSticky()
        } else {
            key(if (down) "kd" else "ku", name)
        }
    }

    private fun typeText(text: String) {
        for (ch in text) {
            val s = ch.toString()
            if (sticky.any { it == "ctrl" || it == "alt" || it == "cmd" }) {
                val mods = sticky.toList()
                mods.forEach { key("kd", it) }
                key("kd", s.lowercase()); key("ku", s.lowercase())
                mods.reversed().forEach { key("ku", it) }
                clearSticky()
            } else {
                key("kd", s); key("ku", s)
            }
        }
    }

    private fun clearSticky() {
        sticky.clear()
        stickyButtons.values.forEach { it.alpha = 0.6f }
    }

    private fun buildExtraKeys(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        fun add(label: String, onClick: (Button) -> Unit): Button {
            val b = Button(this).apply {
                text = label
                isAllCaps = false
                minWidth = 0; minimumWidth = 0
                setPadding(dp(10), 0, dp(10), 0)
                setOnClickListener { onClick(this) }
            }
            row.addView(b, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(44)))
            return b
        }
        fun mod(label: String, name: String) {
            val b = add(label) { btn ->
                if (!sticky.remove(name)) sticky.add(name)
                btn.alpha = if (name in sticky) 1f else 0.6f
            }
            b.alpha = 0.6f
            stickyButtons[name] = b
        }
        add("Esc") { pressKey("esc") }
        add("Tab") { pressKey("tab") }
        mod("Ctrl", "ctrl")
        mod("Alt", "alt")
        mod("Shift", "shift")
        mod("Win", "cmd")
        add("←") { pressKey("left") }
        add("↑") { pressKey("up") }
        add("↓") { pressKey("down") }
        add("→") { pressKey("right") }
        add("Home") { pressKey("home") }
        add("End") { pressKey("end") }
        add("PgUp") { pressKey("page_up") }
        add("PgDn") { pressKey("page_down") }
        add("Del") { pressKey("delete") }
        return HorizontalScrollView(this).apply {
            visibility = View.GONE
            setBackgroundColor(resources.getColor(R.color.bar, theme))
            addView(row)
        }
    }

    // ------------------------------------------------------------------ לוח
    private fun currentClipText(): String? = runCatching {
        clipboard.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(this)?.toString()
    }.getOrNull()

    // ------------------------------------------------------------------ ClientListener (מ-threads של WebRTC)
    override fun onChat(text: String) = runOnUiThread {
        val line = getString(R.string.host_prefix) + text
        chatLog.append(line).append('\n')
        chatView?.text = chatLog
        if (chatView == null) Toast.makeText(this, line, Toast.LENGTH_LONG).show()
    }

    override fun onPerms(p: Perms) = runOnUiThread {
        if (!p.control) screenView?.viewOnly = true
        Toast.makeText(this, R.string.perm_changed, Toast.LENGTH_SHORT).show()
    }

    override fun onClipboard(text: String) = runOnUiThread {
        lastClip = text
        clipboard.setPrimaryClip(ClipData.newPlainText("RDesk", text))
    }

    override fun onClosed(reasonCode: String) = runOnUiThread { endSession(reasonCode) }

    override fun onFileEvent(kind: String, name: String, detail: String) = runOnUiThread {
        val msg = when (kind) {
            "incoming" -> getString(R.string.file_incoming, name)
            "received" -> getString(R.string.file_received, detail)
            "sent" -> getString(R.string.file_sent, name)
            "error" -> getString(R.string.file_error, if (name.isEmpty()) detail else "$name ($detail)")
            else -> null
        }
        if (msg != null) Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    override fun onVideoTrack(track: VideoTrack) {
        pendingTrack = track
        runOnUiThread { screenView?.attach(track) }
    }
}

/**
 * שדה נסתר שמקבל טקסט מהמקלדת הווירטואלית. מחזיק תו "מחסום" כדי לזהות גם מחיקה (Backspace).
 * מעביר תווים ל-onText, ומקשים מיוחדים ל-onKey.
 */
class KeyCatcher(
    context: Context,
    private val onText: (String) -> Unit,
    private val onKey: (name: String, down: Boolean?) -> Unit,
) : EditText(context) {
    private val sentinel = "​"
    private var busy = false

    init {
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS or
                InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        imeOptions = EditorInfo.IME_FLAG_NO_EXTRACT_UI or EditorInfo.IME_FLAG_NO_FULLSCREEN
        alpha = 0f
        isCursorVisible = false
        setSingleLine()
        reset()
        addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun afterTextChanged(s: Editable?) {}
            override fun onTextChanged(s: CharSequence, start: Int, before: Int, count: Int) {
                if (busy) return
                val added = if (count > 0) s.subSequence(start, start + count).toString().replace(sentinel, "") else ""
                if (added.isNotEmpty()) onText(added)
                else if (before > 0) repeat(before) { onKey("backspace", null) }
                post { reset() }
            }
        })
        setOnEditorActionListener { _, _, _ -> onKey("enter", null); true }
        setOnKeyListener { _, keyCode, event ->
            val name = keyName(keyCode)
            if (name != null) {
                if (event.action == KeyEvent.ACTION_DOWN) onKey(name, true)
                else if (event.action == KeyEvent.ACTION_UP) onKey(name, false)
                true
            } else false
        }
    }

    private fun reset() {
        busy = true
        setText(sentinel)
        setSelection(text.length)
        busy = false
    }

    private fun keyName(code: Int): String? = when (code) {
        KeyEvent.KEYCODE_DEL -> "backspace"
        KeyEvent.KEYCODE_FORWARD_DEL -> "delete"
        KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER -> "enter"
        KeyEvent.KEYCODE_TAB -> "tab"
        KeyEvent.KEYCODE_ESCAPE -> "esc"
        KeyEvent.KEYCODE_DPAD_UP -> "up"
        KeyEvent.KEYCODE_DPAD_DOWN -> "down"
        KeyEvent.KEYCODE_DPAD_LEFT -> "left"
        KeyEvent.KEYCODE_DPAD_RIGHT -> "right"
        KeyEvent.KEYCODE_MOVE_HOME -> "home"
        KeyEvent.KEYCODE_MOVE_END -> "end"
        KeyEvent.KEYCODE_PAGE_UP -> "page_up"
        KeyEvent.KEYCODE_PAGE_DOWN -> "page_down"
        KeyEvent.KEYCODE_INSERT -> "insert"
        in KeyEvent.KEYCODE_F1..KeyEvent.KEYCODE_F12 -> "f" + (code - KeyEvent.KEYCODE_F1 + 1)
        else -> null
    }
}
