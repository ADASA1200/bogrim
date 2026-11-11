package org.videoblock

/** Known video apps and video domains. Everything here is blocked regardless of what the scanner detects. */
object Blocklist {

    /** Video apps that are blocked and hidden from the launcher if installed. */
    val videoPackages = setOf(
        "com.google.android.youtube", "com.google.android.apps.youtube.kids",
        "com.google.android.apps.youtube.music", "com.google.android.youtube.tv",
        "app.revanced.android.youtube", "app.rvx.android.youtube", "com.vanced.android.youtube",
        "org.schabi.newpipe", "free.rm.skytube.oss", "com.github.libretube",
        "com.zhiliaoapp.musically", "com.ss.android.ugc.trill", "com.zhiliaoapp.musically.go",
        "com.ss.android.ugc.aweme", "com.lemon.lvoverseas", "com.kwai.video", "com.snaptube.premium",
        "com.netflix.mediaclient", "com.disney.disneyplus", "com.amazon.avod.thirdpartyclient",
        "com.hbo.hbonow", "com.wbd.stream", "com.hulu.plus", "com.apple.atve.androidtv.appletv",
        "tv.twitch.android.app", "com.kick.mobile", "com.rumble.battles", "com.vimeo.android.videoapp",
        "com.dailymotion.dailymotion", "tv.pluto.android", "com.plexapp.android", "org.xbmc.kodi",
        "org.videolan.vlc", "com.mxtech.videoplayer.ad", "com.mxtech.videoplayer.pro",
        "video.player.videoplayer", "com.kmplayer", "com.inshot.xplayer", "is.xyz.mpv",
        "com.instagram.android", "com.instagram.barcelona", "com.instagram.lite",
        "com.facebook.katana", "com.facebook.lite", "com.snapchat.android", "com.likee.video",
        "com.bilibili.app.in", "tv.danmaku.bili", "com.vk.vkvideo", "ru.ok.android",
        "com.keshet.mako.VOD", "il.co.reshet.reshetnews", "com.applicaster.il.channel13",
        "il.co.yes.yesgo", "com.hot.vod", "com.cellcom.cellcomtv", "com.partner.tv",
    )

    /** Domains (and all their sub-domains) refused by the DNS filter. */
    val videoDomains = setOf(
        // YouTube
        "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com", "youtube-nocookie.com",
        "youtubei.googleapis.com", "youtube.googleapis.com", "yt3.ggpht.com", "youtubekids.com",
        "invidious.io", "piped.video", "pipedapi.kavin.rocks",
        // TikTok / ByteDance
        "tiktok.com", "tiktokv.com", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokv.us",
        "byteoversea.com", "ibytedtos.com", "ibyteimg.com", "musical.ly", "muscdn.com", "capcut.com",
        // Video platforms
        "vimeo.com", "vimeocdn.com", "player.vimeo.com", "dailymotion.com", "dmcdn.net", "dm-event.net",
        "twitch.tv", "ttvnw.net", "jtvnw.net", "kick.com", "rumble.com", "bitchute.com", "odysee.com",
        "streamable.com", "bilibili.com", "bilivideo.com", "bilibili.tv", "iqiyi.com", "youku.com",
        "metacafe.com", "veoh.com", "likee.video", "triller.co", "vkvideo.ru", "rutube.ru",
        "brightcove.com", "brightcove.net", "boltdns.net", "jwplayer.com", "jwpcdn.com", "jwplatform.com",
        "kaltura.com", "wistia.com", "wistia.net", "vidyard.com", "mux.com", "litix.io",
        // Streaming services
        "netflix.com", "nflxvideo.net", "nflximg.net", "nflxso.net", "nflxext.com",
        "disneyplus.com", "disney-plus.net", "dssott.com", "bamgrid.com", "primevideo.com",
        "aiv-cdn.net", "aiv-delivery.net", "hulu.com", "hulustream.com", "hbomax.com", "max.com",
        "tv.apple.com", "pluto.tv", "plex.tv", "crunchyroll.com", "paramountplus.com", "peacocktv.com",
        // Israeli VOD / TV
        "mako.co.il", "13tv.co.il", "reshet.tv", "cellcom.tv", "nextvod.co.il", "sting.tv",
        "freetv.tv", "yesplus.co.il", "hotvod.co.il",
        // DNS-over-HTTPS resolvers that would let a browser bypass the filter
        "dns.google", "dns.google.com", "cloudflare-dns.com", "one.one.one.one", "dns.quad9.net",
        "doh.opendns.com", "dns.adguard.com", "dns.adguard-dns.com", "dns.nextdns.io",
        "doh.cleanbrowsing.org", "doh.mullvad.net", "dns.controld.com", "doh.dns.sb",
        "use-application-dns.net",
        // Generic video CDNs / streaming infrastructure used by many apps and sites.
        "akamaihd.net", "akamaized.net", "llnwd.net", "lldns.net", "level3.net",
        "fastly.net", "fastlylb.net", "edgecastcdn.net", "cdn77.org", "b-cdn.net",
        "cloudfront.net", "video.google.com", "vod.akamai.com", "hls.ttvnw.net",
    )

    fun isBlockedDomain(name: String, extra: Set<String>): Boolean {
        var d = name.lowercase().trimEnd('.')
        while (true) {
            if (d in videoDomains || d in extra) return true
            val dot = d.indexOf('.')
            if (dot < 0) return false
            d = d.substring(dot + 1)
        }
    }
}
