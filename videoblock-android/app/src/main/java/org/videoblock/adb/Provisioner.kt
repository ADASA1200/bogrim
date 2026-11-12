package org.videoblock.adb

import android.content.Context
import io.github.muntashirakon.adb.android.AdbMdns
import java.net.InetAddress
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Drives self-provisioning end to end and reports every step through [log] so the user can see
 * exactly what happened (addresses, ports, errors) — the extended diagnostics.
 */
class Provisioner(private val context: Context, private val log: (String) -> Unit) {

    data class Endpoint(val host: String, val port: Int)

    data class Result(val ok: Boolean, val message: String, val accounts: List<String> = emptyList())

    /** Discovers an adb mDNS service (pairing or connect) and returns its host/port. */
    fun discover(serviceType: String, timeoutSec: Long): Endpoint? {
        val latch = CountDownLatch(1)
        val found = java.util.concurrent.atomic.AtomicReference<Endpoint?>(null)
        val mdns = AdbMdns(context, serviceType) { addr: InetAddress?, port: Int ->
            if (addr != null && port > 0 && found.get() == null) {
                found.set(Endpoint(addr.hostAddress ?: "127.0.0.1", port))
                latch.countDown()
            }
        }
        log("מחפש שירות $serviceType ברשת המקומית…")
        mdns.start()
        latch.await(timeoutSec, TimeUnit.SECONDS)
        mdns.stop()
        val ep = found.get()
        if (ep != null) log("נמצא $serviceType בכתובת ${ep.host}:${ep.port}")
        else log("לא נמצא $serviceType (ודא שניפוי הבאגים האלחוטי פתוח).")
        return ep
    }

    /** API 30+: pair with the 6-digit code shown under "Pair device with pairing code". */
    fun pair(code: String): Boolean {
        val ep = discover(AdbMdns.SERVICE_TYPE_TLS_PAIRING, 25) ?: return false
        return try {
            log("מבצע צימוד (SPAKE2) מול ${ep.host}:${ep.port}…")
            val ok = AdbManager.get(context).pair(ep.host, ep.port, code)
            log(if (ok) "הצימוד הצליח ✔" else "הצימוד נכשל ✖")
            ok
        } catch (e: Exception) {
            log("שגיאת צימוד: ${e.javaClass.simpleName}: ${e.message}")
            false
        }
    }

    /** Connects (discovering the connect port) and runs the provisioning script. */
    fun connectAndProvision(): Result {
        val mgr = AdbManager.get(context)
        try {
            log("מתחבר ל-adbd…")
            val connected = mgr.autoConnect(context, 25_000)
            if (!connected) {
                log("החיבור נכשל.")
                return Result(false, "לא ניתן להתחבר. ודא שניפוי הבאגים פעיל ושאישרת את הבקשה במכשיר.")
            }
            log("מחובר. מריץ את סקריפט ההפעלה…")
            val script = context.assets.open("provision.sh").bufferedReader().use { it.readText() }
            val output = mgr.runShell("sh -c " + shellQuote(script))
            output.lineSequence().forEach { if (it.isNotBlank()) log("  $it") }
            return interpret(output)
        } catch (e: io.github.muntashirakon.adb.AdbPairingRequiredException) {
            log("נדרש צימוד תחילה (אנדרואיד 11+).")
            return Result(false, "יש לבצע צימוד תחילה: פתח 'Pair device with pairing code', והזן את הקוד כאן.")
        } catch (e: Exception) {
            log("שגיאה: ${e.javaClass.simpleName}: ${e.message}")
            return Result(false, "שגיאה: ${e.message}")
        } finally {
            runCatching { mgr.close() }
        }
    }

    private fun interpret(output: String): Result {
        val accounts = Regex("(?m)^VB_ACCOUNT:(.+)$").findAll(output).map { it.groupValues[1] }.toList()
        return when {
            output.contains("VB_RESULT:OK") ->
                Result(true, "ההגנה הופעלה בהצלחה — האפליקציה כעת בעלים של המכשיר.")
            accounts.isNotEmpty() ->
                Result(false, "יש להסיר תחילה את החשבונות מהמכשיר (הגדרות ← חשבונות) ואז לנסות שוב.", accounts)
            else -> Result(false, "ההפעלה נכשלה. ראה לוג מפורט למטה.")
        }
    }

    private fun shellQuote(s: String): String = "'" + s.replace("'", "'\\''") + "'"
}
