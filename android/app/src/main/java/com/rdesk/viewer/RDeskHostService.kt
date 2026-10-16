package com.rdesk.viewer

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.media.projection.MediaProjection
import android.os.Build
import android.os.IBinder
import android.util.DisplayMetrics
import android.view.WindowManager
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import org.webrtc.DataChannel
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.ScreenCapturerAndroid
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoSource
import org.webrtc.VideoTrack
import java.security.SecureRandom
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * שירות קדמה (foreground service): הטלפון הזה כמארח - נרשם בשרת האיתות
 * עם HostIdentity, מקבל בקשות חיבור (hello/offer), מציג מסך-אישור
 * (HostApprovalActivity), ואם אושר - משתף את המסך (ScreenCapturerAndroid)
 * ומזריק קלט נכנס דרך RDeskAccessibilityService. תואם לפרוטוקול של
 * rdesk/host.py, בלי סיסמת-גישה-ללא-נוכחות/TOTP/הזמנות (מצב אינטראקטיבי
 * בלבד - כל חיבור דורש אישור אנושי כאן בטלפון) ובלי קבצים/טאנלינג
 * בכיוון הזה - שלב 1 בכוונה, ראו תיעוד הפער בסיכום לטלפון.
 */
class RDeskHostService : Service() {

    companion object {
        const val ACTION_START = "com.rdesk.viewer.action.HOST_START"
        const val ACTION_STOP = "com.rdesk.viewer.action.HOST_STOP"
        const val EXTRA_RESULT_CODE = "resultCode"
        const val EXTRA_RESULT_DATA = "resultData"
        private const val CHANNEL_ID = "rdesk_host"
        private const val NOTIF_ID = 7001
        private const val STUN = "stun:stun.l.google.com:19302"

        @Volatile var isRunning = false
            private set
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var signalingJob: Job? = null
    private lateinit var notificationManager: NotificationManager
    private var screenPermissionData: Intent? = null

    private var pc: PeerConnection? = null
    private var controlChannel: DataChannel? = null
    private var capturer: ScreenCapturerAndroid? = null
    private var videoSource: VideoSource? = null
    private var surfaceHelper: SurfaceTextureHelper? = null
    private var screenW = 0
    private var screenH = 0

    @Volatile private var hasSession = false
    @Volatile private var busyNegotiating = false
    private val pendingNonces = mutableMapOf<String, String>()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        notificationManager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            notificationManager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, getString(R.string.host_notification_title), NotificationManager.IMPORTANCE_LOW)
            )
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopHosting()
            stopSelf()
            return START_NOT_STICKY
        }
        // ה-startForeground חייב לקרות *לפני* כל קריאה שתשתמש ב-MediaProjection
        // (דרישת Android 14) - ולכן תמיד ראשון כאן, גם אם ה-extras לא תקינים.
        startForeground(NOTIF_ID, buildNotification(null))
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        @Suppress("DEPRECATION")
        val resultData: Intent? = intent?.getParcelableExtra(EXTRA_RESULT_DATA)
        if (resultCode != Activity.RESULT_OK || resultData == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        screenPermissionData = resultData
        isRunning = true
        signalingJob = scope.launch { runSignaling() }
        return START_STICKY
    }

    override fun onDestroy() {
        stopHosting()
        super.onDestroy()
    }

    private fun stopHosting() {
        isRunning = false
        signalingJob?.cancel()
        endSession()
        scope.coroutineContext.cancelChildren()
    }

    // ------------------------------------------------------------------ התראה
    private fun buildNotification(connectedTo: String?): Notification {
        val stopIntent = PendingIntent.getService(
            this, 0, Intent(this, RDeskHostService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val text = if (connectedTo != null) getString(R.string.host_notification_connected, connectedTo)
        else getString(R.string.host_notification_text, Protocol.formatId(HostIdentity.get(prefs())))
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.host_notification_title))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, getString(R.string.host_mode_stop), stopIntent).build())
            .build()
    }

    private fun updateNotification(connectedTo: String?) {
        notificationManager.notify(NOTIF_ID, buildNotification(connectedTo))
    }

    private fun prefs(): SharedPreferences = getSharedPreferences("rdesk", Context.MODE_PRIVATE)

    // ------------------------------------------------------------------ איתות (תואם rdesk/host.py)
    private suspend fun runSignaling() {
        val myId = HostIdentity.get(prefs())
        var backoff = 1_000L
        while (scope.isActive) {
            val inbox = Channel<JSONObject>(Channel.UNLIMITED)
            val http = OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build()
            val server = prefs().getString("server", BuildConfig.DEFAULT_SERVER) ?: BuildConfig.DEFAULT_SERVER
            val socket = runCatching {
                http.newWebSocket(Request.Builder().url(server).build(), object : WebSocketListener() {
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        runCatching { inbox.trySend(JSONObject(text)) }
                    }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                        inbox.trySend(JSONObject().put("type", "ws_failure"))
                    }
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                        inbox.trySend(JSONObject().put("type", "ws_failure"))
                    }
                })
            }.getOrNull()
            if (socket == null) {
                runCatching { http.dispatcher.executorService.shutdown() }
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(15_000)
                continue
            }
            socket.send(JSONObject().put("type", "register").put("id", myId).toString())
            try {
                loop@ while (scope.isActive) {
                    val m = withTimeoutOrNull(60_000) { inbox.receive() } ?: break@loop
                    when (m.optString("type")) {
                        "registered" -> backoff = 1_000L
                        "relay" -> handleRelay(socket, m)
                        "ws_failure" -> break@loop
                    }
                }
            } finally {
                runCatching { http.dispatcher.executorService.shutdown() }
            }
            delay(backoff)
            backoff = (backoff * 2).coerceAtMost(15_000)
        }
    }

    private fun relaySend(socket: WebSocket, peer: String, payload: JSONObject) {
        socket.send(JSONObject().put("type", "relay").put("to", peer).put("payload", payload).toString())
    }

    private suspend fun handleRelay(socket: WebSocket, m: JSONObject) {
        val peer = m.optString("from")
        val fromIp = m.optString("from_ip").takeIf { it.isNotBlank() }
        val p = m.optJSONObject("payload") ?: return
        when (p.optString("kind")) {
            "hello" -> {
                if (hasSession || busyNegotiating) {
                    relaySend(socket, peer, JSONObject().put("kind", "reject").put("reason", "busy"))
                    return
                }
                val nonce = ByteArray(16).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
                pendingNonces[peer] = nonce
                relaySend(socket, peer, JSONObject().put("kind", "challenge").put("nonce", nonce))
            }
            "offer" -> {
                val nonce = pendingNonces.remove(peer)
                if (nonce == null || hasSession || busyNegotiating) {
                    relaySend(socket, peer, JSONObject().put("kind", "reject").put("reason", "no session"))
                    return
                }
                busyNegotiating = true
                try {
                    acceptOffer(socket, peer, p, fromIp)
                } finally {
                    busyNegotiating = false
                }
            }
        }
    }

    // ------------------------------------------------------------------ סשן
    private suspend fun acceptOffer(socket: WebSocket, peer: String, p: JSONObject, fromIp: String?) {
        val viewerUsername = p.optString("username").takeIf { it.isNotBlank() }
        val viewerComputer = p.optString("computer").takeIf { it.isNotBlank() }
        val deferred = HostApprovalBus.request(ApprovalInfo(peer, fromIp, viewerUsername, viewerComputer))
        startActivity(
            Intent(this, HostApprovalActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        )
        val allowed = withTimeoutOrNull(60_000) { deferred.await() } ?: false
        if (!allowed) {
            relaySend(socket, peer, JSONObject().put("kind", "reject").put("reason", "declined"))
            return
        }
        val sdp = p.optString("sdp")

        val factory = RDeskClient.ensureFactory(applicationContext)
        val rtcConfig = PeerConnection.RTCConfiguration(
            listOf(PeerConnection.IceServer.builder(STUN).createIceServer())
        ).apply { sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN }
        val gathered = CompletableDeferred<Unit>()

        val connection = factory.createPeerConnection(rtcConfig, object : SimplePcObserver() {
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                if (state == PeerConnection.IceGatheringState.COMPLETE) gathered.complete(Unit)
            }
            override fun onDataChannel(channel: DataChannel) {
                if (channel.label() == "control") {
                    controlChannel = channel
                    channel.registerObserver(SimpleDcObserver { onControlMessage(it) })
                }
            }
            override fun onConnectionChange(newState: PeerConnection.PeerConnectionState) {
                if (newState == PeerConnection.PeerConnectionState.FAILED ||
                    newState == PeerConnection.PeerConnectionState.CLOSED
                ) {
                    endSession()
                }
            }
        }) ?: return
        pc = connection

        connection.awaitSetRemote(SessionDescription(SessionDescription.Type.OFFER, sdp))
        startScreenCapture(factory, connection)
        val answer = connection.awaitCreateAnswer()
        connection.awaitSetLocal(answer)
        withTimeoutOrNull(5_000) { gathered.await() }
        val answerSdp = connection.localDescription.description

        hasSession = true
        relaySend(socket, peer, JSONObject().put("kind", "answer").put("sdp", answerSdp))
        updateNotification(viewerComputer ?: fromIp ?: peer)
        sendControlHello()
    }

    /** שולח "hello" בערוץ control כשהוא נפתח - תואם ל-_on_control_open בפייתון. */
    private fun sendControlHello() {
        scope.launch {
            val ch = withTimeoutOrNull(10_000) {
                while (controlChannel?.state() != DataChannel.State.OPEN && isActive) delay(50)
                controlChannel
            } ?: return@launch
            val monitors = org.json.JSONArray().put(
                JSONObject().put("index", 1).put("width", screenW).put("height", screenH)
            )
            val perms = JSONObject().put("control", true).put("clipboard", false)
                .put("files", false).put("chat", false)
            val hello = JSONObject().put("t", "hello").put("monitors", monitors).put("monitor", 1).put("perms", perms)
            ch.send(DataChannel.Buffer(java.nio.ByteBuffer.wrap(hello.toString().toByteArray(Charsets.UTF_8)), false))
        }
    }

    private fun startScreenCapture(factory: PeerConnectionFactory, connection: PeerConnection) {
        val permissionData = screenPermissionData ?: return
        @Suppress("DEPRECATION")
        val metrics = DisplayMetrics().also {
            (getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(it)
        }
        screenW = metrics.widthPixels
        screenH = metrics.heightPixels

        val cap = ScreenCapturerAndroid(permissionData, object : MediaProjection.Callback() {
            override fun onStop() {
                endSession()
            }
        })
        val source = factory.createVideoSource(true)
        val helper = SurfaceTextureHelper.create("rdesk-host-capture", RDeskClient.eglBase?.eglBaseContext)
        cap.initialize(helper, applicationContext, source.capturerObserver)
        cap.startCapture(screenW, screenH, 20)
        val track: VideoTrack = factory.createVideoTrack("rdesk-screen", source)
        connection.addTrack(track, listOf("rdesk-stream"))
        capturer = cap
        videoSource = source
        surfaceHelper = helper
    }

    // ------------------------------------------------------------------ קלט נכנס
    private fun onControlMessage(raw: String) {
        val m = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val svc = RDeskAccessibilityService.instance
        when (m.optString("t")) {
            "md" -> if (svc != null && screenW > 0) svc.onMouseDown(normX(m), normY(m))
            "mm" -> if (svc != null && screenW > 0) svc.onMouseMove(normX(m), normY(m))
            "mu" -> if (svc != null && screenW > 0) svc.onMouseUp(normX(m), normY(m))
            "ms" -> svc?.onScroll(m.optInt("dy", 0).coerceIn(-20, 20))
            "kd" -> svc?.onKeyDown(m.optString("k"))
            "bye" -> endSession()
        }
    }

    private fun normX(m: JSONObject): Float = (m.optDouble("x", 0.0).coerceIn(0.0, 1.0) * (screenW - 1)).toFloat()
    private fun normY(m: JSONObject): Float = (m.optDouble("y", 0.0).coerceIn(0.0, 1.0) * (screenH - 1)).toFloat()

    private fun endSession() {
        hasSession = false
        RDeskAccessibilityService.instance?.releaseAll()
        runCatching { controlChannel?.close() }
        controlChannel = null
        runCatching { capturer?.stopCapture() }
        runCatching { capturer?.dispose() }
        capturer = null
        runCatching { videoSource?.dispose() }
        videoSource = null
        runCatching { surfaceHelper?.dispose() }
        surfaceHelper = null
        runCatching { pc?.close() }
        runCatching { pc?.dispose() }
        pc = null
        screenW = 0
        screenH = 0
        if (isRunning) updateNotification(null)
    }
}

// ---------------------------------------------------------------------- עזרי WebRTC (מקביל ל-RDeskClient.kt)
private suspend fun PeerConnection.awaitCreateAnswer(): SessionDescription =
    suspendCancellableCoroutine { cont ->
        createAnswer(object : SimpleSdpObserver() {
            override fun onCreateSuccess(sdp: SessionDescription) = cont.resume(sdp)
            override fun onCreateFailure(error: String) = cont.resumeWithException(ConnectException(error))
        }, org.webrtc.MediaConstraints())
    }

private suspend fun PeerConnection.awaitSetLocal(sdp: SessionDescription) =
    suspendCancellableCoroutine<Unit> { cont ->
        setLocalDescription(object : SimpleSdpObserver() {
            override fun onSetSuccess() = cont.resume(Unit)
            override fun onSetFailure(error: String) = cont.resumeWithException(ConnectException(error))
        }, sdp)
    }

private suspend fun PeerConnection.awaitSetRemote(sdp: SessionDescription) =
    suspendCancellableCoroutine<Unit> { cont ->
        setRemoteDescription(object : SimpleSdpObserver() {
            override fun onSetSuccess() = cont.resume(Unit)
            override fun onSetFailure(error: String) = cont.resumeWithException(ConnectException(error))
        }, sdp)
    }
