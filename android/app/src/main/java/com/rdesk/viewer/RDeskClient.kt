package com.rdesk.viewer

import android.content.Context
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.MediaStreamTrack
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpTransceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.VideoTrack
import java.io.File
import java.nio.ByteBuffer
import java.security.SecureRandom
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** מאזין לאירועי הסשן. נקרא מ-threads של WebRTC - יש לעבור ל-UI thread בצד הצורך. */
interface ClientListener {
    fun onChat(text: String)
    fun onPerms(p: Perms)
    fun onClipboard(text: String)
    fun onClosed(reasonCode: String)
    fun onFileEvent(kind: String, name: String, detail: String)
    fun onVideoTrack(track: VideoTrack)
}

/**
 * לקוח צופה: אותו פרוטוקול של rdesk/viewer.py.
 * איתות: WebSocket -> hello / challenge / offer / answer. אחרי זה הכל על WebRTC.
 */
class RDeskClient(
    private val appContext: Context,
    private val listener: ClientListener,
    private val downloadDir: File,
) {
    companion object {
        private const val STUN = "stun:stun.l.google.com:19302"

        @Volatile private var factory: PeerConnectionFactory? = null
        @Volatile var eglBase: EglBase? = null
            private set

        @Synchronized
        fun ensureFactory(ctx: Context): PeerConnectionFactory {
            factory?.let { return it }
            PeerConnectionFactory.initialize(
                PeerConnectionFactory.InitializationOptions.builder(ctx.applicationContext)
                    .createInitializationOptions()
            )
            val egl = EglBase.create()
            eglBase = egl
            val f = PeerConnectionFactory.builder()
                .setVideoDecoderFactory(DefaultVideoDecoderFactory(egl.eglBaseContext))
                .setVideoEncoderFactory(DefaultVideoEncoderFactory(egl.eglBaseContext, true, true))
                .createPeerConnectionFactory()
            factory = f
            return f
        }

        private fun randomHex(n: Int): String {
            val b = ByteArray(n)
            SecureRandom().nextBytes(b)
            return b.joinToString("") { "%02x".format(it) }.take(n)
        }
    }

    private var pc: PeerConnection? = null
    private var control: DataChannel? = null
    private var filesChannel: DataChannel? = null
    private var files: FileTransfer? = null

    @Volatile var perms = Perms()
        private set
    @Volatile var connected = false
        private set
    @Volatile private var closing = false

    private val hello = CompletableDeferred<JSONObject>()

    // ------------------------------------------------------------------ חיבור
    suspend fun connect(serverUrl: String, hostIdRaw: String, password: String): ConnectionInfo =
        withContext(Dispatchers.IO) {
            val hostId = Protocol.cleanId(hostIdRaw)
            val inbox = Channel<JSONObject>(Channel.UNLIMITED)
            val http = OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build()
            val ws = try {
                http.newWebSocket(Request.Builder().url(serverUrl).build(), object : WebSocketListener() {
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
            } catch (e: IllegalArgumentException) {
                throw ConnectException("bad server")
            }

            try {
                val me = "v" + randomHex(12)
                ws.send(JSONObject().put("type", "register").put("id", me).toString())
                expect(inbox, "registered", 10_000)

                fun relay(payload: JSONObject) {
                    ws.send(JSONObject().put("type", "relay").put("to", hostId).put("payload", payload).toString())
                }

                relay(JSONObject().put("kind", "hello"))
                val challenge = nextPayload(inbox, 10_000)
                when (challenge.optString("kind")) {
                    "reject" -> throw ConnectException(challenge.optString("reason", "rejected"))
                    "challenge" -> Unit
                    else -> throw ConnectException("protocol error")
                }
                val nonce = challenge.getString("nonce")
                val key: ByteArray? = if (password.isNotEmpty()) Protocol.deriveKey(password) else null

                // ---- WebRTC
                val f = ensureFactory(appContext)
                val gathered = CompletableDeferred<Unit>()
                val rtcConfig = PeerConnection.RTCConfiguration(
                    listOf(PeerConnection.IceServer.builder(STUN).createIceServer())
                ).apply { sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN }

                val peer = f.createPeerConnection(rtcConfig, object : SimplePcObserver() {
                    override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                        if (state == PeerConnection.IceGatheringState.COMPLETE) gathered.complete(Unit)
                    }

                    override fun onTrack(transceiver: RtpTransceiver) {
                        val t = transceiver.receiver.track()
                        if (t is VideoTrack) listener.onVideoTrack(t)
                    }

                    override fun onConnectionChange(newState: PeerConnection.PeerConnectionState) {
                        if (connected && (newState == PeerConnection.PeerConnectionState.FAILED ||
                                    newState == PeerConnection.PeerConnectionState.CLOSED)
                        ) {
                            close("connection lost")
                        }
                    }
                }) ?: throw ConnectException("internal error")
                pc = peer

                peer.addTransceiver(
                    MediaStreamTrack.MediaType.MEDIA_TYPE_VIDEO,
                    RtpTransceiver.RtpTransceiverInit(RtpTransceiver.RtpTransceiverDirection.RECV_ONLY),
                )
                control = peer.createDataChannel("control", DataChannel.Init())
                filesChannel = peer.createDataChannel("files", DataChannel.Init())
                control!!.registerObserver(SimpleDcObserver { onControlMessage(it) })
                files = FileTransfer(
                    filesChannel!!, downloadDir,
                    allowed = { perms.files },
                    onEvent = { kind, name, detail -> listener.onFileEvent(kind, name, detail) },
                )

                val offer = peer.awaitCreateOffer()
                peer.awaitSetLocal(offer)
                withTimeoutOrNull(10_000) { gathered.await() }   // ללא trickle: ממתינים לכל המועמדים
                val offerSdp = peer.localDescription.description

                relay(
                    JSONObject().put("kind", "offer").put("sdp", offerSdp)
                        .put("auth", if (key != null) Protocol.authTag(key, nonce, "viewer", offerSdp) else JSONObject.NULL)
                )

                val answer = nextPayload(inbox, 90_000)      // כולל המתנה לאישור המשתמש
                if (answer.optString("kind") == "reject") {
                    close("rejected")
                    throw ConnectException(answer.optString("reason", "rejected"))
                }
                if (answer.optString("kind") != "answer") {
                    close("protocol")
                    throw ConnectException("protocol error")
                }
                val answerSdp = answer.getString("sdp")
                var mode = "interactive"
                if (!answer.isNull("auth")) {
                    // סיסמה קבועה שהמארח הכיר: התשובה חתומה. אחרת (אישור משתמש) - קוד האבטחה מגן.
                    if (key == null || !Protocol.verifyTag(key, nonce, "host", answerSdp, answer.getString("auth"))) {
                        close("auth")
                        throw ConnectException("host authentication failed")
                    }
                    mode = "unattended"
                }
                val code = Protocol.sessionCode(offerSdp, answerSdp)
                peer.awaitSetRemote(SessionDescription(SessionDescription.Type.ANSWER, answerSdp))

                val h = withTimeoutOrNull(30_000) { hello.await() }
                if (h == null) {
                    close("timeout")
                    throw ConnectException("timed out waiting for host")
                }
                connected = true
                ConnectionInfo(
                    monitors = parseMonitors(h.optJSONArray("monitors")),
                    monitor = h.optInt("monitor", 1),
                    perms = perms,
                    mode = mode,
                    code = code,
                )
            } catch (e: ConnectException) {
                throw e
            } catch (e: Exception) {
                close("error")
                throw ConnectException(e.message ?: "connection failed")
            } finally {
                ws.close(1000, null)
                http.dispatcher.executorService.shutdown()
            }
        }

    private suspend fun expect(inbox: Channel<JSONObject>, type: String, timeoutMs: Long) {
        while (true) {
            val m = withTimeoutOrNull(timeoutMs) { inbox.receive() } ?: throw ConnectException("timed out waiting for host")
            when (m.optString("type")) {
                type -> return
                "error" -> throw ConnectException(m.optString("reason", "server error"))
                "ws_failure" -> throw ConnectException("server unreachable")
            }
        }
    }

    private suspend fun nextPayload(inbox: Channel<JSONObject>, timeoutMs: Long): JSONObject {
        while (true) {
            val m = withTimeoutOrNull(timeoutMs) { inbox.receive() } ?: throw ConnectException("timed out waiting for host")
            when (m.optString("type")) {
                "relay" -> return m.optJSONObject("payload") ?: JSONObject()
                "unreachable" -> throw ConnectException("host not found / offline")
                "ws_failure" -> throw ConnectException("server unreachable")
            }
        }
    }

    // ------------------------------------------------------------------ קליטה
    private fun onControlMessage(raw: String) {
        val m = runCatching { JSONObject(raw) }.getOrNull() ?: return
        when (m.optString("t")) {
            "hello" -> {
                perms = parsePerms(m.optJSONObject("perms"))
                hello.complete(m)
            }
            "perms" -> {
                perms = parsePerms(m.optJSONObject("perms"))
                listener.onPerms(perms)
            }
            "chat" -> listener.onChat(m.optString("text").take(2000))
            "clip" -> if (perms.clipboard) {
                val text = m.optString("text")
                if (text.toByteArray().size <= Protocol.MAX_CLIPBOARD_BYTES) listener.onClipboard(text)
            }
            "bye" -> close("host ended the session")
        }
    }

    private fun parsePerms(o: JSONObject?): Perms = if (o == null) Perms() else Perms(
        control = o.optBoolean("control", false),
        clipboard = o.optBoolean("clipboard", false),
        files = o.optBoolean("files", false),
        chat = o.optBoolean("chat", true),
    )

    private fun parseMonitors(a: JSONArray?): List<Monitor> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            a.optJSONObject(i)?.let { Monitor(it.optInt("index"), it.optInt("width"), it.optInt("height")) }
        }
    }

    // ------------------------------------------------------------------ שליחה
    private fun send(obj: JSONObject) {
        val dc = control ?: return
        if (dc.state() == DataChannel.State.OPEN) {
            dc.send(DataChannel.Buffer(ByteBuffer.wrap(obj.toString().toByteArray(Charsets.UTF_8)), false))
        }
    }

    /** אירוע קלט (עכבר/מקלדת). נשלח רק אם המארח אישר שליטה. */
    fun sendInput(ev: JSONObject) {
        if (perms.control) send(ev)
    }

    fun setQuality(fps: Int, scale: Double) = send(JSONObject().put("t", "cfg").put("fps", fps).put("scale", scale))

    fun setMonitor(index: Int) = send(JSONObject().put("t", "cfg").put("monitor", index))

    fun sendChat(text: String) = send(JSONObject().put("t", "chat").put("text", text.take(2000)))

    fun sendClipboard(text: String) {
        if (perms.clipboard && text.toByteArray().size <= Protocol.MAX_CLIPBOARD_BYTES) {
            send(JSONObject().put("t", "clip").put("text", text))
        }
    }

    suspend fun sendFile(context: Context, uri: android.net.Uri, name: String, size: Long) {
        if (!perms.files) {
            listener.onFileEvent("error", name, "file transfer not allowed")
            return
        }
        files?.sendFile(context, uri, name, size)
    }

    // ------------------------------------------------------------------ סיום
    fun disconnect() {
        if (connected) send(JSONObject().put("t", "bye"))
        close("disconnected")
    }

    @Synchronized
    fun close(reason: String) {
        if (closing) return
        closing = true
        val was = connected
        connected = false
        runCatching { files?.close() }
        runCatching { control?.close() }
        runCatching { filesChannel?.close() }
        runCatching { pc?.close() }
        runCatching { pc?.dispose() }
        pc = null
        if (was) listener.onClosed(reason)
    }
}

// ---------------------------------------------------------------------- עזרים של WebRTC
private suspend fun PeerConnection.awaitCreateOffer(): SessionDescription =
    suspendCancellableCoroutine { cont ->
        createOffer(object : SimpleSdpObserver() {
            override fun onCreateSuccess(sdp: SessionDescription) = cont.resume(sdp)
            override fun onCreateFailure(error: String) = cont.resumeWithException(ConnectException(error))
        }, MediaConstraints())
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

open class SimpleSdpObserver : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription) {}
    override fun onSetSuccess() {}
    override fun onCreateFailure(error: String) {}
    override fun onSetFailure(error: String) {}
}

open class SimplePcObserver : PeerConnection.Observer {
    override fun onSignalingChange(state: PeerConnection.SignalingState) {}
    override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {}
    override fun onIceConnectionReceivingChange(receiving: Boolean) {}
    override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {}
    override fun onIceCandidate(candidate: IceCandidate) {}
    override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) {}
    override fun onAddStream(stream: MediaStream) {}
    override fun onRemoveStream(stream: MediaStream) {}
    override fun onDataChannel(channel: DataChannel) {}
    override fun onRenegotiationNeeded() {}
}

/** עטיפה לטקסט בלבד: ההודעות בערוץ control הן JSON. */
class SimpleDcObserver(private val onText: (String) -> Unit) : DataChannel.Observer {
    override fun onBufferedAmountChange(previousAmount: Long) {}
    override fun onStateChange() {}
    override fun onMessage(buffer: DataChannel.Buffer) {
        if (buffer.binary) return
        val bytes = ByteArray(buffer.data.remaining())
        buffer.data.get(bytes)
        onText(String(bytes, Charsets.UTF_8))
    }
}
