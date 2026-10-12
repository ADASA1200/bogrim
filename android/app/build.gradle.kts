plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// כתובת שרת האיתות ברירת המחדל באפליקציה:  ./gradlew assembleDebug -PrdeskServer=wss://signal.example.com
val defaultServer: String = (findProperty("rdeskServer") as String?) ?: "ws://10.0.2.2:8765"

android {
    namespace = "com.rdesk.viewer"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.rdesk.viewer"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "DEFAULT_SERVER", "\"$defaultServer\"")
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
    }

    buildFeatures { buildConfig = true }

    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

dependencies {
    implementation("io.getstream:stream-webrtc-android:1.3.10")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
