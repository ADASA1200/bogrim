package org.videoblock

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.text.method.ScrollingMovementMethod
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import org.videoblock.adb.Provisioner
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * One-tap self-provisioning with full diagnostics. The user enables debugging, (on Android 11+)
 * pairs with the 6-digit code, and the app runs `dpm set-device-owner` over a local ADB
 * connection — no PC. Every step is written to an on-screen log.
 */
class ProvisioningActivity : AppCompatActivity() {

    private val logText = StringBuilder()
    private lateinit var logView: TextView
    private val ui = android.os.Handler(android.os.Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNetworkPermissions()
        val col = column()
        col.addView(header("הפעלה אוטומטית", "ללא מחשב — האפליקציה מפעילה את עצמה"))

        col.addView(card {
            val wireless = Build.VERSION.SDK_INT >= 30
            addView(text("שלבים", 18f, bold = true))
            addView(text(
                "1. פתח 'אפשרויות מפתחים' (7 הקשות על 'מספר גרסה' בהגדרות ← אודות).\n" +
                (if (wireless)
                    "2. הפעל 'ניפוי באגים אלחוטי'.\n" +
                    "3. היכנס ל'התאמה באמצעות קוד' (Pair device with pairing code) — יוצג קוד בן 6 ספרות.\n" +
                    "4. הקלד כאן את הקוד והקש 'צמד והפעל'."
                 else
                    "2. הפעל 'ניפוי באגים ב-USB'.\n" +
                    "3. הקש 'חבר והפעל' ואשר את חלון ניפוי הבאגים.")
            ))
            addView(outlinedButton("פתח אפשרויות מפתחים") { openDev() })
        })

        if (Build.VERSION.SDK_INT >= 30) {
            col.addView(card {
                addView(text("צימוד אלחוטי", 18f, bold = true))
                val (layout, edit) = codeField()
                addView(layout)
                addView(button("צמד והפעל") {
                    val code = edit.text.toString().trim()
                    if (code.length < 6) { toast("הקלד את קוד הצימוד בן 6 הספרות"); return@button }
                    runFlow(pairCode = code)
                })
            })
        }

        col.addView(card {
            addView(text("כבר מצומד? (או ניפוי USB)", 16f, bold = true))
            addView(outlinedButton("חבר והפעל") { runFlow(pairCode = null) })
        })

        // Extended diagnostics log.
        col.addView(card {
            addView(text("לוג מפורט", 16f, bold = true))
            logView = TextView(this@ProvisioningActivity).apply {
                textSize = 12f
                setTextColor(resources.getColor(R.color.muted))
                typeface = android.graphics.Typeface.MONOSPACE
                textDirection = View.TEXT_DIRECTION_LTR
                gravity = Gravity.START
                movementMethod = ScrollingMovementMethod()
                minLines = 6
            }
            addView(logView)
            addView(outlinedButton("העתק לוג") {
                (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                    .setPrimaryClip(ClipData.newPlainText("log", logText.toString()))
                toast("הלוג הועתק")
            })
        })

        setContentView(ScrollView(this).apply { addView(col) })
        log("מוכן. אנדרואיד API ${Build.VERSION.SDK_INT}.")
    }

    private fun codeField(): Pair<TextInputLayout, TextInputEditText> {
        val edit = TextInputEditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            textDirection = View.TEXT_DIRECTION_LTR
            gravity = Gravity.CENTER
            textSize = 22f
        }
        val layout = TextInputLayout(this).apply {
            hint = "קוד צימוד (6 ספרות)"
            addView(edit)
        }
        return layout to edit
    }

    /** mDNS discovery of the local adbd needs these at runtime (NEARBY_WIFI_DEVICES on API 33+). */
    private fun requestNetworkPermissions() {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(android.Manifest.permission.NEARBY_WIFI_DEVICES) !=
                android.content.pm.PackageManager.PERMISSION_GRANTED)
                needed += android.Manifest.permission.NEARBY_WIFI_DEVICES
        } else {
            if (checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) !=
                android.content.pm.PackageManager.PERMISSION_GRANTED)
                needed += android.Manifest.permission.ACCESS_FINE_LOCATION
        }
        if (needed.isNotEmpty()) runCatching { requestPermissions(needed.toTypedArray(), 7) }
    }

    private fun openDev() {
        runCatching { startActivity(Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)) }
            .onFailure { runCatching { startActivity(Intent(Settings.ACTION_DEVICE_INFO_SETTINGS)) } }
    }

    private fun runFlow(pairCode: String?) {
        log("— מתחיל —")
        Thread {
            // Catch everything: a crash on this worker would kill the app before the log is seen.
            try {
                val prov = Provisioner(this) { line -> log(line) }
                if (pairCode != null) {
                    if (!prov.pair(pairCode)) {
                        ui.post { toast("הצימוד נכשל — ראה לוג") }
                        return@Thread
                    }
                }
                val result = prov.connectAndProvision()
                ui.post {
                    if (result.ok) {
                        Policy.enforceAsync(this)
                        toast("ההגנה הופעלה")
                        startActivity(Intent(this, MainActivity::class.java)
                            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
                        finish()
                    } else toast(result.message)
                }
            } catch (t: Throwable) {
                log("✖ קריסה נמנעה: ${t.javaClass.name}: ${t.message}")
                t.stackTrace.take(6).forEach { log("   at $it") }
                ui.post { toast("אירעה שגיאה — ראה לוג מפורט") }
            }
        }.start()
    }

    private fun log(line: String) {
        val ts = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        synchronized(logText) { logText.append("[$ts] ").append(line).append('\n') }
        ui.post {
            logView.text = logText.toString()
            (logView.parent.parent as? ScrollView)?.post { }
        }
    }
}
