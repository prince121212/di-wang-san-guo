package com.example.dwpmclone.domain.state

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.locks.ReentrantLock

/** One process-wide mutation lane per account, shared by scheduler and manual UI actions. */
object AccountOperationLockRegistry {
    private val locks = ConcurrentHashMap<Long, ReentrantLock>()

    fun acquire(accountId: Long) {
        require(accountId > 0L) { "accountId must be positive" }
        lockFor(accountId).lock()
    }

    fun tryAcquire(accountId: Long): Boolean {
        require(accountId > 0L) { "accountId must be positive" }
        return lockFor(accountId).tryLock()
    }

    fun release(accountId: Long) {
        val lock = locks[accountId] ?: return
        check(lock.isHeldByCurrentThread) { "account operation lock released by non-owner" }
        lock.unlock()
    }

    private fun lockFor(accountId: Long): ReentrantLock =
        locks.getOrPut(accountId) { ReentrantLock(true) }
}
