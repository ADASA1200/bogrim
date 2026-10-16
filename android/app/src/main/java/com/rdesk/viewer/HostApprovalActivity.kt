package com.rdesk.viewer

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * מסך אישור חיבור נכנס במצב מארח - מוקפץ מעל כל מה שרץ (גם מסך נעול),
 * בדיוק כמו בקשת אישור חיבור ב-AnyDesk/שולחן-העבודה של RDesk. מוצגים
 * ה-IP, שם המשתמש ושם המחשב שדיווח הצד המתחבר (לא מאומתים - אינדיקציה
 * בלבד ל"זה נראה מוכר?", בדיוק כמו בצד שולחן-העבודה).
 */
class HostApprovalActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
        )
        val info = HostApprovalBus.info
        if (info == null) {
            finish()
            return
        }

        fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(resources.getColor(R.color.bg, theme))
            setPadding(dp(24), dp(48), dp(24), dp(24))
            gravity = Gravity.CENTER_HORIZONTAL
        }
        root.addView(TextView(this).apply {
            setText(R.string.host_approval_title)
            textSize = 22f
            setTextColor(resources.getColor(R.color.fg, theme))
        })
        val details = buildString {
            append(getString(R.string.host_approval_message, info.peer))
            info.computer?.let { append('\n'); append(it) }
            info.username?.let { append(" (").append(it).append(')') }
            info.ip?.let { append('\n'); append(it) }
        }
        root.addView(TextView(this).apply {
            text = details
            textSize = 15f
            setPadding(0, dp(16), 0, dp(28))
            setTextColor(resources.getColor(R.color.fg_faint, theme))
        })
        root.addView(Button(this).apply {
            setText(R.string.host_approval_approve)
            isAllCaps = false
            setBackgroundResource(R.drawable.bg_btn_primary)
            setTextColor(Color.WHITE)
            setOnClickListener { HostApprovalBus.resolve(true); finish() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52)))
        root.addView(Button(this).apply {
            setText(R.string.host_approval_decline)
            isAllCaps = false
            setBackgroundResource(R.drawable.bg_btn_ghost)
            setTextColor(resources.getColor(R.color.fg, theme))
            setOnClickListener { HostApprovalBus.resolve(false); finish() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52)).apply { topMargin = dp(10) })
        setContentView(root)
    }

    override fun onDestroy() {
        // המסך נסגר בלי בחירה (למשל כיבוי מסך/מעבר אפליקציה) - נחשב דחייה,
        // כדי לא להשאיר את המארח תקוע מחכה לאישור שלא יגיע (fail-closed).
        HostApprovalBus.resolve(false)
        super.onDestroy()
    }
}
