package com.rdesk.viewer

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.provider.Settings
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.KeyEvent
import android.widget.PopupMenu
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
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.webrtc.VideoTrack
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity(), ClientListener {

    companion object {
        private const val REQ_FILE = 42
        private const val REQ_SCREEN_CAPTURE = 44
        private const val REQ_NOTIF_PERM = 45
        private const val PREF_SERVER = "server"
        private const val PREF_RECENT = "recent"
    }

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private lateinit var prefs: SharedPreferences
    private lateinit var root: FrameLayout
    private lateinit var clipboard: ClipboardManager

    // מסך חיבור
    private lateinit var connectScreen: View
    private lateinit var inviteInput: EditText
    private lateinit var idInput: EditText
    private lateinit var passInput: EditText
    private lateinit var totpInput: EditText
    private lateinit var serverInput: EditText
    private lateinit var connectBtn: Button
    private lateinit var statusText: TextView
    private lateinit var recentBox: LinearLayout
    private lateinit var wolMacInput: EditText
    private lateinit var wolBtn: Button
    private var pendingInviteToken: String? = null
    private var invitePasting = false

    // מצב מארח (הטלפון הזה מקבל חיבורים נכנסים)
    private lateinit var hostIdText: TextView
    private lateinit var hostToggleBtn: Button
    private lateinit var hostStatusText: TextView

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
    private var activePeerId: String? = null
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

    override fun onResume() {
        super.onResume()
        if (sessionScreen == null) refreshHostModeUi()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (sessionScreen != null) confirmDisconnect() else super.onBackPressed()
    }

    // ------------------------------------------------------------------ מסך חיבור
    private fun buildConnectScreen() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(resources.getColor(R.color.bg, theme))
            setPadding(dp(20), dp(36), dp(20), dp(24))
        }
        col.addView(TextView(this).apply {
            setText(R.string.connect_title)
            textSize = 24f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(resources.getColor(R.color.fg, theme))
            setPadding(dp(4), 0, dp(4), dp(16))
        })

        val mainCard = card()
        inviteInput = field(R.string.hint_invite, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI).apply {
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.START
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    if (!invitePasting) pasteInviteLink(s?.toString() ?: "")
                }
            })
        }
        idInput = field(R.string.hint_id, InputType.TYPE_CLASS_NUMBER).apply { textSize = 22f }
        passInput = field(R.string.hint_password, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        totpInput = field(R.string.hint_totp, InputType.TYPE_CLASS_NUMBER).apply {
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.START
            filters = arrayOf(android.text.InputFilter.LengthFilter(6))
        }
        serverInput = field(R.string.hint_server, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI).apply {
            setText(prefs.getString(PREF_SERVER, BuildConfig.DEFAULT_SERVER))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.START
        }
        mainCard.addView(inviteInput)
        mainCard.addView(idInput, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) })
        mainCard.addView(passInput, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) })
        mainCard.addView(totpInput, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) })
        mainCard.addView(TextView(this).apply {
            setText(R.string.pw_help)
            setTextColor(resources.getColor(R.color.fg_faint, theme))
            textSize = 12.5f
            setPadding(dp(2), dp(8), dp(2), dp(4))
        })
        mainCard.addView(serverInput)
        connectBtn = primaryButton(R.string.btn_connect) { connect() }
        mainCard.addView(connectBtn, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply { topMargin = dp(14) })
        statusText = TextView(this).apply { setPadding(dp(2), dp(10), dp(2), 0); textSize = 14f }
        mainCard.addView(statusText)
        col.addView(mainCard)

        col.addView(spacer(16))
        val recentCard = card()
        recentCard.addView(TextView(this).apply {
            setText(R.string.recent)
            setTextColor(resources.getColor(R.color.fg_faint, theme))
            textSize = 12.5f
        })
        recentBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        recentCard.addView(recentBox, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(6) })
        recentCard.addView(ghostButton(R.string.history_btn) { showHistory() }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(10) })
        col.addView(recentCard)

        col.addView(spacer(16))
        col.addView(buildWolSection())
        col.addView(spacer(16))
        col.addView(buildHostModeSection())
        connectScreen = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(resources.getColor(R.color.bg, theme))
            addView(col)
        }
    }

    private fun buildWolSection(): View {
        val box = card()
        box.addView(TextView(this).apply {
            setText(R.string.wol_title)
            setTextColor(resources.getColor(R.color.fg_faint, theme))
            textSize = 12.5f
        })
        wolMacInput = field(R.string.wol_mac_hint, InputType.TYPE_CLASS_TEXT).apply {
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.START
            // שומרים/מאמתים רק באיבוד פוקוס (כמו onBlur בצד הדסקטופ) - לא
            // בכל הקשה, שהיה מציג "MAC לא תקין" תוך כדי הקלדה תקינה חלקית.
            setOnFocusChangeListener { _, hasFocus ->
                if (hasFocus) return@setOnFocusChangeListener
                val id = Protocol.cleanId(idInput.text.toString())
                val mac = text.toString().trim()
                if (id.length != 9) return@setOnFocusChangeListener
                if (mac.isEmpty()) {
                    WakeOnLan.setMac(prefs, id, "")
                    return@setOnFocusChangeListener
                }
                if (runCatching { WakeOnLan.normalizeMac(mac) }.isSuccess) {
                    WakeOnLan.setMac(prefs, id, mac)
                } else {
                    Toast.makeText(this@MainActivity, R.string.wol_bad_mac, Toast.LENGTH_SHORT).show()
                }
            }
        }
        box.addView(wolMacInput, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) })
        wolBtn = ghostButton(R.string.wol_wake) { wakeOnLan() }
        box.addView(wolBtn, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(10) })
        idInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val id = Protocol.cleanId(idInput.text.toString())
                wolMacInput.setText(if (id.length == 9) WakeOnLan.getMac(prefs, id) ?: "" else "")
            }
        })
        return box
    }

    private fun buildHostModeSection(): View {
        val box = card()
        box.addView(TextView(this).apply {
            setText(R.string.host_mode_title)
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(resources.getColor(R.color.fg, theme))
            textSize = 15f
        })
        box.addView(TextView(this).apply {
            setText(R.string.host_mode_help)
            setTextColor(resources.getColor(R.color.fg_faint, theme))
            textSize = 12.5f
            setPadding(0, dp(6), 0, dp(10))
        })
        hostIdText = TextView(this).apply {
            textSize = 20f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(resources.getColor(R.color.fg, theme))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.CENTER
        }
        box.addView(hostIdText, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(4) })
        hostStatusText = TextView(this).apply {
            textSize = 12.5f
            gravity = Gravity.CENTER
            setPadding(0, dp(4), 0, dp(10))
        }
        box.addView(hostStatusText)
        hostToggleBtn = primaryButton(R.string.host_mode_start) { toggleHostMode() }
        box.addView(hostToggleBtn, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)))
        return box
    }

    private fun refreshHostModeUi() {
        hostIdText.text = Protocol.formatId(HostIdentity.get(prefs))
        val running = RDeskHostService.isRunning
        hostToggleBtn.setText(if (running) R.string.host_mode_stop else R.string.host_mode_start)
        hostStatusText.setText(if (running) R.string.host_mode_active else R.string.host_mode_inactive)
        hostStatusText.setTextColor(resources.getColor(if (running) R.color.success else R.color.fg_faint, theme))
    }

    private fun toggleHostMode() {
        if (RDeskHostService.isRunning) {
            startService(Intent(this, RDeskHostService::class.java).setAction(RDeskHostService.ACTION_STOP))
            refreshHostModeUi()
            return
        }
        if (!RDeskAccessibilityService.isEnabled(this)) {
            AlertDialog.Builder(this)
                .setMessage(R.string.accessibility_not_enabled)
                .setPositiveButton(R.string.accessibility_open_settings) { _, _ ->
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }
                .setNegativeButton(R.string.close, null)
                .show()
            return
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            // לא חוסמים על זה - גם בלי ההרשאה השירות ממשיך לרוץ, רק ההתראה לא תוצג
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIF_PERM)
        }
        val mgr = getSystemService(MediaProjectionManager::class.java)
        startActivityForResult(mgr.createScreenCaptureIntent(), REQ_SCREEN_CAPTURE)
    }

    private fun wakeOnLan() {
        val id = Protocol.cleanId(idInput.text.toString())
        val mac = WakeOnLan.getMac(prefs, id)
        if (mac == null) {
            Toast.makeText(this, R.string.wol_no_mac, Toast.LENGTH_SHORT).show()
            return
        }
        scope.launch {
            val ok = withContext(Dispatchers.IO) { WakeOnLan.send(mac) }
            Toast.makeText(this@MainActivity, if (ok) R.string.wol_sent else R.string.wol_bad_mac, Toast.LENGTH_LONG).show()
        }
    }

    private fun pasteInviteLink(text: String) {
        if (!text.startsWith("rdesk://")) return
        val link = Protocol.parseInviteUrl(text)
        if (link == null) {
            Toast.makeText(this, R.string.invite_link_invalid, Toast.LENGTH_SHORT).show()
            return
        }
        pendingInviteToken = link.token
        invitePasting = true
        idInput.setText(link.id)
        if (link.server.isNotEmpty()) serverInput.setText(link.server)
        invitePasting = false
        connect(invite = link.token)
    }

    private fun field(hintRes: Int, type: Int) = EditText(this).apply {
        setHint(hintRes)
        inputType = type
        setSingleLine()
        setBackgroundResource(R.drawable.bg_input)
        setPadding(dp(12), dp(10), dp(12), dp(10))
        setTextColor(resources.getColor(R.color.fg, theme))
        setHintTextColor(resources.getColor(R.color.fg_faint, theme))
    }

    /** כרטיס לבן מעוגל-פינות (כמו .card בצד שולחן העבודה) - עוטף קבוצת שדות קשורה. */
    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundResource(R.drawable.bg_card)
        setPadding(dp(16), dp(16), dp(16), dp(16))
    }

    private fun primaryButton(textRes: Int, onClick: () -> Unit) = Button(this).apply {
        setText(textRes)
        isAllCaps = false
        setTextColor(Color.WHITE)
        setBackgroundResource(R.drawable.bg_btn_primary)
        stateListAnimator = null
        setOnClickListener { onClick() }
    }

    private fun ghostButton(textRes: Int, onClick: () -> Unit) = ghostButton(getString(textRes), onClick)

    private fun ghostButton(label: CharSequence, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        setTextColor(resources.getColor(R.color.fg, theme))
        setBackgroundResource(R.drawable.bg_btn_ghost)
        stateListAnimator = null
        setOnClickListener { onClick() }
    }

    private fun spacer(heightDp: Int) = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(heightDp))
    }

    private fun showConnect(message: String?, isError: Boolean = true) {
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        root.removeAllViews()
        root.addView(connectScreen)
        connectBtn.isEnabled = true
        passInput.setText("")
        statusText.text = message ?: ""
        statusText.setTextColor(resources.getColor(if (isError) R.color.danger else R.color.muted, theme))
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
            recentBox.addView(
                ghostButton(Protocol.formatId(id)) { idInput.setText(id); passInput.requestFocus() },
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(4) }
            )
        }
    }

    private fun connect(invite: String = "") {
        val id = Protocol.cleanId(idInput.text.toString())
        if (id.isEmpty()) {
            statusText.setTextColor(resources.getColor(R.color.danger, theme))
            statusText.setText(R.string.need_id)
            return
        }
        val pw = passInput.text.toString()
        val totp = totpInput.text.toString().trim()
        val server = serverInput.text.toString().trim()
        prefs.edit().putString(PREF_SERVER, server).apply()
        connectBtn.isEnabled = false
        statusText.setTextColor(Color.DKGRAY)
        statusText.setText(
            when {
                invite.isNotEmpty() -> R.string.connecting_invite
                pw.isEmpty() -> R.string.waiting_approval
                else -> R.string.connecting
            }
        )
        hideKeyboard(idInput)

        val c = RDeskClient(applicationContext, this, downloadDir())
        client = c
        scope.launch {
            try {
                val i = c.connect(server, id, pw, totp, invite)
                saveRecent(id)
                activePeerId = id
                ConnectionHistory.startEntry(prefs, id, i.mode)
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
        "bad totp" -> getString(R.string.err_bad_totp)
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
        screen.onWhiteboardStroke = { data -> client?.sendWhiteboard(data) }
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
        m.add(0, 8, 6, R.string.whiteboard).apply { isCheckable = true; isChecked = screen.whiteboardActive }
        m.add(0, 9, 7, R.string.whiteboard_clear)
        m.add(0, 10, 8, R.string.tunnel).isEnabled = c.perms.control
        m.add(0, 7, 9, R.string.disconnect)
        pm.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                1 -> screen.viewOnly = !screen.viewOnly
                2 -> screen.directMode = !screen.directMode
                3 -> chooseMonitor()
                4 -> chooseQuality()
                5 -> showChat()
                6 -> pickFile()
                7 -> confirmDisconnect()
                8 -> screen.whiteboardActive = !screen.whiteboardActive
                9 -> { screen.clearWhiteboard(); client?.sendWhiteboard(JSONObject().put("type", "clear")) }
                10 -> showTunnelDialog()
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

    private fun showTunnelDialog() {
        val c = client ?: return
        val listBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val localInput = EditText(this).apply { setHint(R.string.tunnel_local_port); inputType = InputType.TYPE_CLASS_NUMBER; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        val hostInput = EditText(this).apply { setHint(R.string.tunnel_remote_host); setText("127.0.0.1"); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        val remoteInput = EditText(this).apply { setHint(R.string.tunnel_remote_port); inputType = InputType.TYPE_CLASS_NUMBER; layoutDirection = View.LAYOUT_DIRECTION_LTR }

        fun refreshList() {
            listBox.removeAllViews()
            for (port in c.tunnelActivePorts()) {
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                row.addView(TextView(this).apply { text = "127.0.0.1:$port"; layoutDirection = View.LAYOUT_DIRECTION_LTR }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                row.addView(Button(this).apply {
                    setText(R.string.tunnel_close)
                    isAllCaps = false
                    setOnClickListener { c.stopTunnel(port); refreshList() }
                })
                listBox.addView(row)
            }
        }
        refreshList()

        val ll = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
            addView(listBox)
            addView(localInput)
            addView(hostInput)
            addView(remoteInput)
            addView(Button(this@MainActivity).apply {
                setText(R.string.tunnel_add)
                isAllCaps = false
                setOnClickListener {
                    val localPort = localInput.text.toString().trim().toIntOrNull()
                    val remotePort = remoteInput.text.toString().trim().toIntOrNull()
                    val host = hostInput.text.toString().trim()
                    if (localPort == null || remotePort == null || host.isEmpty()) {
                        Toast.makeText(this@MainActivity, R.string.tunnel_bad_port, Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    scope.launch {
                        try {
                            c.startTunnel(localPort, host, remotePort)
                            localInput.setText("")
                            remoteInput.setText("")
                            refreshList()
                        } catch (e: Exception) {
                            Toast.makeText(this@MainActivity, getString(R.string.connect_failed, e.message ?: ""), Toast.LENGTH_LONG).show()
                        }
                    }
                }
            })
        }
        AlertDialog.Builder(this).setTitle(R.string.tunnel).setView(ScrollView(this).apply { addView(ll) })
            .setNegativeButton(R.string.close, null)
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
        if (requestCode == REQ_SCREEN_CAPTURE) {
            if (resultCode == RESULT_OK && data != null) {
                val intent = Intent(this, RDeskHostService::class.java)
                    .setAction(RDeskHostService.ACTION_START)
                    .putExtra(RDeskHostService.EXTRA_RESULT_CODE, resultCode)
                    .putExtra(RDeskHostService.EXTRA_RESULT_DATA, data)
                if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
            } else {
                Toast.makeText(this, R.string.screen_capture_denied, Toast.LENGTH_LONG).show()
            }
            refreshHostModeUi()
            return
        }
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
        activePeerId?.let { ConnectionHistory.endLast(prefs, it) }
        activePeerId = null
        showConnect(getString(R.string.session_closed, reasonText(reasonCode)), isError = false)
    }

    // ------------------------------------------------------------------ היסטוריית חיבורים
    private fun showHistory() {
        val entries = ConnectionHistory.recent(prefs)
        val df = SimpleDateFormat("dd/MM HH:mm", Locale.getDefault())
        val view: View = if (entries.isEmpty()) {
            TextView(this).apply {
                setText(R.string.history_empty)
                setPadding(dp(16), dp(16), dp(16), dp(16))
            }
        } else {
            val col = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(8), dp(8), dp(8), dp(8))
            }
            for (e in entries) {
                val mode = getString(if (e.mode == "unattended") R.string.mode_unattended else R.string.mode_interactive)
                val duration = e.endedAt?.let { formatDuration(it - e.startedAt) } ?: getString(R.string.history_ongoing)
                col.addView(TextView(this).apply {
                    text = "${df.format(Date(e.startedAt * 1000))} · ${Protocol.formatId(e.peer)} · $mode · $duration"
                    setPadding(0, dp(6), 0, dp(6))
                })
            }
            ScrollView(this).apply { addView(col) }
        }
        AlertDialog.Builder(this).setTitle(R.string.history_title).setView(view)
            .setNegativeButton(R.string.close, null)
            .setNeutralButton(R.string.history_clear) { _, _ -> ConnectionHistory.clear(prefs) }
            .show()
    }

    private fun formatDuration(seconds: Long): String {
        val s = seconds.coerceAtLeast(0)
        return "%d:%02d".format(s / 60, s % 60)
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

    override fun onWhiteboard(data: JSONObject?) = runOnUiThread {
        screenView?.applyRemoteWhiteboard(data)
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
