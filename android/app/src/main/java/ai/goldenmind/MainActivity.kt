package ai.goldenmind

import android.os.Bundle
import android.view.Gravity
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private var token: String? = null
    private lateinit var baseUrl: EditText
    private lateinit var status: TextView
    private lateinit var content: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showLogin()
    }

    private fun showLogin() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 32, 28, 28)
            setBackgroundColor(android.graphics.Color.rgb(11, 16, 32))
        }
        val title = TextView(this).apply {
            text = "GOLDEN MIND AI"
            textSize = 30f
            setTextColor(android.graphics.Color.WHITE)
            gravity = Gravity.CENTER
        }
        val subtitle = TextView(this).apply {
            text = "Safety-first trading control • TESTNET / PAPER"
            textSize = 14f
            setTextColor(android.graphics.Color.LTGRAY)
            gravity = Gravity.CENTER
        }
        baseUrl = EditText(this).apply {
            hint = "API URL (e.g. http://10.0.2.2:8000)"
            setSingleLine()
            setText("http://10.0.2.2:8000")
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }
        val user = EditText(this).apply {
            hint = "Username"
            setSingleLine()
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }
        val pass = EditText(this).apply {
            hint = "Password"
            inputType = 0x81
            setSingleLine()
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }
        val login = Button(this).apply { text = "SIGN IN" }
        status = TextView(this).apply {
            setTextColor(android.graphics.Color.LTGRAY)
            gravity = Gravity.CENTER
        }
        login.setOnClickListener {
            status.text = "Connecting..."
            requestToken(baseUrl.text.toString(), user.text.toString(), pass.text.toString())
        }
        root.addView(title, lp())
        root.addView(subtitle, lp())
        root.addView(space())
        root.addView(baseUrl, lp())
        root.addView(user, lp())
        root.addView(pass, lp())
        root.addView(login, lp())
        root.addView(status, lp())
        setContentView(root)
    }

    private fun showDashboard(api: String) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(22, 26, 22, 26)
            setBackgroundColor(android.graphics.Color.rgb(11, 16, 32))
        }
        val title = TextView(this).apply {
            text = "GOLDEN MIND AI • TESTNET"
            textSize = 22f
            setTextColor(android.graphics.Color.WHITE)
        }
        val badge = TextView(this).apply {
            text = "LIVE TRADING DISABLED BY DEFAULT"
            setTextColor(android.graphics.Color.rgb(56, 189, 248))
            textSize = 12f
        }
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        status = TextView(this).apply { setTextColor(android.graphics.Color.LTGRAY) }
        val refresh = Button(this).apply { text = "REFRESH ACCOUNT / HEALTH" }
        val logout = Button(this).apply { text = "SIGN OUT" }
        refresh.setOnClickListener { loadDashboard(api) }
        logout.setOnClickListener { token = null; showLogin() }
        root.addView(title, lp())
        root.addView(badge, lp())
        root.addView(space())
        root.addView(status, lp())
        root.addView(refresh, lp())
        root.addView(content, lp())
        root.addView(logout, lp())
        setContentView(root)
        loadDashboard(api)
    }

    private fun requestToken(api: String, username: String, password: String) {
        executor.execute {
            try {
                val conn = URL(api.trimEnd('/') + "/token").openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")

                val encodedUsername = java.net.URLEncoder.encode(username, "UTF-8")
                val encodedPassword = java.net.URLEncoder.encode(password, "UTF-8")
                val body = "username=" + encodedUsername + "&password=" + encodedPassword

                conn.outputStream.use { it.write(body.toByteArray()) }
                val code = conn.responseCode
                val response = (if (code in 200..299) conn.inputStream else conn.errorStream)
                    .bufferedReader().readText()

                if (code !in 200..299) {
                    throw RuntimeException("HTTP $code: $response")
                }

                val access = JSONObject(response).optString("access_token")
                if (access.isBlank()) {
                    throw RuntimeException("Token missing")
                }

                token = access
                runOnUiThread { showDashboard(api) }
            } catch (e: Exception) {
                runOnUiThread { status.text = "Sign-in failed: " + e.message }
            }
        }
    }

    private fun loadDashboard(api: String) {
        status.text = "Checking API..."
        executor.execute {
            try {
                val health = get(api.trimEnd('/') + "/health")
                val accounts = get(api.trimEnd('/') + "/accounts")
                runOnUiThread {
                    status.text = "API: ONLINE\n" + health
                    content.removeAllViews()
                    val a = TextView(this).apply {
                        text = "Accounts\n" + accounts
                        setTextColor(android.graphics.Color.WHITE)
                        textSize = 15f
                    }
                    content.addView(a, lp())
                }
            } catch (e: Exception) {
                runOnUiThread { status.text = "API error: " + e.message }
            }
        }
    }

    private fun get(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        token?.let { conn.setRequestProperty("Authorization", "Bearer " + it) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val body = stream.bufferedReader().readText()
        if (code !in 200..299) throw RuntimeException("HTTP $code: $body")
        return body
    }

    private fun lp() = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 10, 0, 10) }
    private fun space() = Space(this).apply { layoutParams = LinearLayout.LayoutParams(1, 24) }
}
