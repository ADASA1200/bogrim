package com.rdesk.viewer

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * מזריקה את הקלט מהצד המתחבר (מצב מארח) לתוך המכשיר הזה - בלי root, דרך
 * AccessibilityService, בדיוק כמו שעובדות אפליקציות תמיכה-מרחוק לגיטימיות
 * אחרות באנדרואיד (למשל TeamViewer QuickSupport). המשתמש חייב להפעיל את
 * השירות הזה ידנית בהגדרות המכשיר - אי אפשר להעניק הרשאת נגישות פרוגרמטית,
 * מטעמי אבטחה של המערכת עצמה.
 *
 * מגבלות אמיתיות, לא "תכל'ס זה עובד מושלם":
 * - מגע: dispatchGesture() דורש Path+משך-זמן *שלם* מראש - אי אפשר "לדווח
 *   חי" על כל ניקוד mm שמגיע בנפרד. נאגרים כל נקודות ה-mm בין md ל-mu, ורק
 *   כש-mu מגיע נשלחת מחווה אחת מלאה. המשמעות: גרירה/ציור מגיעים ליעד הנכון,
 *   אבל בלי משוב ויזואלי חי על המסך תוך כדי הגרירה עצמה (רק כשהיא מסתיימת).
 * - מקלדת: AccessibilityNodeInfo.ACTION_SET_TEXT מחליף את כל הטקסט בשדה
 *   הממוקד ומזיז את הסמן בעצמנו - עובד טוב בשדות עריכה רגילים (EditText),
 *   אבל *לא* בשדות טקסט מצוירים-בעצמם (קנבס, חלק ממשחקים/עורכים מיוחדים)
 *   שלא חושפים AccessibilityNodeInfo עם isEditable=true. Enter/טאב נתמכים
 *   חלקית בלבד (תלוי גרסת אנדרואיד ואפליקציית היעד).
 */
class RDeskAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile var instance: RDeskAccessibilityService? = null
            private set

        fun isEnabled(context: Context): Boolean {
            val enabled = Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: ""
            val id = "${context.packageName}/${RDeskAccessibilityService::class.java.name}"
            return enabled.split(':').any { it.equals(id, ignoreCase = true) }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}

    // ------------------------------------------------------------ מגע (עכבר/אצבע מדומים)
    private data class Point(val x: Float, val y: Float, val tMs: Long)

    private var dragging = false
    private var strokeStartTime = 0L
    private val buffered = mutableListOf<Point>()
    private var lastX = 0f
    private var lastY = 0f

    fun onMouseDown(x: Float, y: Float) {
        lastX = x; lastY = y
        dragging = true
        strokeStartTime = SystemClock.uptimeMillis()
        buffered.clear()
        buffered.add(Point(x, y, 0))
    }

    fun onMouseMove(x: Float, y: Float) {
        lastX = x; lastY = y
        if (!dragging) return   // אין "ריחוף" במסך מגע בלי כפתור לחוץ
        buffered.add(Point(x, y, SystemClock.uptimeMillis() - strokeStartTime))
    }

    fun onMouseUp(x: Float, y: Float) {
        lastX = x; lastY = y
        if (!dragging) return
        buffered.add(Point(x, y, SystemClock.uptimeMillis() - strokeStartTime))
        dispatchBufferedStroke()
        dragging = false
        buffered.clear()
    }

    /** גלגלת עכבר מהצד המתחבר - אין "מיקום עכבר" קבוע במסך מגע, אז מגלגלים
     * במקום הנגיעה האחרון הידוע (או מרכז המסך אם עדיין לא היה קלט). */
    fun onScroll(dy: Int) {
        if (dragging) return
        val x = if (lastX > 0f) lastX else 500f
        val y = if (lastY > 0f) lastY else 800f
        val delta = (-dy * 14f).coerceIn(-600f, 600f)
        val path = Path()
        path.moveTo(x, y)
        path.lineTo(x, (y + delta).coerceAtLeast(0f))
        val stroke = GestureDescription.StrokeDescription(path, 0, 120)
        runCatching { dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null) }
    }

    /** קריאה בסיום/נפילת סשן - לא משאירים "גרירה תקועה" אם mu לא הגיע. */
    fun releaseAll() {
        dragging = false
        buffered.clear()
    }

    private fun dispatchBufferedStroke() {
        if (buffered.isEmpty()) return
        if (buffered.size == 1) buffered.add(buffered[0].copy(tMs = 60))   // קליק פשוט - נגיעה קצרה
        val path = Path()
        path.moveTo(buffered[0].x, buffered[0].y)
        for (i in 1 until buffered.size) path.lineTo(buffered[i].x, buffered[i].y)
        val duration = buffered.last().tMs.coerceIn(30L, 15_000L)
        val stroke = GestureDescription.StrokeDescription(path, 0, duration)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        runCatching { dispatchGesture(gesture, null, null) }
    }

    // ------------------------------------------------------------ מקלדת (עריכת השדה הממוקד)
    fun onKeyDown(name: String) {
        val node = runCatching { findFocus(AccessibilityNodeInfo.FOCUS_INPUT) }.getOrNull() ?: return
        try {
            if (!node.isEditable) return
            when (name) {
                "backspace" -> editText(node) { text, sel -> if (sel > 0) (text.removeRange(sel - 1, sel) to sel - 1) else (text to sel) }
                "delete" -> editText(node) { text, sel -> if (sel < text.length) (text.removeRange(sel, sel + 1) to sel) else (text to sel) }
                "enter" -> runCatching { node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id) }
                "space" -> insertText(node, " ")
                "left" -> moveSelection(node, -1)
                "right" -> moveSelection(node, 1)
                "tab", "esc", "home", "end", "up", "down" -> {} // אין מקבילה כללית אמינה דרך נגישות
                else -> if (name.length == 1) insertText(node, name)
            }
        } finally {
            @Suppress("DEPRECATION")
            runCatching { node.recycle() }
        }
    }

    private fun insertText(node: AccessibilityNodeInfo, s: String) {
        editText(node) { text, sel -> (text.substring(0, sel) + s + text.substring(sel)) to (sel + s.length) }
    }

    private fun editText(node: AccessibilityNodeInfo, transform: (String, Int) -> Pair<String, Int>) {
        val current = node.text?.toString() ?: ""
        val sel = (if (node.textSelectionEnd >= 0) node.textSelectionEnd else current.length).coerceIn(0, current.length)
        val (newText, newSel) = transform(current, sel)
        val setTextArgs = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, newText)
        }
        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, setTextArgs)
        moveSelectionTo(node, newSel.coerceIn(0, newText.length))
    }

    private fun moveSelection(node: AccessibilityNodeInfo, delta: Int) {
        val current = node.text?.toString() ?: return
        val sel = ((if (node.textSelectionEnd >= 0) node.textSelectionEnd else current.length) + delta).coerceIn(0, current.length)
        moveSelectionTo(node, sel)
    }

    private fun moveSelectionTo(node: AccessibilityNodeInfo, pos: Int) {
        val args = Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, pos)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, pos)
        }
        runCatching { node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, args) }
    }
}
