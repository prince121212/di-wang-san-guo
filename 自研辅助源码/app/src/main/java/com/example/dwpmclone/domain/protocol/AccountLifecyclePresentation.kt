package com.example.dwpmclone.domain.protocol

data class AccountLifecyclePresentation(
    val status: String,
    val statusText: String,
    val started: Boolean
)

/** Maps persisted user intent and the live Android execution owner to the shared UI contract. */
object AccountLifecyclePresentationPolicy {
    fun resolve(
        accountEnabled: Boolean,
        executionOwnerActive: Boolean,
        loginState: String,
        contract: AccountLifecycleBehaviorContract = AccountLifecycleBehaviorContract.defaults()
    ): AccountLifecyclePresentation {
        val state = loginState.uppercase()
        val ownerRequiredButMissing = accountEnabled &&
            contract.startedRequiresExecutionOwner &&
            !executionOwnerActive
        val started = accountEnabled &&
            (!contract.startedRequiresExecutionOwner || executionOwnerActive)
        val status = when {
            ownerRequiredButMissing -> "stopped"
            "CHECK" in state -> "checking"
            listOf("OFFLINE", "DISCONNECT", "NEED_RELOGIN", "NETWORK_PAUSED")
                .any(state::contains) -> "offline"
            !accountEnabled || "STOPPED" in state -> "stopped"
            else -> "online"
        }
        return AccountLifecyclePresentation(
            status = status,
            statusText = contract.statusText.getValue(status),
            started = started
        )
    }

    /** A persisted Session is an internal restart credential, not proof that the UI may act. */
    fun mayUseLiveSession(
        accountEnabled: Boolean,
        executionOwnerActive: Boolean,
        loginState: String,
        sourceMode: Int,
        contract: AccountLifecycleBehaviorContract = AccountLifecycleBehaviorContract.defaults()
    ): Boolean {
        val presentation = resolve(
            accountEnabled = accountEnabled,
            executionOwnerActive = executionOwnerActive,
            loginState = loginState,
            contract = contract
        )
        return sourceMode == 1 && presentation.started && presentation.status == "online"
    }
}
