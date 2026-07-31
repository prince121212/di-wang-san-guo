plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val generatedAssistantAssets = layout.buildDirectory.dir("generated/assistantWebAssets")
val syncAssistantWebAssets by tasks.registering(Sync::class) {
    from(rootProject.file("../电脑端辅助前端")) {
        include("index.html", "app.js", "styles.css", "assistant-api.js")
        into("assistant")
    }
    from(rootProject.file("../shared_core")) {
        include("assistant_behavior_contract.json", "feature_parity_matrix.json")
        into("shared_core")
    }
    into(generatedAssistantAssets)
}

android {
    namespace = "com.example.dwpmclone"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.dwpmclone"
        minSdk = 23
        targetSdk = 36
        versionCode = 15
        versionName = "V0.0.15"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets.getByName("main").assets.srcDir(generatedAssistantAssets)
}

tasks.named("preBuild").configure {
    dependsOn(syncAssistantWebAssets)
}

kotlin {
    jvmToolchain(17)
}


dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
