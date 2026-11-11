package org.videoblock.adb

import java.io.BufferedInputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket

/**
 * Minimal ADB host client that connects to the device's own adbd over TCP and runs one shell
 * command. Used for self-provisioning: the app runs `dpm set-device-owner` on itself after the
 * user turns on debugging and approves the on-device authorization dialog.
 *
 * The RSA-auth path is pure Kotlin and needs no native code. It requires the adbd TCP port to be
 * reachable: on Android 11+ via Wireless debugging, or on any version via a one-time `adb tcpip`.
 */
class AdbClient(private val host: String, private val port: Int, private val key: AdbKey) {

    sealed class Result {
        data class Output(val text: String) : Result()
        object NeedsAuthApproval : Result()   // device is showing the "Allow debugging?" dialog
        data class Failed(val reason: String) : Result()
    }

    /** Connects, authenticates, runs [command] in a shell and returns its combined output. */
    fun runShell(command: String, connectTimeoutMs: Int = 5000, ioTimeoutMs: Int = 20000): Result {
        Socket().use { socket ->
            try {
                socket.connect(InetSocketAddress(host, port), connectTimeoutMs)
                socket.soTimeout = ioTimeoutMs
            } catch (e: Exception) {
                return Result.Failed("לא ניתן להתחבר ל-$host:$port (${e.message})")
            }
            val input = BufferedInputStream(socket.getInputStream())
            val out = socket.getOutputStream()

            // CNXN handshake.
            AdbProtocol.write(out, AdbProtocol.encode(AdbProtocol.CNXN, AdbProtocol.VERSION,
                AdbProtocol.MAX_DATA, "host::features=shell_v2,cmd\u0000".toByteArray()))

            var sentSignature = false
            while (true) {
                val msg = try { AdbProtocol.read(input) }
                catch (e: Exception) { return Result.Failed("החיבור נסגר (${e.message})") }
                when (msg.command) {
                    AdbProtocol.AUTH -> {
                        if (!sentSignature) {
                            // First challenge: sign the token with our private key.
                            sentSignature = true
                            AdbProtocol.write(out, AdbProtocol.encode(
                                AdbProtocol.AUTH, AdbProtocol.AUTH_SIGNATURE, 0, key.sign(msg.payload)))
                        } else {
                            // Key unknown to this device: send the public key; adbd prompts the user.
                            AdbProtocol.write(out, AdbProtocol.encode(
                                AdbProtocol.AUTH, AdbProtocol.AUTH_RSAPUBLICKEY, 0, key.adbPublicKey()))
                            // We cannot proceed until the user taps "Allow".
                            socket.soTimeout = 60000
                        }
                    }
                    AdbProtocol.CNXN -> return openShell(input, out, command)
                    AdbProtocol.CLSE -> return Result.Failed("adbd סגר את החיבור")
                    else -> { /* ignore until authenticated */ }
                }
            }
        }
    }

    private fun openShell(input: BufferedInputStream, out: OutputStream, command: String): Result {
        val localId = 1
        AdbProtocol.write(out, AdbProtocol.encode(
            AdbProtocol.OPEN, localId, 0, "shell:$command\u0000".toByteArray()))
        val sb = StringBuilder()
        var remoteId = 0
        while (true) {
            val msg = try { AdbProtocol.read(input) }
            catch (e: java.io.EOFException) { break }
            catch (e: Exception) { return Result.Failed("שגיאת קריאה (${e.message})") }
            when (msg.command) {
                AdbProtocol.OKAY -> remoteId = msg.arg0
                AdbProtocol.WRTE -> {
                    sb.append(decodeShell(msg.payload))
                    AdbProtocol.write(out, AdbProtocol.encode(AdbProtocol.OKAY, localId, msg.arg0, ByteArray(0)))
                }
                AdbProtocol.CLSE -> {
                    AdbProtocol.write(out, AdbProtocol.encode(AdbProtocol.CLSE, localId, remoteId, ByteArray(0)))
                    break
                }
            }
        }
        return Result.Output(sb.toString())
    }

    /** shell_v2 frames output as [id(1)][len(4 LE)][data]; fall back to raw bytes otherwise. */
    private fun decodeShell(payload: ByteArray): String {
        if (payload.size >= 5 && payload[0].toInt() in 0..2) {
            val sb = StringBuilder(); var i = 0
            while (i + 5 <= payload.size) {
                val id = payload[i].toInt()
                val len = (payload[i + 1].toInt() and 0xFF) or ((payload[i + 2].toInt() and 0xFF) shl 8) or
                        ((payload[i + 3].toInt() and 0xFF) shl 16) or ((payload[i + 4].toInt() and 0xFF) shl 24)
                i += 5
                if (len < 0 || i + len > payload.size) break
                if (id == 1 || id == 2) sb.append(String(payload, i, len))
                i += len
            }
            if (sb.isNotEmpty()) return sb.toString()
        }
        return String(payload)
    }
}
