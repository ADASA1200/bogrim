package org.videoblock

/**
 * Heuristics for recognising an active video player on screen, used by the accessibility layer.
 * Kept as pure functions so they can be unit-tested without a device.
 */
object VideoUi {

    /** View / widget class names that indicate a video surface is being shown. */
    private val playerClasses = listOf(
        "exoplayer", "videoview", "surfaceview", "textureview",
        "playerview", "styledplayerview", "video_player", "videoplayer",
        "media3.ui", "libvlc", "ijkplayer", "jwplayer", "brightcove",
        "youtube.player", "html5video",
    )

    /** Text that commonly labels a video player control (resolution/quality, fullscreen, etc.). */
    private val playerHints = listOf(
        "1080p", "720p", "480p", "360p", "240p", "144p", "פתח במסך מלא",
        "מסך מלא", "fullscreen", "הפעל וידאו", "watch video", "live stream", "שידור חי",
    )

    /** True if any of the on-screen view class names looks like a video player. */
    fun hasPlayerClass(classNames: Collection<CharSequence?>): Boolean {
        for (c in classNames) {
            val s = c?.toString()?.lowercase() ?: continue
            if (playerClasses.any { s.contains(it) }) return true
        }
        return false
    }

    /** True if visible on-screen text strongly suggests a video player. */
    fun hasPlayerText(texts: Collection<CharSequence?>): Boolean {
        val joined = texts.mapNotNull { it?.toString()?.lowercase() }
        // Require a resolution label AND a time-like token to avoid false positives on plain text.
        val hasHint = joined.any { t -> playerHints.any { t.contains(it) } }
        val hasTime = joined.any { Regex("\\b\\d{1,2}:\\d{2}\\b").containsMatchIn(it) }
        return hasHint && hasTime
    }
}
