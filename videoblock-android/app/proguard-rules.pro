# Device admin receiver is referenced from the manifest/DevicePolicyManager by name.
-keep class org.videoblock.AdminReceiver { *; }

# libadb-android + its crypto (used reflectively / via providers).
-keep class io.github.muntashirakon.adb.** { *; }
-dontwarn io.github.muntashirakon.adb.**

# BouncyCastle security provider (registered at runtime via Security.addProvider).
-keep class org.bouncycastle.** { *; }
-dontwarn org.bouncycastle.**
-keep class org.bouncycastle.jcajce.provider.** { *; }
-keep class org.bouncycastle.jce.provider.** { *; }

# SPAKE2 pairing implementation.
-keep class com.github.muntashirakon.** { *; }
-dontwarn javax.annotation.**
