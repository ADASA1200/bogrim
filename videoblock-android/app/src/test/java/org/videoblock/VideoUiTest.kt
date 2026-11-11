package org.videoblock

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VideoUiTest {
    @Test fun detectsPlayerClasses() {
        assertTrue(VideoUi.hasPlayerClass(listOf("android.widget.FrameLayout",
            "com.google.android.exoplayer2.ui.StyledPlayerView")))
        assertTrue(VideoUi.hasPlayerClass(listOf("android.widget.VideoView")))
        assertTrue(VideoUi.hasPlayerClass(listOf("android.view.SurfaceView")))
    }

    @Test fun ignoresOrdinaryScreens() {
        assertFalse(VideoUi.hasPlayerClass(listOf(
            "android.widget.TextView", "android.widget.Button", "androidx.recyclerview.widget.RecyclerView")))
    }

    @Test fun detectsPlayerTextOnlyWithTimecode() {
        assertTrue(VideoUi.hasPlayerText(listOf("1080p", "03:24", "HD")))
        // A resolution-like word without a timecode must not trigger (e.g. a settings screen).
        assertFalse(VideoUi.hasPlayerText(listOf("1080p display", "brightness")))
        assertFalse(VideoUi.hasPlayerText(listOf("hello", "12:00 lunch")))
    }
}
