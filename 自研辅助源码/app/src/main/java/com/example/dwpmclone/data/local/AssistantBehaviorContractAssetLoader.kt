package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract

/** Loads the packaged cross-platform behavior contract and never invents runtime defaults. */
object AssistantBehaviorContractAssetLoader {
    private const val ASSET_PATH = "shared_core/assistant_behavior_contract.json"

    fun load(context: Context): AssistantBehaviorContract = runCatching {
        context.applicationContext.assets.open(ASSET_PATH)
            .bufferedReader(Charsets.UTF_8)
            .use { AssistantBehaviorContract.fromJson(it.readText()) }
    }.getOrElse { cause ->
        throw IllegalStateException(
            "共享行为契约 $ASSET_PATH 缺失或无效；为防止电脑端与手机端逻辑分叉，已拒绝启动执行核心",
            cause
        )
    }
}
