import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val generatedAssistantAssets = layout.buildDirectory.dir("generated/assistantWebAssets")
val sharedCoreRoot = rootProject.layout.projectDirectory.dir("../shared_core")
val sharedPythonSource = sharedCoreRoot.dir("python")
val generatedSharedPythonBundle = layout.buildDirectory.dir("generated/sharedPythonBundle")
val sharedCoreContractNames = listOf(
    "api_route_ownership.json",
    "assistant_behavior_contract.json",
    "feature_parity_matrix.json",
    "protocol_parity_fixtures.json"
)
val sharedPythonFiles = fileTree(sharedCoreRoot.dir("python/dwpm_core")) {
    include("**/*.py")
    exclude("**/__pycache__/**")
}

val generateSharedPythonBundle by tasks.registering {
    inputs.files(sharedPythonFiles)
    inputs.file(sharedCoreRoot.file("python/pyproject.toml"))
    inputs.files(sharedCoreContractNames.map(sharedCoreRoot::file))
    outputs.dir(generatedSharedPythonBundle)

    doLast {
        val root = sharedCoreRoot.asFile.canonicalFile
        val outputRoot = generatedSharedPythonBundle.get().asFile
        val bundlePackage = outputRoot.resolve("dwpm_core/_embedded_bundle")
        project.delete(outputRoot)
        check(bundlePackage.mkdirs()) { "Cannot create generated shared-core bundle" }

        val records = mutableListOf<Pair<String, File>>()
        sharedPythonFiles.files.forEach { source ->
            records += root.toPath().relativize(source.canonicalFile.toPath())
                .toString().replace(File.separatorChar, '/') to source
        }
        records += "python/pyproject.toml" to root.resolve("python/pyproject.toml")
        sharedCoreContractNames.forEach { name ->
            val contract = root.resolve(name)
            check(contract.isFile) { "Shared-core contract is missing: $contract" }
            records += name to contract
            contract.copyTo(bundlePackage.resolve(name), overwrite = true)
        }
        val sortedRecords = records.sortedBy { it.first }
        val digest = MessageDigest.getInstance("SHA-256")
        sortedRecords.forEach { (name, source) ->
            digest.update(name.toByteArray(Charsets.UTF_8))
            digest.update(byteArrayOf(0))
            digest.update(source.readBytes())
            digest.update(byteArrayOf(0))
        }
        val coreHash = digest.digest().joinToString("") { byte: Byte ->
            "%02x".format(byte.toInt() and 0xff)
        }
        val filesJson = sortedRecords.joinToString(",") { (name, _) -> "\"$name\"" }
        bundlePackage.resolve("__init__.py").writeText(
            "\"\"\"Build-generated resources; never edit this directory.\"\"\"\n",
            Charsets.UTF_8
        )
        bundlePackage.resolve("source_manifest.json").writeText(
            "{\"coreHash\":\"$coreHash\",\"files\":[$filesJson],\"schemaVersion\":1}",
            Charsets.UTF_8
        )
    }
}

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
        minSdk = 24
        targetSdk = 36
        versionCode = 16
        versionName = "V0.0.16"
        ndk {
            abiFilters += listOf("armeabi-v7a", "arm64-v8a")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets.getByName("main").assets.srcDir(generatedAssistantAssets)
}

tasks.named("preBuild").configure {
    dependsOn(syncAssistantWebAssets, generateSharedPythonBundle)
}

tasks.configureEach {
    if (name != generateSharedPythonBundle.name && name.contains("Python")) {
        dependsOn(generateSharedPythonBundle)
    }
}

kotlin {
    jvmToolchain(17)
}

chaquopy {
    defaultConfig {
        version = "3.10"
    }
    sourceSets {
        getByName("main") {
            srcDir(sharedPythonSource.asFile)
            srcDir(generatedSharedPythonBundle.get().asFile)
        }
    }
}


dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
