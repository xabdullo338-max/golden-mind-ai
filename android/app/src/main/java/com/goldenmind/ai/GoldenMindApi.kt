package com.goldenmind.ai

import android.content.Context
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.security.KeyStore

data class ApiHealth(
    val status: String,
    val tradingMode: String,
    val accounts: Int
)

data class AccountInfo(
    val accountId: String,
    val broker: String,
    val mode: String,
    val enabled: Boolean
)

class SecureTokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("gmai_secure", Context.MODE_PRIVATE)
    private val alias = "GoldenMindAI.TokenKey"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance("AES", "AndroidKeyStore")
        gen.init(256)
        return gen.generateKey()
    }

    fun save(token: String) {
        val iv = ByteArray(12).also { java.security.SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key(), GCMParameterSpec(128, iv))
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString("iv", Base64.encodeToString(iv, Base64.NO_WRAP))
            .putString("token", Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .apply()
    }

    fun read(): String? = runCatching {
        val iv = Base64.decode(prefs.getString("iv", null), Base64.NO_WRAP)
        val data = Base64.decode(prefs.getString("token", null), Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        String(cipher.doFinal(data), Charsets.UTF_8)
    }.getOrNull()

    fun clear() = prefs.edit().clear().apply()
}

class GoldenMindApi(
    private val context: Context,
    private val baseUrl: String = "http://10.0.2.2:8000"
) {
    private val tokenStore = SecureTokenStore(context)

    private fun request(path: String, method: String = "GET", body: String? = null, contentType: String = "application/json"): String {
        val connection = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection)
        connection.requestMethod = method
        connection.connectTimeout = 8000
        connection.readTimeout = 10000
        connection.setRequestProperty("Accept", "application/json")
        tokenStore.read()?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", contentType)
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
        if (code !in 200..299) error("HTTP $code: $text")
        return text
    }

    fun health(): ApiHealth {
        val json = JSONObject(request("/health"))
        return ApiHealth(
            status = json.optString("status"),
            tradingMode = json.optString("trading_mode"),
            accounts = json.optInt("accounts")
        )
    }

    fun login(username: String, password: String): Boolean {
        val body = "username=${URLEncoder.encode(username, "UTF-8")}" +
            "&password=${URLEncoder.encode(password, "UTF-8")}" +
            "&grant_type=password"
        val json = JSONObject(request("/token", "POST", body, "application/x-www-form-urlencoded"))
        val token = json.optString("access_token")
        if (token.isBlank()) error("Access token missing")
        tokenStore.save(token)
        return true
    }

    fun logout() = tokenStore.clear()

    fun accounts(): List<AccountInfo> {
        val arr = JSONArray(request("/accounts"))
        return buildList {
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                add(AccountInfo(
                    accountId = item.optString("account_id"),
                    broker = item.optString("broker"),
                    mode = item.optString("mode"),
                    enabled = item.optBoolean("enabled")
                ))
            }
        }
    }
}
