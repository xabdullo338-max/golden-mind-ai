package ai.goldenmind

import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.*
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : android.app.Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private var token: String? = null
    private var language = "uz"
    private val gold = android.graphics.Color.rgb(255, 194, 45)
    private val white = android.graphics.Color.WHITE
    private val panel = android.graphics.Color.rgb(10, 20, 36)
    private fun tr(key: String): String = when (language) {
        "ru" -> mapOf("signin" to "ВОЙТИ", "username" to "Имя пользователя", "password" to "Пароль", "subtitle" to "AI-система торговли и контроля риска", "backend" to "Безопасный центр управления", "testnet" to "TESTNET / PAPER", "dashboard" to "Главная", "refresh" to "Обновить", "logout" to "ВЫЙТИ", "risk" to "Контроль риска", "bot" to "Торговый бот").getOrDefault(key, key)
        "en" -> mapOf("signin" to "SIGN IN", "username" to "Username", "password" to "Password", "subtitle" to "AI Trading & Risk Control System", "backend" to "Secure Backend Control Center", "testnet" to "TESTNET / PAPER", "dashboard" to "Dashboard", "refresh" to "Refresh", "logout" to "SIGN OUT", "risk" to "Risk Control", "bot" to "Trading Bot").getOrDefault(key, key)
        else -> mapOf("signin" to "KIRISH", "username" to "Foydalanuvchi nomi", "password" to "Parol", "subtitle" to "AI savdo va xavfsizlik boshqaruv tizimi", "backend" to "Xavfsiz backend boshqaruv markazi", "testnet" to "TESTNET / PAPER", "dashboard" to "Bosh sahifa", "refresh" to "Yangilash", "logout" to "CHIQISH", "risk" to "Risk boshqaruvi", "bot" to "Savdo boti").getOrDefault(key, key)
    }
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
            setBackgroundColor(android.graphics.Color.rgb(3, 9, 20))
        }
        val title = TextView(this).apply {
            text = "◉  GOLDEN MIND AI"
            textSize = 30f
            setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
            setTextColor(gold)
            gravity = Gravity.CENTER
        }
        val subtitle = TextView(this).apply {
            text = tr("subtitle")
            textSize = 14f
            setTextColor(android.graphics.Color.LTGRAY)
            gravity = Gravity.CENTER
        }
        baseUrl = EditText(this).apply {
            hint = "https://golden-mind-ai.vercel.app"
            setSingleLine()
            setText("https://golden-mind-ai.vercel.app")
            setTextColor(gold)
            setHintTextColor(android.graphics.Color.GRAY)
        }
        val user = EditText(this).apply {
            hint = tr("username")
            setSingleLine()
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }
        val pass = EditText(this).apply {
            hint = tr("password")
            inputType = 0x81
            setSingleLine()
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }
        val login = Button(this).apply { text = tr("signin"); setTextColor(android.graphics.Color.rgb(30,25,5)); setBackgroundColor(gold); minHeight = 54 }
        status = TextView(this).apply {
            setTextColor(android.graphics.Color.LTGRAY)
            gravity = Gravity.CENTER
        }
        login.setOnClickListener {
            status.text = "Connecting..."
            requestToken(baseUrl.text.toString(), user.text.toString(), pass.text.toString())
        }
        val logo = ImageView(this).apply {
            setImageResource(com.goldenmind.ai.R.drawable.golden_mind_logo)
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            layoutParams = LinearLayout.LayoutParams(-1, 220).apply { setMargins(0, 0, 0, 8) }
        }
        root.addView(logo)
        root.addView(title, lp())
        val lang = Spinner(this)
        lang.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, listOf("🇺🇿 O‘zbekcha", "🇷🇺 Русский", "🇬🇧 English"))
        lang.setSelection(if (language == "uz") 0 else if (language == "ru") 1 else 2)
        lang.setOnItemSelectedListener(object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val nl = listOf("uz", "ru", "en")[position]
                if (nl != language) { language = nl; showLogin() }
            }
        })
        root.addView(lang, lp())
        root.addView(subtitle, lp())
        root.addView(space())
        root.addView(baseUrl, lp())
        root.addView(user, lp())
        root.addView(pass, lp())
        root.addView(login, lp())
        root.addView(TextView(this).apply { text = "🔒 HTTPS • 🧪 " + tr("testnet"); textSize = 12f; setTextColor(android.graphics.Color.rgb(80,220,130)); gravity = Gravity.CENTER }, lp())
        root.addView(status, lp())
        setContentView(root)
    }

    private fun showDashboard(api: String) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(22, 26, 22, 26)
            setBackgroundColor(android.graphics.Color.rgb(3, 9, 20))
        }
        val title = TextView(this).apply {
            text = "GOLDEN MIND AI  •  " + tr("testnet")
            textSize = 23f
            setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
            setTextColor(android.graphics.Color.WHITE)
        }
        val badge = TextView(this).apply {
            text = "🛡 " + tr("risk") + "  •  TESTNET  •  ONLINE"
            setTextColor(gold)
            textSize = 12f
        }
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        status = TextView(this).apply { setTextColor(android.graphics.Color.LTGRAY) }
        val refresh = Button(this).apply { text = tr("refresh"); setTextColor(android.graphics.Color.rgb(30,25,5)); setBackgroundColor(gold) }
        val logout = Button(this).apply { text = tr("logout") }
        refresh.setOnClickListener { loadDashboard(api) }
        logout.setOnClickListener { token = null; showLogin() }
        val logo = ImageView(this).apply {
            setImageResource(com.goldenmind.ai.R.drawable.golden_mind_logo)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            layoutParams = LinearLayout.LayoutParams(-1, 180).apply { setMargins(0, 0, 0, 4) }
        }
        root.addView(logo)
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
