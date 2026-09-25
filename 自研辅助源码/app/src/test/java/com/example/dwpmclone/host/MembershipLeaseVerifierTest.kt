package com.example.dwpmclone.host

import java.security.KeyPairGenerator
import java.security.Signature
import java.util.Base64
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class MembershipLeaseVerifierTest {
    private val keys = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
    private val now = 1_800_000_000_000L
    private fun claims() = JSONObject().put("kind","dwpm-member-lease-v1").put("issuer","dwpm").put("audience","android")
        .put("memberId","member-1").put("sessionId","session-1").put("deviceId","device-1").put("requestId","nonce-1")
        .put("issuedAt",now).put("expiresAt",now+7_200_000L).put("memberExpiresAt",now+86_400_000L).put("maxGameAccounts",2)
    private fun verify(value: JSONObject = claims(), request: String = "nonce-1", device: String = "device-1", signatureMutation: Boolean = false): Long {
        val bytes = value.toString().toByteArray(Charsets.UTF_8)
        val encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
        val signer = Signature.getInstance("SHA256withRSA").apply {
            initSign(keys.private); update(encoded.toByteArray(Charsets.UTF_8))
        }
        val sig = signer.sign().also { if (signatureMutation) it[0] = (it[0].toInt() xor 1).toByte() }
        return MembershipLeaseVerifier.verify(keys.public.encoded,encoded,bytes,sig,
            "member-1","session-1",device,request,now,500)
    }
    @Test fun acceptsOnlyBoundTwoHourLeaseAndSubtractsTransitTime() { assertEquals(7_199_500L,verify()) }
    @Test fun copiedLeaseFailsOnAnotherDevice() { assertThrows(IllegalArgumentException::class.java) { verify(device="other-device") } }
    @Test fun replayedOldResponseFailsOnNewRequest() { assertThrows(IllegalArgumentException::class.java) { verify(request="new-nonce") } }
    @Test fun mutatedSignatureDoesNotAuthorize() { assertThrows(IllegalArgumentException::class.java) { verify(signatureMutation=true) } }
    @Test fun leaseCannotExceedTwoHoursEvenWhenSigned() { assertThrows(IllegalArgumentException::class.java) { verify(claims().put("expiresAt",now+7_200_001L)) } }
    @Test fun leaseCannotOutliveMembership() { assertThrows(IllegalArgumentException::class.java) { verify(claims().put("memberExpiresAt",now+1000L)) } }
    @Test fun audienceAndScopeCannotChange() { assertThrows(IllegalArgumentException::class.java) { verify(claims().put("audience","admin")) } }
    @Test fun membershipDoesNotGrantExtraGameSlots() { assertThrows(IllegalArgumentException::class.java) { verify(claims().put("maxGameAccounts",3)) } }
}
