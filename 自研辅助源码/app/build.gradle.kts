plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.example.dwpmclone"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.dwpmclone"
        minSdk = 23
        targetSdk = 36
        versionCode = 1
        versionName = "1.0-v2-real-login"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    jvmToolchain(17)
}


dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
