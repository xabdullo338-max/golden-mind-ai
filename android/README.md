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
