package org.videoblock.adb

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
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
        // A multicast lock is required on most devices to actually receive mDNS replies.
        val lock = acquireMulticastLock()
        val mdns = AdbMdns(context, serviceType) { addr: InetAddress?, port: Int ->
            if (addr != null && port > 0 && found.get() == null) {
                found.set(Endpoint(addr.hostAddress ?: "127.0.0.1", port))
                latch.countDown()
            }
        }
        log("מחפש שירות $serviceType ברשת המקומית…")
        try {
            mdns.start()
            latch.await(timeoutSec, TimeUnit.SECONDS)
        } finally {
            runCatching { mdns.stop() }
            runCatching { lock?.release() }
        }
        val ep = found.get()
        if (ep != null) log("נמצא $serviceType בכתובת ${ep.host}:${ep.port}")
        else log("לא נמצא $serviceType (ודא שניפוי הבאגים האלחוטי פתוח ושאישרת הרשאת רשת).")
        return ep
    }

    private fun acquireMulticastLock(): WifiManager.MulticastLock? = try {
        val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        wifi?.createMulticastLock("videoblock-adb")?.apply { setReferenceCounted(true); acquire() }
    } catch (t: Throwable) { log("אזהרה: לא ניתן לנעול multicast (${t.message})"); null }

    /** API 30+: pair with the 6-digit code shown under "Pair device with pairing code". */
    fun pair(code: String): Boolean {
        val ep = discover(AdbMdns.SERVICE_TYPE_TLS_PAIRING, 25) ?: return false
        val mgr = try { AdbManager.create(context) }
        catch (t: Throwable) { logError("יצירת זהות ADB", t); return false }
        return try {
            log("מבצע צימוד (SPAKE2) מול ${ep.host}:${ep.port}…")
            val ok = mgr.pair(ep.host, ep.port, code)
            log(if (ok) "הצימוד הצליח ✔" else "הצימוד נכשל ✖")
            ok
        } catch (t: Throwable) {
            logError("צימוד", t)
            false
        } finally {
            runCatching { mgr.close() }
        }
    }

    /** Connects and runs the provisioning script. Tries the classic local port first, then mDNS. */
    fun connectAndProvision(): Result {
        val mgr = try { AdbManager.create(context) }
        catch (t: Throwable) { logError("יצירת זהות ADB", t); return Result(false, "שגיאה ביצירת זהות ADB") }
        try {
            // 1) Direct classic adbd port (how PCAPdroid-MDM connects). Works when `adb tcpip` was
            //    enabled, on USB-over-TCP, or on rooted devices — no mDNS needed.
            for (port in listOf(5555)) {
                if (tryConnect(mgr, "127.0.0.1", port)) return runScript(mgr)
            }
            // 2) Wireless-debugging connect service via mDNS (API 30+, after pairing).
            if (Build.VERSION.SDK_INT >= 30) {
                val ep = discover(AdbMdns.SERVICE_TYPE_TLS_CONNECT, 20)
                if (ep != null && tryConnect(mgr, ep.host, ep.port)) return runScript(mgr)
            }
            log("לא נמצא חיבור ADB זמין.")
            return Result(false,
                if (Build.VERSION.SDK_INT >= 30)
                    "לא נמצא חיבור. ב-אנדרואיד 11+: בצע קודם 'צימוד באמצעות קוד' (כפתור 'צמד והפעל')."
                else
                    "לא נמצא חיבור. במכשיר זה יש להפעיל פעם אחת ממחשב: adb tcpip 5555, ואז לנסות שוב.")
        } catch (t: Throwable) {
            logError("חיבור/הפעלה", t)
            return Result(false, "שגיאה: ${t.message ?: t.javaClass.simpleName}")
        } finally {
            runCatching { mgr.close() }
        }
    }

    /** Attempts one ADB connection; logs the outcome. Returns true only if fully connected. */
    private fun tryConnect(mgr: AdbManager, host: String, port: Int): Boolean {
        return try {
            log("מנסה חיבור ל-$host:$port… (אשר את חלון ניפוי הבאגים אם יופיע)")
            val ok = mgr.connect(host, port)
            log(if (ok) "מחובר ל-$host:$port ✔" else "אין מענה ב-$host:$port")
            ok
        } catch (e: io.github.muntashirakon.adb.AdbPairingRequiredException) {
            log("$host:$port דורש צימוד (TLS). דלג.")
            false
        } catch (t: Throwable) {
            log("$host:$port נכשל: ${t.javaClass.simpleName}: ${t.message}")
            false
        }
    }

    private fun runScript(mgr: AdbManager): Result {
        log("מחובר. מריץ את סקריפט ההפעלה…")
        val script = context.assets.open("provision.sh").bufferedReader().use { it.readText() }
        val output = mgr.runShell("sh -c " + shellQuote(script))
        output.lineSequence().forEach { if (it.isNotBlank()) log("  $it") }
        return interpret(output)
    }

    /** Logs an exception with its type, message and first stack frames, for diagnosis. */
    private fun logError(stage: String, t: Throwable) {
        log("✖ שגיאה בשלב '$stage': ${t.javaClass.name}: ${t.message}")
        t.cause?.let { log("   סיבה: ${it.javaClass.name}: ${it.message}") }
        t.stackTrace.take(4).forEach { log("   at $it") }
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
