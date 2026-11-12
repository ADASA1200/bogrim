package org.videoblock

import androidx.appcompat.app.AppCompatActivity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.widget.ScrollView

class MainActivity : AppCompatActivity() {

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun render() {
        val prefs = Prefs(this)
        val col = column()

        if (!Policy.isDeviceOwner(this)) {
            col.addView(header(getString(R.string.app_name), "חסימת וידאו לכל המכשיר"))
            renderSetup(col)
        } else {
            Policy.enforceAsync(this)
            if (!prefs.hasPin) newPin(cancelable = false) { render() }
            col.addView(header(getString(R.string.app_name), "ההגנה פעילה"))
            val blocked = prefs.suspendedByUs.size
            col.addView(card {
                addView(text("✅ ההגנה פעילה", 20f, bold = true, color = resources.getColor(R.color.ok)))
                addView(text(
                    "• $blocked אפליקציות וידאו / דפדפנים חסומים\n" +
                    "• סינון DNS חוסם אתרי וידאו בכל האפליקציות\n" +
                    "• אפליקציות וידאו חדשות נחסמות אוטומטית בהתקנה\n" +
                    "• לא ניתן להסיר את התוכנה, לאפס מההגדרות, להיכנס למצב בטוח, " +
                    "להפעיל ADB, להחליף VPN או להעביר קבצים ב-USB / כרטיס זיכרון"
                ))
                if (prefs.blockCamera) addView(text("• המצלמה חסומה"))
            })
            if (!a11yEnabled()) {
                col.addView(card {
                    addView(text("שכבת הגנה נוספת", 16f, bold = true))
                    addView(text("סגירת וידאו גם בתוך אפליקציות פתוחות (מסרונים, דפדפן). הפעל את שירות הנגישות:"))
                    addView(button("הפעלת שכבת חסימת וידאו") {
                        runCatching { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
                    })
                })
            }
            if (prefs.permanent) {
                col.addView(card {
                    addView(text("🔒 המכשיר נעול לצמיתות. לא ניתן לשנות הגדרות או להסיר את ההגנה.",
                        bold = true))
                })
            } else {
                col.addView(card {
                    addView(text("ניהול", 16f, bold = true))
                    addView(text("להסרת ההגנה או לשינוי הגדרות — הזן את סיסמת ההסרה שהגדרת."))
                    addView(button("ניהול והסרה (דורש סיסמה)") {
                        askPin { startActivity(Intent(this@MainActivity, AdminActivity::class.java)) }
                    })
                })
            }
        }
        setContentView(ScrollView(this).apply {
            setBackgroundColor(resources.getColor(R.color.bg)); addView(col)
        })
    }

    private fun a11yEnabled(): Boolean {
        val flat = Settings.Secure.getString(contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        val me = "$packageName/${MediaBlockService::class.java.name}"
        val split = TextUtils.SimpleStringSplitter(':')
        split.setString(flat)
        while (split.hasNext()) if (split.next().equals(me, true)) return true
        return false
    }

    private fun renderSetup(col: android.widget.LinearLayout) {
        val prefs = Prefs(this)

        // Step 1 — define the removal password BEFORE protection is enabled.
        // This same password is later required to open settings or remove the protection.
        if (!prefs.hasPin) {
            col.addView(card {
                addView(text("שלב 1 מתוך 2", 14f, bold = true, color = resources.getColor(R.color.muted)))
                addView(text("הגדרת סיסמת הסרה", 20f, bold = true))
                addView(text(
                    "לפני הפעלת ההגנה יש להגדיר סיסמה. רק באמצעותה יהיה ניתן בעתיד להסיר את ההגנה " +
                    "או לשנות הגדרות. מומלץ למסור אותה לאדם אחר (רב / הורה / חבר).\n\n" +
                    "בלי סיסמה זו לא ניתן להמשיך."
                ))
                addView(button("הגדר סיסמת הסרה") { newPin(cancelable = false) { render() } })
            })
            return
        }

        col.addView(card {
            addView(text("✅ שלב 1: סיסמת ההסרה הוגדרה", 16f, bold = true, color = resources.getColor(R.color.ok)))
            addView(outlinedButton("שינוי סיסמת ההסרה") { askPin { newPin(cancelable = true) {} } })
        })

        // Step 2 — activate protection (Device Owner).
        val cmd = "adb shell dpm set-device-owner $packageName/.AdminReceiver"
        col.addView(card {
            addView(text("שלב 2 מתוך 2", 14f, bold = true, color = resources.getColor(R.color.muted)))
            addView(text("הפעלת ההגנה", 20f, bold = true))
            addView(text(
                "התוכנה חייבת לפעול כ\"בעלים של המכשיר\" (Device Owner). הדרך הקלה היא אוטומטית, ללא מחשב:"
            ))
            addView(button("⚡ הפעלה אוטומטית (ללא מחשב)") {
                startActivity(Intent(this@MainActivity, ProvisioningActivity::class.java))
            })
            addView(text(
                "או ידנית ממחשב: מחק את כל החשבונות (הגדרות ← חשבונות), הפעל 'ניפוי באגים ב-USB', חבר למחשב והרץ:",
                14f
            ))
            addView(text(cmd, 13f, bold = true))
            addView(outlinedButton("העתק פקודה") {
                (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                    .setPrimaryClip(ClipData.newPlainText("cmd", cmd))
                toast("הועתק")
            })
        })
    }
}
