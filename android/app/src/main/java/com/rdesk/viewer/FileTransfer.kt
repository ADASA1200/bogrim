package com.rdesk.viewer

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.webrtc.DataChannel
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.security.SecureRandom

/**
 * העברת קבצים על ערוץ "files". תואם ל-rdesk/files.py:
 * JSON {"op":"start","name","size"} -> חתיכות בינאריות -> {"op":"end"}.
 * kind באירועים: incoming / received / sending / sent / error.
 */
class FileTransfer(
    private val ch: DataChannel,
    private val dir: File,
    private val allowed: () -> Boolean,
    private val onEvent: (kind: String, name: String, detail: String) -> Unit,
) {
    private var out: FileOutputStream? = null
    private var target: File? = null
    private var name = ""
    private var expected = 0L
    private var got = 0L

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
        if (buffer.binary) {
            val o = out ?: return
            got += bytes.size
            if (got > expected) { abort("file larger than announced"); return }
            o.write(bytes)
            return
        }
        val m = runCatching { JSONObject(String(bytes, Charsets.UTF_8)) }.getOrNull() ?: return
        when (m.optString("op")) {
            "start" -> {
                abortSilent()
                val size = m.optLong("size", -1)
                if (!allowed()) { sendJson(JSONObject().put("op", "denied").put("reason", "file transfer not allowed")); return }
                if (size < 0 || size > 2L * 1024 * 1024 * 1024) { sendJson(JSONObject().put("op", "denied").put("reason", "bad size")); return }
                dir.mkdirs()
                name = Protocol.safeFileName(m.optString("name"))
                var f = File(dir, name)
                while (f.exists()) {
                    val suffix = ByteArray(2).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
                    f = File(dir, "${f.nameWithoutExtension}-$suffix${if (f.extension.isEmpty()) "" else "." + f.extension}")
                }
                target = f
                out = FileOutputStream(f)
                expected = size
                got = 0
                onEvent("incoming", name, size.toString())
            }
            "end" -> {
                val o = out ?: return
                o.close(); out = null
                if (got == expected) onEvent("received", name, target?.absolutePath ?: "")
                else { target?.delete(); onEvent("error", name, "incomplete") }
            }
            "denied" -> onEvent("error", "", m.optString("reason", "denied"))
        }
    }

    private fun abort(reason: String) {
        val n = name
        abortSilent()
        onEvent("error", n, reason)
    }

    private fun abortSilent() {
        runCatching { out?.close() }
        out = null
        target?.delete()
        target = null
    }

    fun close() = abortSilent()

    private fun sendJson(o: JSONObject) {
        if (ch.state() == DataChannel.State.OPEN) {
            ch.send(DataChannel.Buffer(ByteBuffer.wrap(o.toString().toByteArray(Charsets.UTF_8)), false))
        }
    }

    suspend fun sendFile(context: Context, uri: Uri, fileName: String, size: Long) = withContext(Dispatchers.IO) {
        try {
            val input = context.contentResolver.openInputStream(uri) ?: throw IllegalStateException("cannot open file")
            input.use { ins ->
                sendJson(JSONObject().put("op", "start").put("name", fileName).put("size", size))
                val buf = ByteArray(Protocol.FILE_CHUNK)
                var sent = 0L
                while (true) {
                    val n = ins.read(buf)
                    if (n <= 0) break
                    while (ch.bufferedAmount() > 1_000_000) delay(10)        // backpressure
                    if (ch.state() != DataChannel.State.OPEN) throw IllegalStateException("channel closed")
                    ch.send(DataChannel.Buffer(ByteBuffer.wrap(buf.copyOf(n)), true))
                    sent += n
                    onEvent("sending", fileName, "$sent/$size")
                }
                sendJson(JSONObject().put("op", "end"))
            }
            onEvent("sent", fileName, "")
        } catch (e: Exception) {
            onEvent("error", fileName, e.message ?: "failed")
        }
    }
}
