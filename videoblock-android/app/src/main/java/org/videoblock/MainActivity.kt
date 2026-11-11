package org.videoblock

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.widget.ScrollView

class MainActivity : Activity() {

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun render() {
        val prefs = Prefs(this)
        val col = column()
        col.addView(text(getString(R.string.app_name), 26f, bold = true))

        if (!Policy.isDeviceOwner(this)) {
            renderSetup(col)
        } else {
            Policy.enforceAsync(this)
            if (!prefs.hasPin) newPin(cancelable = false) { render() }
            val blocked = prefs.suspendedByUs.size
            col.addView(text("✅ ההגנה פעילה", 20f, bold = true))
            col.addView(text(
                "• $blocked אפליקציות וידאו / דפדפנים חסומים\n" +
                "• סינון DNS חוסם אתרי וידאו בכל האפליקציות\n" +
                "• אפליקציות וידאו חדשות נחסמות אוטומטית בהתקנה\n" +
                "• לא ניתן להסיר את התוכנה, לאפס את המכשיר מההגדרות, להיכנס למצב בטוח, " +
                "להפעיל ADB, להחליף VPN או להעביר קבצים ב-USB / כרטיס זיכרון"
            ))
            if (prefs.blockCamera) col.addView(text("• המצלמה חסומה"))
            if (!a11yEnabled()) {
                col.addView(text("לשכבת הגנה נוספת (סגירת וידאו גם בתוך אפליקציות פתוחות) יש להפעיל את שירות הנגישות:"))
                col.addView(button("הפעלת שכבת חסימת וידאו") {
                    runCatching { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
                })
            }
            if (prefs.permanent) {
                col.addView(text("🔒 המכשיר נעול לצמיתות. לא ניתן לשנות הגדרות או להסיר את ההגנה.", bold = true))
            } else {
                col.addView(text("להסרת ההגנה או לשינוי הגדרות — הזן את סיסמת ההסרה שהגדרת:"))
                col.addView(button("ניהול והסרה (דורש סיסמה)") {
                    askPin { startActivity(Intent(this, AdminActivity::class.java)) }
                })
            }
        }
        setContentView(ScrollView(this).apply { addView(col) })
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
        col.addView(text("התקנה", 20f, bold = true))

        // Step 1 — define the removal password BEFORE protection is enabled.
        // This same password is later required to open settings or remove the protection.
        if (!prefs.hasPin) {
            col.addView(text("שלב 1 מתוך 2: הגדרת סיסמת הסרה", 18f, bold = true))
            col.addView(text(
                "לפני הפעלת ההגנה יש להגדיר סיסמה. רק באמצעותה יהיה ניתן בעתיד להסיר את ההגנה " +
                "או לשנות הגדרות. מומלץ למסור אותה לאדם אחר (רב / הורה / חבר) ולא לשמור אותה אצלך.\n\n" +
                "בלי סיסמה זו לא ניתן להמשיך."
            ))
            col.addView(button("הגדר סיסמת הסרה") { newPin(cancelable = false) { render() } })
            return
        }

        col.addView(text("✅ שלב 1: סיסמת ההסרה הוגדרה", 16f, bold = true))
        col.addView(button("שינוי סיסמת ההסרה") { askPin { newPin(cancelable = true) {} } })

        // Step 2 — activate protection (Device Owner).
        val cmd = "adb shell dpm set-device-owner $packageName/.AdminReceiver"
        col.addView(text("שלב 2 מתוך 2: הפעלת ההגנה", 18f, bold = true))
        col.addView(text(
            "כדי שלא יהיה ניתן להסיר את החסימה בשום צורה, התוכנה חייבת לפעול כ\"בעלים של המכשיר\" " +
            "(Device Owner). הדרך הקלה היא אוטומטית, ללא מחשב:"
        ))
        col.addView(button("⚡ הפעלה אוטומטית (ללא מחשב)") {
            startActivity(Intent(this, ProvisioningActivity::class.java))
        })
        col.addView(text(
            "או הפעלה ידנית ממחשב: מחק את כל החשבונות (הגדרות ← חשבונות), הפעל 'ניפוי באגים ב-USB', " +
            "חבר למחשב והרץ:"
        ))
        col.addView(text(cmd, 14f, bold = true))
        col.addView(button("העתק פקודה") {
            (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                .setPrimaryClip(ClipData.newPlainText("cmd", cmd))
            toast("הועתק")
        })
        col.addView(text(
            "לאחר ההפעלה ניפוי הבאגים ייחסם אוטומטית, כך שגם דרך המחשב לא ניתן יהיה להסיר את התוכנה. " +
            "ההסרה תתאפשר אך ורק באמצעות סיסמת ההסרה שהגדרת, ממסך הניהול."
        ))
    }
}
