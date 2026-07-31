package com.example.dwpmclone.domain.state

import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccountOperationLockRegistryTest {
    @Test
    fun sameAccountIsMutuallyExclusiveWhileDifferentAccountsRemainIndependent() {
        val held = CountDownLatch(1)
        val release = CountDownLatch(1)
        val worker = Thread {
            AccountOperationLockRegistry.acquire(1608603L)
            try {
                held.countDown()
                release.await(2, TimeUnit.SECONDS)
            } finally {
                AccountOperationLockRegistry.release(1608603L)
            }
        }
        worker.start()
        assertTrue(held.await(2, TimeUnit.SECONDS))

        assertFalse(AccountOperationLockRegistry.tryAcquire(1608603L))
        assertTrue(AccountOperationLockRegistry.tryAcquire(1608602L))
        AccountOperationLockRegistry.release(1608602L)

        release.countDown()
        worker.join(2_000L)
        assertFalse(worker.isAlive)
    }
}
