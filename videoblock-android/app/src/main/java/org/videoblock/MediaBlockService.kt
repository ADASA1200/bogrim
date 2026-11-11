package org.videoblock

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Toast

/**
 * Second enforcement layer. The DNS/VPN filter stops video traffic; this watches the screen and
 * closes a video player if one still manages to appear inside an app the administrator left open
 * (a messenger, a browser). It only reads the view hierarchy — it never records or sends anything.
 */
class MediaBlockService : AccessibilityService() {

    private var lastBlock = 0L

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return
        val type = event.eventType
        if (type != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
            type != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return

        val pkg = event.packageName?.toString() ?: return
        if (pkg == packageName || pkg == "com.android.systemui") return

        val root = rootInActiveWindow ?: return
        val classes = ArrayList<CharSequence?>()
        val texts = ArrayList<CharSequence?>()
        collect(root, classes, texts, 0)

        if (VideoUi.hasPlayerClass(classes) || VideoUi.hasPlayerText(texts)) block()
    }

    private fun block() {
        val now = System.currentTimeMillis()
        if (now - lastBlock < 1500) return   // debounce repeated events from one player
        lastBlock = now
        performGlobalAction(GLOBAL_ACTION_BACK)
        Toast.makeText(this, "צפייה בווידאו חסומה", Toast.LENGTH_SHORT).show()
    }

    /** Depth-limited walk of the node tree, gathering class names and visible text. */
    private fun collect(
        node: AccessibilityNodeInfo?, classes: MutableList<CharSequence?>,
        texts: MutableList<CharSequence?>, depth: Int,
    ) {
        node ?: return
        if (depth > 40 || classes.size > 400) return
        classes.add(node.className)
        node.text?.let { texts.add(it) }
        node.contentDescription?.let { texts.add(it) }
        for (i in 0 until node.childCount) collect(node.getChild(i), classes, texts, depth + 1)
    }

    override fun onInterrupt() {}
}
