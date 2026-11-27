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

data class ApiHealth(val status: String, val tradingMode: String, val accounts: Int)
data class AccountInfo(val accountId: String, val broker: String, val mode: String, val enabled: Boolean)
data class AccountState(
    val accountId: String,
    val broker: String,
    val balances: Map<String, Double>,
    val positions: Map<String, Double>,
    val confirmed: Boolean
)
data class OrderResult(val status: String, val symbol: String, val side: String, val quantity: Double, val price: Double?)

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
        val ivEncoded = prefs.getString("iv", null) ?: return@runCatching null
        val tokenEncoded = prefs.getString("token", null) ?: return@runCatching null
        val iv = Base64.decode(ivEncoded, Base64.NO_WRAP)
        val data = Base64.decode(tokenEncoded, Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        String(cipher.doFinal(data), Charsets.UTF_8)
    }.getOrNull()

    fun clear() = prefs.edit().clear().apply()
}

class GoldenMindApi(
    private val context: Context,
    private val baseUrl: String = defaultBaseUrl()
) {
    companion object {
        private fun defaultBaseUrl(): String {
            val fp = android.os.Build.FINGERPRINT.lowercase()
            val model = android.os.Build.MODEL.lowercase()
            val emulator = fp.contains("generic") || fp.contains("emulator") || model.contains("sdk") || model.contains("emulator")
            return if (emulator) "http://10.0.2.2:8000" else BuildConfig.API_BASE_URL
        }
    }
    private val tokenStore = SecureTokenStore(context)
    private val prefs = context.getSharedPreferences("gmai_config", Context.MODE_PRIVATE)

    fun getBaseUrl(): String =
        prefs.getString("api_base_url", null)?.takeIf { it.isNotBlank() } ?: baseUrl

    fun setBaseUrl(url: String) {
        prefs.edit().putString("api_base_url", url.trim().trimEnd('/')).apply()
    }

    private fun request(
        path: String,
        method: String = "GET",
        body: String? = null,
        contentType: String = "application/json"
    ): String {
        val connection = (URL(getBaseUrl().trimEnd('/') + path).openConnection() as HttpURLConnection)
        connection.requestMethod = method
        connection.connectTimeout = 8000
        connection.readTimeout = 10000
        connection.setRequestProperty("Accept", "application/json")

        tokenStore.read()?.let {
            connection.setRequestProperty("Authorization", "Bearer $it")
        }

        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", contentType)
            connection.outputStream.use {
                it.write(body.toByteArray(Charsets.UTF_8))
            }
        }

        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
        connection.disconnect()

        if (code !in 200..299) {
            error("HTTP $code: $text")
        }
        return text
    }

    fun health(): ApiHealth {
        val json = JSONObject(request("/health"))
        return ApiHealth(
            json.optString("status"),
            json.optString("trading_mode"),
            json.optInt("accounts")
        )
    }

    fun login(username: String, password: String): Boolean {
        val body =
            "username=${URLEncoder.encode(username, "UTF-8")}" +
            "&password=${URLEncoder.encode(password, "UTF-8")}" +
            "&grant_type=password"

        val json = JSONObject(
            request(
                "/token",
                "POST",
                body,
                "application/x-www-form-urlencoded"
            )
        )

        val token = json.optString("access_token")
        if (token.isBlank()) error("Access token missing")

        tokenStore.save(token)
        return true
    }

    fun hasSession(): Boolean = tokenStore.read() != null
    fun logout() = tokenStore.clear()

    fun accounts(): List<AccountInfo> {
        val root = JSONObject(request("/accounts"))
        val arr = root.optJSONArray("accounts") ?: JSONArray()

        return buildList {
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                add(
                    AccountInfo(
                        item.optString("account_id"),
                        item.optString("broker"),
                        item.optString("mode"),
                        item.optBoolean("enabled")
                    )
                )
            }
        }
    }

    fun state(accountId: String): AccountState {
        val id = URLEncoder.encode(accountId, "UTF-8")
        val json = JSONObject(request("/accounts/$id/state"))

        fun map(name: String): Map<String, Double> {
            val obj = json.optJSONObject(name) ?: return emptyMap()
            return obj.keys().asSequence()
                .associateWith { obj.optDouble(it, 0.0) }
        }

        return AccountState(
            json.optString("account_id"),
            json.optString("broker"),
            map("balances"),
            map("positions"),
            json.optBoolean("confirmed")
        )
    }

    fun placeMarketOrder(
        accountId: String,
        clientOrderId: String,
        symbol: String,
        side: String,
        quantity: Double,
        price: Double? = null
    ): OrderResult {
        val body = JSONObject().apply {
            put("account_id", accountId)
            put("client_order_id", clientOrderId)
            put("symbol", symbol)
            put("side", side.uppercase())
            put("quantity", quantity)
            put("order_type", "MARKET")
            if (price != null) put("price", price)
        }

        val json = JSONObject(request("/orders/test", "POST", body.toString()))

        return OrderResult(
            json.optString("status"),
            json.optString("symbol"),
            json.optString("side"),
            json.optDouble("executedQty", quantity),
            if (json.has("price")) json.optDouble("price") else null
        )
    }

    fun emergencyStop() {
        request("/kill-switch/stop", "POST", "{}")
    }
}
