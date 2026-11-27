package com.goldenmind.ai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.UUID

private val Bg = Color(0xFF070B14)
private val Card = Color(0xFF111827)
private val Card2 = Color(0xFF1B2740)
private val Txt = Color(0xFFF8FAFC)
private val Muted = Color(0xFFA9B4C7)
private val Green = Color(0xFF31D49B)
private val Red = Color(0xFFFF6B78)
private val Amber = Color(0xFFFFC857)
private val Blue = Color(0xFF6E8CFF)
private val Purple = Color(0xFF8B6CFF)

private val GmColors = darkColorScheme(
    background = Bg,
    surface = Card,
    surfaceVariant = Card2,
    primary = Blue,
    secondary = Purple,
    onBackground = Txt,
    onSurface = Txt,
    onSurfaceVariant = Muted,
    outline = Color(0xFF47536A)
)

@Composable
fun LoginScreen(api: GoldenMindApi, onLoggedIn: () -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var serverUrl by remember { mutableStateOf(api.getBaseUrl()) }
    Box(Modifier.fillMaxSize().background(Bg).padding(24.dp), contentAlignment = Alignment.Center) {
        Surface(shape = RoundedCornerShape(28.dp), color = Card, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Default.Bolt, null, tint = Blue, modifier = Modifier.size(48.dp))
                Text("GOLDEN MIND AI", color = Txt, fontSize = 25.sp, fontWeight = FontWeight.ExtraBold)
                Text("Secure backend control center", color = Muted, fontSize = 13.sp)
                Spacer(Modifier.height(20.dp))
                OutlinedTextField(value = serverUrl, onValueChange = { serverUrl = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Backend URL") }, singleLine = true, shape = RoundedCornerShape(14.dp), colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Blue, unfocusedBorderColor = Color(0xFF526078), focusedLabelColor = Blue, unfocusedLabelColor = Muted, focusedTextColor = Txt, unfocusedTextColor = Txt, cursorColor = Blue))
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value = username, onValueChange = { username = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Username") }, singleLine = true, shape = RoundedCornerShape(14.dp), colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Blue, unfocusedBorderColor = Color(0xFF526078), focusedLabelColor = Blue, unfocusedLabelColor = Muted, focusedTextColor = Txt, unfocusedTextColor = Txt, cursorColor = Blue))
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value = password, onValueChange = { password = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Password") }, singleLine = true, shape = RoundedCornerShape(14.dp), colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Purple, unfocusedBorderColor = Color(0xFF526078), focusedLabelColor = Purple, unfocusedLabelColor = Muted, focusedTextColor = Txt, unfocusedTextColor = Txt, cursorColor = Purple))
                error?.let { Text(it, color = Red, fontSize = 11.sp, modifier = Modifier.padding(top = 8.dp)) }
                Spacer(Modifier.height(16.dp))
                Button(onClick = {
                    if (serverUrl.isBlank()) { error = "Backend URLni kiriting."; return@Button }
                    api.setBaseUrl(serverUrl)
                    busy = true
                    Thread {
                        try {
                            api.login(username, password)
                            android.os.Handler(android.os.Looper.getMainLooper()).post { busy = false; onLoggedIn() }
                        } catch (e: Exception) {
                            android.os.Handler(android.os.Looper.getMainLooper()).post { busy = false; error = e.message ?: "Login failed" }
                        }
                    }.start()
                }, Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(14.dp)) {
                    Text(if (busy) "CONNECTING…" else "SIGN IN", fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.height(10.dp))
                Text("Testnet / Paper • API secrets are server-side", color = Muted, fontSize = 10.sp)
            }
        }
    }
}


class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { GoldenMindApp() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GoldenMindApp() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val api = remember { GoldenMindApi(context) }
    var selected by remember { mutableIntStateOf(0) }
    var session by remember { mutableStateOf(api.hasSession()) }
    var health by remember { mutableStateOf<ApiHealth?>(null) }
    var accounts by remember { mutableStateOf<List<AccountInfo>>(emptyList()) }
    MaterialTheme(colorScheme = GmColors) {
        if (!session) {
            LoginScreen(api) { session = true }
            return@MaterialTheme
        }
    val mainHandler = remember { android.os.Handler(android.os.Looper.getMainLooper()) }
    LaunchedEffect(Unit) {
        Thread {
            try {
                val h = api.health()
                val a = api.accounts()
                mainHandler.post {
                    health = h
                    accounts = a
                }
            } catch (_: Exception) {
            }
        }.start()
    }
    MaterialTheme(colorScheme = darkColorScheme(background = Bg, surface = Card, primary = Blue, onBackground = Txt, onSurface = Txt)) {
        Scaffold(
            containerColor = Bg,
            bottomBar = {
                NavigationBar(containerColor = Color(0xFF0F1522)) {
                    listOf(
                        Triple("Home", Icons.Default.Home, 0),
                        Triple("Trade", Icons.Default.ShowChart, 1),
                        Triple("Robot", Icons.Default.Bolt, 2),
                        Triple("Accounts", Icons.Default.AccountBalanceWallet, 3),
                        Triple("Risk", Icons.Default.Security, 4)
                    ).forEach { (label, icon, index) ->
                        NavigationBarItem(
                            selected = selected == index,
                            onClick = { selected = index },
                            icon = { Icon(icon, label) },
                            label = { Text(label, fontSize = 11.sp) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = Txt, selectedTextColor = Txt,
                                indicatorColor = Blue.copy(alpha = .22f),
                                unselectedIconColor = Muted, unselectedTextColor = Muted
                            )
                        )
                    }
                }
            }
        ) { padding ->
            when (selected) {
                0 -> DashboardScreen(health, accounts, false, null, padding, {})
                1 -> TradeScreen(padding, api, accounts)
                2 -> RobotScreen(padding)
                3 -> AccountsScreen(accounts, api, padding)
                else -> RiskScreen(padding)
            }
        }
    }
}

@Composable
fun Header(title: String, subtitle: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(title, color = Txt, fontSize = 25.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(4.dp))
        Text(subtitle, color = Muted, fontSize = 13.sp)
    }
}

@Composable
fun StatCard(label: String, value: String, detail: String, positive: Boolean = true) {
    Surface(shape = RoundedCornerShape(18.dp), color = Card, modifier = Modifier.width(160.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text(label, color = Muted, fontSize = 12.sp)
            Spacer(Modifier.height(8.dp))
            Text(value, color = Txt, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(5.dp))
            Text(detail, color = if (positive) Green else Red, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
fun DashboardScreen(health: ApiHealth?, accounts: List<AccountInfo>, loading: Boolean, error: String?, padding: PaddingValues, onRefresh: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Header("Golden Mind", "AI Trading Control Center")
                IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, "Refresh", tint = Txt) }
            }
        }
        error?.let { msg -> item { Surface(shape = RoundedCornerShape(16.dp), color = Color(0xFF2A1820)) {
            Text(msg, color = Red, fontSize = 12.sp, modifier = Modifier.padding(14.dp))
        } } }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Backend status", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(7.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(10.dp).clip(CircleShape).background(if (health?.status == "ok") Green else Amber))
                        Spacer(Modifier.width(10.dp))
                        Text(health?.status?.uppercase() ?: if (loading) "CONNECTING…" else "OFFLINE", color = Txt, fontWeight = FontWeight.Bold)
                    }
                    Spacer(Modifier.height(14.dp))
                    StatusLine("Mode", health?.tradingMode ?: "—", Amber)
                    StatusLine("Connected accounts", (health?.accounts ?: accounts.size).toString(), Green)
                }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Safety state", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(8.dp))
                    StatusLine("Execution mode", health?.tradingMode ?: "UNKNOWN", Amber)
                    StatusLine("Broker connections", if (accounts.isEmpty()) "None" else accounts.size.toString() + " connected", Green)
                    StatusLine("Broker secrets", "Server-side only", Blue)
                    StatusLine("Kill switch", "Available in Risk", Blue)
                }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(22.dp), color = Color(0xFF111C2E)) {
                Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Security, null, tint = Blue)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text("Live values only", color = Txt, fontWeight = FontWeight.Bold)
                        Text("Unavailable P&L and win-rate values are not fabricated.", color = Muted, fontSize = 11.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun StatusLine(label: String, value: String, color: Color) {
    Row(Modifier.fillMaxWidth().padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(10.dp))
        Text(label, color = Muted, modifier = Modifier.weight(1f), fontSize = 13.sp)
        Text(value, color = Txt, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun TradeScreen(padding: PaddingValues, api: GoldenMindApi, accounts: List<AccountInfo>) {
    var side by remember { mutableStateOf("BUY") }
    var symbol by remember { mutableStateOf("BTCUSDT") }
    var quantity by remember { mutableStateOf("0.001") }
    var busy by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }

    LazyColumn(
        Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item { Header("Trade", "Manual order console") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                listOf("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT").forEach { pair ->
                    FilterChip(
                        selected = symbol == pair,
                        onClick = { symbol = pair },
                        label = { Text(pair) }
                    )
                }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Order side", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(10.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(
                            { side = "BUY" },
                            Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = if (side == "BUY") Green else Card2)
                        ) { Text("BUY") }
                        Button(
                            { side = "SELL" },
                            Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = if (side == "SELL") Red else Card2)
                        ) { Text("SELL") }
                    }
                    Spacer(Modifier.height(18.dp))
                    OutlinedTextField(
                        quantity,
                        { quantity = it },
                        Modifier.fillMaxWidth(),
                        label = { Text("Quantity") },
                        singleLine = true
                    )
                    Spacer(Modifier.height(12.dp))
                    Text("MARKET order", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(18.dp))
                    Button(
                        onClick = {
                            val account = accounts.firstOrNull { it.enabled }
                            val qty = quantity.toDoubleOrNull()
                            if (account == null || qty == null || qty <= 0) {
                                result = "No enabled account or invalid quantity"
                            } else {
                                busy = true
                                result = null
                                Thread {
                                    try {
                                        val order = api.placeMarketOrder(
                                            account.accountId,
                                            "GMAI-ANDROID-" + UUID.randomUUID().toString().replace("-", "").take(20),
                                            symbol,
                                            side,
                                            qty
                                        )
                                        android.os.Handler(android.os.Looper.getMainLooper()).post {
                                            busy = false
                                            result = order.status + ": " + order.side + " " + order.quantity + " " + order.symbol
                                        }
                                    } catch (e: Exception) {
                                        android.os.Handler(android.os.Looper.getMainLooper()).post {
                                            busy = false
                                            result = "Order rejected: " + (e.message ?: "unknown error")
                                        }
                                    }
                                }.start()
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !busy && accounts.any { it.enabled } && quantity.toDoubleOrNull()?.let { it > 0 } == true,
                        shape = RoundedCornerShape(14.dp),
                        content = {
                            Text(if (busy) "SENDING…" else "SEND TESTNET/PAPER ORDER")
                        }
                    )
                    result?.let {
                        Spacer(Modifier.height(12.dp))
                        Text(it, color = if (it.startsWith("Order rejected")) Red else Green, fontSize = 12.sp)
                    }
                }
            }
        }
        item {
            Text(
                "Orders are routed through the backend risk and execution gates. LIVE remains disabled by default.",
                color = Muted,
                fontSize = 12.sp
            )
        }
    }
}
@Composable
fun RobotScreen(padding: PaddingValues) {
    var enabled by remember { mutableStateOf(false) }
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Header("Robot", "Strategy & execution control") }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Scalping engine", fontWeight = FontWeight.Bold)
                            Text("Momentum • guarded execution", color = Muted, fontSize = 12.sp)
                        }
                        Switch(enabled, { enabled = it })
                    }
                    HorizontalDivider(Modifier.padding(vertical = 16.dp), color = Card2)
                    SettingRow("Target trades / hour", "100")
                    SettingRow("Maximum trades / hour", "100")
                    SettingRow("Cooldown", "0.5 sec")
                    SettingRow("Max spread", "0.08%")
                    SettingRow("Data freshness", "2.0 sec")
                }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(22.dp), color = Color(0xFF111C2E)) {
                Column(Modifier.padding(18.dp)) {
                    Text("Important", color = Blue, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(7.dp))
                    Text("The engine never trades just to hit a trade-count target. Signal quality and risk gates remain mandatory.", color = Muted, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun SettingRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Text(label, color = Muted, modifier = Modifier.weight(1f), fontSize = 13.sp)
        Text(value, color = Txt, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
    }
}

@Composable
fun AccountsScreen(accounts: List<AccountInfo>, api: GoldenMindApi, padding: PaddingValues) {
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Header("Accounts", "Broker connections") }
        if (accounts.isEmpty()) item { Text("No accounts returned by backend.", color = Muted, fontSize = 13.sp) }
        items(accounts, key = { it.accountId }) { account ->
            var state by remember(account.accountId) { mutableStateOf<AccountState?>(null) }
            var error by remember(account.accountId) { mutableStateOf<String?>(null) }
            LaunchedEffect(account.accountId) {
                Thread {
                    try {
                        val s = api.state(account.accountId)
                        android.os.Handler(android.os.Looper.getMainLooper()).post { state = s }
                    } catch (e: Exception) {
                        android.os.Handler(android.os.Looper.getMainLooper()).post { error = e.message }
                    }
                }.start()
            }
            Surface(shape = RoundedCornerShape(20.dp), color = Card) {
                Column(Modifier.padding(18.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(44.dp).clip(CircleShape).background(if (account.enabled) Green.copy(alpha=.15f) else Red.copy(alpha=.15f)), contentAlignment = Alignment.Center) {
                            Icon(Icons.Default.AccountBalance, null, tint = if (account.enabled) Green else Red)
                        }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(account.accountId, color = Txt, fontWeight = FontWeight.Bold)
                            Text(account.broker + " • " + account.mode, color = Muted, fontSize = 12.sp)
                        }
                        Text(if (account.enabled) "ENABLED" else "DISABLED", color = if (account.enabled) Green else Red, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                    Spacer(Modifier.height(12.dp))
                    Text("State: " + if (state?.confirmed == true) "RECONCILED" else "UNCONFIRMED",
                        color = if (state?.confirmed == true) Green else Amber, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    state?.balances?.entries?.take(3)?.forEach { (asset, value) ->
                        SettingRow(asset, "%.6f".format(java.util.Locale.US, value))
                    }
                    error?.let { Text(it, color = Red, fontSize = 10.sp) }
                }
            }
        }
    }
}

@Composable
fun RiskScreen(padding: PaddingValues) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val api = remember { GoldenMindApi(context) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    LazyColumn(
        Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item { Header("Risk Center", "Protection before profit") }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Configured limits", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(8.dp))
                    SettingRow("Daily loss limit", "3.00%")
                    SettingRow("Risk / trade", "0.25%")
                    SettingRow("Max positions", "3")
                    SettingRow("Kill switch", "Backend protected")
                    SettingRow("State reconciliation", "Required before execution")
                }
            }
        }
        item {
            Button(
                onClick = {
                    busy = true
                    message = null
                    Thread {
                        try {
                            api.emergencyStop()
                            android.os.Handler(android.os.Looper.getMainLooper()).post {
                                busy = false
                                message = "Emergency stop activated."
                            }
                        } catch (e: Exception) {
                            android.os.Handler(android.os.Looper.getMainLooper()).post {
                                busy = false
                                message = "Emergency stop failed: " + (e.message ?: "unknown error")
                            }
                        }
                    }.start()
                },
                modifier = Modifier.fillMaxWidth().height(54.dp),
                enabled = !busy,
                colors = ButtonDefaults.buttonColors(containerColor = Red),
                shape = RoundedCornerShape(16.dp),
                content = {
                    Icon(Icons.Default.Warning, null)
                    Spacer(Modifier.width(8.dp))
                    Text(if (busy) "STOPPING…" else "EMERGENCY STOP", fontWeight = FontWeight.ExtraBold)
                }
            )
        }
        message?.let {
            item { Text(it, color = if (it.startsWith("Emergency stop failed")) Red else Green, fontSize = 12.sp) }
        }
    }
}
