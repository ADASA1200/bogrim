package org.videoblock.adb

import android.content.Context

/**
 * Orchestrates self-provisioning: connect to the local adbd, run the provisioning script, and
 * interpret the result. Tries the classic cleartext adbd port (reachable after Wireless debugging
 * on API 30+, or a one-time `adb tcpip`). Reports clearly instead of failing silently.
 */
class Provisioner(private val context: Context) {

    data class Outcome(val ok: Boolean, val message: String, val blockingAccounts: List<String> = emptyList())

    /** Candidate local ADB ports to try, newest-discovered first. */
    fun candidatePorts(discovered: Int?): List<Int> =
        buildList { discovered?.let { add(it) }; add(5555); addAll(37000..37010) }.distinct()

    fun provision(discoveredPort: Int?): Outcome {
        val key = AdbKey.load(context)
        val script = context.assets.open("provision.sh").bufferedReader().use { it.readText() }
        // Keep the whole script on one `sh -c` so a single stream carries it.
        val command = "sh -c " + shellQuote(script)

        var lastError = "לא נמצא חיבור ADB מקומי"
        for (port in candidatePorts(discoveredPort)) {
            when (val r = AdbClient("127.0.0.1", port, key).runShell(command)) {
                is AdbClient.Result.Output -> return interpret(r.text)
                is AdbClient.Result.Failed -> lastError = r.reason
                AdbClient.Result.NeedsAuthApproval ->
                    return Outcome(false, "אשר את בקשת ניפוי הבאגים שמופיעה במסך ונסה שוב.")
            }
        }
        return Outcome(false, lastError)
    }

    private fun interpret(output: String): Outcome {
        val accounts = Regex("(?m)^VB_ACCOUNT:(.+)$").findAll(output).map { it.groupValues[1] }.toList()
        val ok = output.contains("VB_RESULT:OK")
        return when {
            ok -> Outcome(true, "החסימה הופעלה בהצלחה — האפליקציה כעת בעלים של המכשיר.")
            accounts.isNotEmpty() -> Outcome(false,
                "יש להסיר תחילה את החשבונות מהמכשיר (הגדרות ← חשבונות), ואז לנסות שוב.", accounts)
            else -> Outcome(false, "ההפעלה נכשלה. פלט: " + output.takeLast(300))
        }
    }

    /** Single-quote a script for `sh -c`, escaping embedded single quotes. */
    private fun shellQuote(s: String): String = "'" + s.replace("'", "'\\''") + "'"
}
