package com.example.dwpmclone.domain.scheduler

import java.util.concurrent.CountDownLatch
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.startCoroutine

/** Minimal blocking bridge for local suspend tasks without adding kotlinx-coroutines. */
object SuspendRunner {
    fun <T> run(block: suspend () -> T): T {
        val latch = CountDownLatch(1)
        var value: T? = null
        var error: Throwable? = null
        block.startCoroutine(object : Continuation<T> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(result: Result<T>) {
                result.onSuccess { value = it }
                result.onFailure { error = it }
                latch.countDown()
            }
        })
        latch.await()
        error?.let { throw it }
        @Suppress("UNCHECKED_CAST")
        return value as T
    }
}
