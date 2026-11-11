package org.videoblock

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.ScrollView
import org.videoblock.adb.Provisioner
import java.util.concurrent.atomic.AtomicInteger

/**
 * One-tap self-provisioning. The user turns on debugging; this activity connects to the device's
 * own adbd and runs `dpm set-device-owner` — no PC and no typed command. Everything happens only
 * after the user approves the on-device "Allow debugging" dialog.
 */
class ProvisioningActivity : Activity() {

    private val discoveredPort = AtomicInteger(0)
    private var nsd: NsdManager? = null
    private var listener: NsdManager.DiscoveryListener? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        render(null)
        startPortDiscovery()
    }

    private fun render(status: String?) {
        val col = column()
        col.addView(text("הפעלה אוטומטית של החסימה", 22f, bold = true))
        col.addView(text(
            "כך מפעילים את החסימה בלי מחשב ובלי להקליד פקודות:\n\n" +
            "1. פתח 'אפשרויות מפתחים' (הקש 7 פעמים על 'מספר גרסה' בתוך הגדרות ← אודות).\n" +
            (if (Build.VERSION.SDK_INT >= 30)
                "2. הפעל 'ניפוי באגים אלחוטי' (Wireless debugging).\n"
             else
                "2. הפעל 'ניפוי באגים ב-USB'.\n") +
            "3. חזור לכאן והקש 'הפעל חסימה'.\n" +
            "4. אשר את חלון 'אפשר ניפוי באגים' שיופיע. זהו — החסימה תופעל."
        ))
        col.addView(button("פתח אפשרויות מפתחים") {
            runCatching { startActivity(Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)) }
                .onFailure { runCatching { startActivity(Intent(Settings.ACTION_DEVICE_INFO_SETTINGS)) } }
        })
        col.addView(button("הפעל חסימה") { runProvision() })
        status?.let { col.addView(text(it, 16f, bold = true)) }
        col.addView(text(
            "אם מופיעה הודעה שצריך חיבור ADB: במכשירי אנדרואיד 11 ומעלה 'ניפוי אלחוטי' פותח " +
            "את החיבור לבד. במכשירים ישנים יותר ייתכן שצריך להפעיל פעם אחת 'adb tcpip 5555' ממחשב " +
            "(פעולה חד-פעמית). לאחר מכן האפליקציה עושה את כל השאר לבד.", 13f))
        setContentView(ScrollView(this).apply { addView(col) })
    }

    private fun runProvision() {
        render("מתחבר… אשר את חלון ניפוי הבאגים אם הוא מופיע.")
        Thread {
            val port = discoveredPort.get().takeIf { it > 0 }
            val outcome = Provisioner(this).provision(port)
            runOnUiThread {
                if (outcome.ok) {
                    Policy.enforceAsync(this)
                    toast("החסימה הופעלה")
                    startActivity(Intent(this, MainActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
                    finish()
                } else render(outcome.message)
            }
        }.start()
    }

    /** Looks for the wireless-debugging connect service on API 30+, to learn its port. */
    private fun startPortDiscovery() {
        if (Build.VERSION.SDK_INT < 30) return
        val manager = getSystemService(Context.NSD_SERVICE) as? NsdManager ?: return
        nsd = manager
        listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {}
            override fun onServiceFound(info: NsdServiceInfo) {
                runCatching {
                    manager.resolveService(info, object : NsdManager.ResolveListener {
                        override fun onServiceResolved(s: NsdServiceInfo) { discoveredPort.set(s.port) }
                        override fun onResolveFailed(s: NsdServiceInfo, e: Int) {}
                    })
                }
            }
            override fun onServiceLost(info: NsdServiceInfo) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
        }
        runCatching {
            manager.discoverServices("_adb-tls-connect._tcp", NsdManager.PROTOCOL_DNS_SD, listener)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        runCatching { listener?.let { nsd?.stopServiceDiscovery(it) } }
    }
}
