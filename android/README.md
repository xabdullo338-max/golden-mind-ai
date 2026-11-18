# Golden Mind AI Android

Native Jetpack Compose control-center app for Golden Mind AI.

## Build locally

From the repository root:

```bash
cd android
gradle assembleDebug
```

The APK is generated at:

`app/build/outputs/apk/debug/app-debug.apk`

## Safety

This app currently ships as a PAPER/monitoring UI shell. It does not embed Binance or IBKR API secrets. LIVE trading must remain controlled by the authenticated backend safety gates.

The GitHub Actions workflow builds an installable debug APK on every Android-project change.

## Backend connection

The Android client does not contain Binance/IBKR API keys. It stores only the backend JWT in Android Keystore-backed encrypted storage.

### Emulator
The debug build defaults to `http://10.0.2.2:8000` (Android emulator -> host machine).

### Physical phone / production
Build with an HTTPS backend URL:

```bash
gradle -PAPI_BASE_URL=https://YOUR_BACKEND_HOST assembleDebug
```

For local HTTP testing on a physical phone, use your computer's LAN IP and keep the debug build only. Release deployments should use HTTPS.

### Current screens
- Dashboard: backend health, mode, account state and balance
- Trade: authenticated market-order submission through backend gates
- Accounts: broker/account status and reconciled balances
- Robot: scalping controls and safety constraints
- Risk: emergency global kill switch
