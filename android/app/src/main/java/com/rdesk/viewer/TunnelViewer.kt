package com.rdesk.viewer

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.webrtc.DataChannel
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicInteger

/**
 * TCP Tunneling בצד הצופה (כמו ב-AnyDesk): שרת TCP מקומי לכל חוק העברה;
 * כל חיבור אליו הופך ל"זרם" אחד מעל data channel "tunnel", עד שהמארח
 * מאשר (opened) או דוחה (error). תואם בדיוק לפרוטוקול rdesk/tunnel.py::
 * TunnelViewer - אותה מיסגור (4 בתים ראשונים = stream id big-endian
 * בהודעות בינאריות; JSON open/opened/close/error בהודעות טקסט), כדי
 * שמארח Python יוכל לדבר עם זה בלי שום שינוי.
 */
class TunnelViewer(private val ch: DataChannel) {
    companion object {
        private const val HEADER_SIZE = 4
        private const val CHUNK = 16 * 1024
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val nextId = AtomicInteger(1)
    private val sockets = mutableMapOf<Int, Socket>()
    private val opened = mutableMapOf<Int, CompletableDeferred<Boolean>>()
    private val servers = mutableMapOf<Int, ServerSocket>()

    init {
        ch.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(previousAmount: Long) {}
            override fun onStateChange() {}
            override fun onMessage(buffer: DataChannel.Buffer) = handle(buffer)
        })
    }

    private fun handle(buffer: DataChannel.Buffer) {
        val bytes = ByteArray(buffer.data.remaining())
        buffer.data.get(bytes)
        if (buffer.binary) handleData(bytes) else handleControl(String(bytes, Charsets.UTF_8))
    }

    private fun handleControl(raw: String) {
        val m = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val sid = m.optInt("id", -1)
        when (m.optString("op")) {
            "opened" -> opened.remove(sid)?.complete(true)
            "error" -> opened.remove(sid)?.completeExceptionally(RuntimeException(m.optString("reason", "tunnel error")))
            "close" -> sockets.remove(sid)?.let { runCatching { it.close() } }
        }
    }

    private fun handleData(frame: ByteArray) {
        if (frame.size < HEADER_SIZE) return
        val sid = ByteBuffer.wrap(frame, 0, HEADER_SIZE).int
        val socket = sockets[sid] ?: return
        runCatching { socket.getOutputStream().write(frame, HEADER_SIZE, frame.size - HEADER_SIZE) }
    }

    private fun send(obj: JSONObject) {
        if (ch.state() == DataChannel.State.OPEN) {
            ch.send(DataChannel.Buffer(ByteBuffer.wrap(obj.toString().toByteArray(Charsets.UTF_8)), false))
        }
    }

    private fun sendData(sid: Int, payload: ByteArray, len: Int) {
        if (ch.state() != DataChannel.State.OPEN) return
        val buf = ByteBuffer.allocate(HEADER_SIZE + len)
        buf.putInt(sid)
        buf.put(payload, 0, len)
        buf.flip()
        ch.send(DataChannel.Buffer(buf, true))
    }

    /** פותח שרת TCP מקומי (127.0.0.1 בלבד) - חיבורים אליו מועברים ליעד
    המבוקש בצד המארח. זורק אם הפורט המקומי כבר תפוס. */
    suspend fun startForward(localPort: Int, remoteHost: String, remotePort: Int) {
        if (servers.containsKey(localPort)) throw IllegalStateException("port already forwarded")
        val server = withContext(Dispatchers.IO) {
            ServerSocket(localPort, 50, InetAddress.getByName("127.0.0.1"))
        }
        servers[localPort] = server
        scope.launch {
            while (!server.isClosed) {
                val client = try {
                    server.accept()
                } catch (e: Exception) {
                    break
                }
                scope.launch { handleClient(client, remoteHost, remotePort) }
            }
        }
    }

    private suspend fun handleClient(socket: Socket, remoteHost: String, remotePort: Int) {
        val sid = nextId.getAndIncrement()
        val fut = CompletableDeferred<Boolean>()
        opened[sid] = fut
        sockets[sid] = socket
        send(JSONObject().put("op", "open").put("id", sid).put("host", remoteHost).put("port", remotePort))
        try {
            withTimeout(10_000) { fut.await() }
        } catch (e: Exception) {
            sockets.remove(sid)
            runCatching { socket.close() }
            return
        }
        try {
            val input = socket.getInputStream()
            val buf = ByteArray(CHUNK)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                sendData(sid, buf, n)
            }
        } catch (e: Exception) {
            // זרם נסגר - מנוקה ב-finally
        } finally {
            send(JSONObject().put("op", "close").put("id", sid))
            sockets.remove(sid)
            runCatching { socket.close() }
        }
    }

    fun stopForward(localPort: Int) {
        servers.remove(localPort)?.let { runCatching { it.close() } }
    }

    fun activePorts(): List<Int> = servers.keys.toList()

    fun closeAll() {
        for (port in servers.keys.toList()) stopForward(port)
        for ((sid, socket) in sockets.toList()) {
            sockets.remove(sid)
            runCatching { socket.close() }
        }
        scope.cancel()
    }
}
