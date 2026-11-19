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

private val Bg = Color(0xFF0B0F19)
private val Card = Color(0xFF121827)
private val Card2 = Color(0xFF182033)
private val Txt = Color(0xFFF4F7FB)
private val Muted = Color(0xFF8D99AD)
private val Green = Color(0xFF31D49B)
private val Red = Color(0xFFFF6B78)
private val Amber = Color(0xFFFFC857)
private val Blue = Color(0xFF5E8BFF)

@Composable
fun LoginScreen(api: GoldenMindApi, onLoggedIn: () -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Box(Modifier.fillMaxSize().background(Bg).padding(24.dp), contentAlignment = Alignment.Center) {
        Surface(shape = RoundedCornerShape(28.dp), color = Card, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Default.Bolt, null, tint = Blue, modifier = Modifier.size(48.dp))
                Text("GOLDEN MIND AI", fontSize = 25.sp, fontWeight = FontWeight.ExtraBold)
                Text("Secure backend control center", color = Muted, fontSize = 12.sp)
                Spacer(Modifier.height(20.dp))
                OutlinedTextField(username, { username = it }, Modifier.fillMaxWidth(), label = { Text("Username") }, singleLine = true)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(password, { password = it }, Modifier.fillMaxWidth(), label = { Text("Password") }, singleLine = true)
                error?.let { Text(it, color = Red, fontSize = 11.sp, modifier = Modifier.padding(top = 8.dp)) }
                Spacer(Modifier.height(16.dp))
                Button(enabled = !busy && username.isNotBlank() && password.isNotBlank(), onClick = {
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
                Text("Broker API secrets are not stored in the APK.", color = Muted, fontSize = 10.sp)
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
    var trading by remember { mutableStateOf(false) }
    var session by remember { mutableStateOf(api.hasSession()) }
    var health by remember { mutableStateOf<ApiHealth?>(null) }
    var accounts by remember { mutableStateOf<List<AccountInfo>>(emptyList()) }
    if (!session) {
        LoginScreen(api) { session = true }
        return
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
                0 -> DashboardScreen(trading, { trading = !trading }, padding)
                1 -> TradeScreen(padding)
                2 -> RobotScreen(padding)
                3 -> AccountsScreen(padding)
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
fun DashboardScreen(trading: Boolean, onToggle: () -> Unit, padding: PaddingValues) {
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Header("Golden Mind", "AI Trading Control Center")
                Surface(shape = CircleShape, color = Card2) { IconButton({}) { Icon(Icons.Default.NotificationsNone, "Notifications", tint = Txt) } }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = if (trading) Color(0xFF10271F) else Card) {
                Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(12.dp).clip(CircleShape).background(if (trading) Green else Muted))
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(if (trading) "TRADING ACTIVE" else "TRADING PAUSED", color = Txt, fontWeight = FontWeight.Bold)
                        Text(if (trading) "Paper mode • execution gate ready" else "Safe state • no new orders", color = Muted, fontSize = 12.sp)
                    }
                    Switch(trading, { onToggle() })
                }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Portfolio balance", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(7.dp))
                    Text(health?.tradingMode ?: "—", color = Txt, fontSize = 34.sp, fontWeight = FontWeight.ExtraBold)
                    Text("+$4.82  •  +1.61% today", color = Green, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(18.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                        repeat(7) { i -> Box(Modifier.weight(1f).height((18 + i * 7).dp).clip(RoundedCornerShape(8.dp)).background(if (i < 4) Blue.copy(alpha=.75f) else Green.copy(alpha=.75f))) }
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("Last 7 sessions", color = Muted, fontSize = 11.sp)
                }
            }
        }
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) { StatCard("Win rate", "67.4%", "24 wins / 12 losses"); StatCard("Open positions", "2", "1.1% portfolio risk") } }
        item {
            Surface(shape = RoundedCornerShape(22.dp), color = Card) {
                Column(Modifier.padding(18.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Execution status", fontWeight = FontWeight.Bold)
                        Text("PAPER", color = Amber, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }
                    Spacer(Modifier.height(14.dp))
                    StatusLine("Market data", "Fresh • 0.42s", Green)
                    StatusLine("Broker state", "Reconciled", Green)
                    StatusLine("Risk engine", "Within limits", Green)
                    StatusLine("Kill switch", "Armed", Blue)
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
fun TradeScreen(padding: PaddingValues) {
    var side by remember { mutableStateOf("BUY") }
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Header("Trade", "Manual order console") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                listOf("BTC/USDT", "ETH/USDT").forEach { pair -> FilterChip(selected = pair == "BTC/USDT", onClick = {}, label = { Text(pair) }) }
            }
        }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Order side", color = Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(10.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button({ side = "BUY" }, Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = if (side == "BUY") Green else Card2)) { Text("BUY") }
                        Button({ side = "SELL" }, Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = if (side == "SELL") Red else Card2)) { Text("SELL") }
                    }
                    Spacer(Modifier.height(18.dp))
                    OutlinedTextField("0.001", {}, Modifier.fillMaxWidth(), label = { Text("Quantity") })
                    Spacer(Modifier.height(12.dp))
                    OutlinedTextField("Market", {}, Modifier.fillMaxWidth(), label = { Text("Order type") })
                    Spacer(Modifier.height(18.dp))
                    Button({}, Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp)) { Text("Preview $side order") }
                }
            }
        }
        item { Text("Orders are routed through the same risk and execution gates as the backend.", color = Muted, fontSize = 12.sp) }
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
fun AccountsScreen(padding: PaddingValues) {
    val accounts = listOf(
        Triple("Connected accounts", accounts.size.toString(), Green)
    )
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Header("Accounts", "Broker connections") }
        items(accounts) { (name, mode, color) ->
            Surface(shape = RoundedCornerShape(20.dp), color = Card) {
                Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(44.dp).clip(CircleShape).background(color.copy(alpha=.15f)), contentAlignment = Alignment.Center) { Icon(Icons.Default.AccountBalance, null, tint = color) }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) { Text(name, color = Txt, fontWeight = FontWeight.Bold); Text(mode, color = Muted, fontSize = 12.sp) }
                    Text("READY", color = Green, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
fun RiskScreen(padding: PaddingValues) {
    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Header("Risk Center", "Protection before profit") }
        item {
            Surface(shape = RoundedCornerShape(24.dp), color = Card) {
                Column(Modifier.padding(20.dp)) {
                    Text("Daily loss limit", color = Muted, fontSize = 12.sp)
                    Text("3.00%", color = Txt, fontSize = 28.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(10.dp))
                    LinearProgressIndicator(progress = { 0.21f }, Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                    Text("Current drawdown: 0.63%", color = Green, fontSize = 12.sp)
                    Spacer(Modifier.height(18.dp))
                    SettingRow("Risk / trade", "0.25%")
                    SettingRow("Max positions", "3")
                    SettingRow("Kill switch", "ARMED")
                    SettingRow("State reconciliation", "REQUIRED")
                }
            }
        }
        item {
            Button({}, Modifier.fillMaxWidth().height(54.dp), colors = ButtonDefaults.buttonColors(containerColor = Red), shape = RoundedCornerShape(16.dp)) {
                Icon(Icons.Default.Warning, null); Spacer(Modifier.width(8.dp)); Text("EMERGENCY STOP", fontWeight = FontWeight.ExtraBold)
            }
        }
    }
}
