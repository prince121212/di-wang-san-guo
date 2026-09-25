package com.example.dwpmclone.host

import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import org.json.JSONObject

/** Fixed algorithm and pinned server key. No client-controlled key/alg selection. */
internal object MembershipLeaseVerifier {
    const val MAX_LEASE_MILLIS = 2L * 60L * 60L * 1000L

    fun verify(
        publicKeyDer: ByteArray, encodedPayload: String, payloadBytes: ByteArray, signatureBytes: ByteArray,
        memberId: String, sessionId: String, deviceId: String, requestId: String,
        serverTimeMillis: Long, requestDurationMillis: Long
    ): Long {
        val key = KeyFactory.getInstance("RSA").generatePublic(X509EncodedKeySpec(publicKeyDer))
        val verifier = Signature.getInstance("SHA256withRSA")
        verifier.initVerify(key)
        verifier.update(encodedPayload.toByteArray(Charsets.UTF_8))
        require(verifier.verify(signatureBytes)) { "会员授权签名无效" }
        val claims = JSONObject(String(payloadBytes, Charsets.UTF_8))
        require(claims.optString("kind") == "dwpm-member-lease-v1" &&
            claims.optString("issuer") == "dwpm" && claims.optString("audience") == "android") { "会员授权类型无效" }
        require(claims.optString("memberId") == memberId && claims.optString("sessionId") == sessionId &&
            claims.optString("deviceId") == deviceId && claims.optString("requestId") == requestId) { "会员授权不属于本次设备请求" }
        val issued = claims.getLong("issuedAt")
        val expires = claims.getLong("expiresAt")
        val memberExpires = claims.getLong("memberExpiresAt")
        require(expires > issued && expires - issued <= MAX_LEASE_MILLIS && expires <= memberExpires &&
            serverTimeMillis >= issued - 60_000L && serverTimeMillis <= issued + 60_000L &&
            claims.getInt("maxGameAccounts") in 1..2) { "会员授权期限或范围无效" }
        val remaining = minOf(expires - issued, expires - serverTimeMillis) - requestDurationMillis.coerceAtLeast(0)
        require(remaining > 0) { "会员授权已过期" }
        return remaining
    }
}
