from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

import httpx
import websockets


BASE_URL = os.getenv("BINANCE_BASE_URL", "https://testnet.binance.vision").rstrip("/")
WS_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"
API_KEY = os.environ["BINANCE_API_KEY"]
API_SECRET = os.environ["BINANCE_API_SECRET"]
SYMBOL = os.getenv("BINANCE_TEST_SYMBOL", "BTCUSDT").upper()
QUOTE_USDT = Decimal(os.getenv("BINANCE_TEST_QUOTE_USDT", "10"))
TIMEOUT = 15.0


def sign(params: dict[str, object]) -> str:
    query = urlencode({k: v for k, v in sorted(params.items())})
    return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


async def rest(client: httpx.AsyncClient, method: str, path: str, *,
               signed: bool = False, params: dict[str, object] | None = None):
    params = dict(params or {})
    if signed:
        params.setdefault("timestamp", int(time.time() * 1000))
        params.setdefault("recvWindow", 5000)
        params["signature"] = sign(params)
    response = await client.request(
        method, f"{BASE_URL}{path}", params=params,
        headers={"X-MBX-APIKEY": API_KEY},
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Binance {response.status_code}: {response.text[:800]}")
    return response.json()


def step_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


async def ws_subscribe(ws):
    params = {
        "apiKey": API_KEY,
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000,
    }
    params["signature"] = sign(params)
    request_id = str(uuid.uuid4())
    await ws.send(json.dumps({
        "id": request_id,
        "method": "userDataStream.subscribe.signature",
        "params": params,
    }))
    while True:
        message = json.loads(await ws.recv())
        if message.get("id") == request_id:
            if message.get("status") != 200 or message.get("error"):
                raise RuntimeError(f"User stream subscription rejected: {message}")
            return


async def wait_execution(ws, client_order_id: str, timeout: float = 20.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        remaining = max(0.1, deadline - asyncio.get_running_loop().time())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        message = json.loads(raw)
        event = message.get("event", message)
        if not isinstance(event, dict):
            continue
        if event.get("e") == "executionReport" and event.get("c") == client_order_id:
            return event
    raise RuntimeError(f"No executionReport received for {client_order_id}")


async def main():
    if "testnet.binance.vision" not in BASE_URL:
        raise RuntimeError("REFUSING TO RUN: BINANCE_BASE_URL is not Binance TESTNET")
    if not API_KEY.strip() or not API_SECRET.strip():
        raise RuntimeError("BINANCE_API_KEY and BINANCE_API_SECRET are required")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        await rest(client, "GET", "/api/v3/ping")
        server_time = await rest(client, "GET", "/api/v3/time")
        info = await rest(client, "GET", "/api/v3/exchangeInfo", params={"symbol": SYMBOL})
        account_before = await rest(client, "GET", "/api/v3/account", signed=True)

        symbol_info = info["symbols"][0]
        filters = {item["filterType"]: item for item in symbol_info["filters"]}
        lot = filters["LOT_SIZE"]
        step = Decimal(lot["stepSize"])
        min_qty = Decimal(lot["minQty"])
        min_notional = Decimal(
            filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional", "0")
        )

        ticker = await rest(client, "GET", "/api/v3/ticker/price", params={"symbol": SYMBOL})
        price = Decimal(str(ticker["price"]))
        quantity = step_down(QUOTE_USDT / price, step)
        if quantity < min_qty:
            raise RuntimeError(f"Calculated quantity {quantity} is below minQty {min_qty}")
        if quantity * price < min_notional:
            raise RuntimeError(
                f"Calculated notional {quantity * price} is below minNotional {min_notional}"
            )

        base_asset = symbol_info["baseAsset"]
        quote_asset = symbol_info["quoteAsset"]
        balances = {
            item["asset"]: Decimal(item["free"])
            for item in account_before["balances"]
            if Decimal(item["free"]) > 0
        }
        if balances.get(quote_asset, Decimal("0")) < quantity * price:
            raise RuntimeError(
                f"Insufficient TESTNET {quote_asset} balance for smoke order: "
                f"need ~{quantity * price}, have {balances.get(quote_asset, Decimal('0'))}"
            )

        async with websockets.connect(
            WS_URL, ping_interval=20, ping_timeout=20, close_timeout=5
        ) as ws:
            await ws_subscribe(ws)

            client_id = f"GMAI-SMOKE-{uuid.uuid4().hex[:16]}"
            buy = await rest(
                client, "POST", "/api/v3/order", signed=True,
                params={
                    "symbol": SYMBOL,
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": format(quantity, "f"),
                    "newClientOrderId": client_id,
                },
            )
            buy_event = await wait_execution(ws, client_id)

            if buy.get("status") != "FILLED" or buy_event.get("X") != "FILLED":
                raise RuntimeError(f"BUY was not fully executed: REST={buy} WS={buy_event}")

            executed_qty = Decimal(str(buy["executedQty"]))
            if executed_qty <= 0:
                raise RuntimeError("BUY executedQty is zero")

            sell_qty = step_down(executed_qty, step)
            sell_id = f"GMAI-SMOKE-SELL-{uuid.uuid4().hex[:12]}"
            sell = await rest(
                client, "POST", "/api/v3/order", signed=True,
                params={
                    "symbol": SYMBOL,
                    "side": "SELL",
                    "type": "MARKET",
                    "quantity": format(sell_qty, "f"),
                    "newClientOrderId": sell_id,
                },
            )
            sell_event = await wait_execution(ws, sell_id)

            if sell.get("status") != "FILLED" or sell_event.get("X") != "FILLED":
                raise RuntimeError(f"SELL was not fully executed: REST={sell} WS={sell_event}")

            order_check = await rest(
                client, "GET", "/api/v3/order", signed=True,
                params={"symbol": SYMBOL, "origClientOrderId": client_id},
            )
            account_after = await rest(client, "GET", "/api/v3/account", signed=True)

    print("GMAI TESTNET SMOKE TEST: PASS")
    print(f"serverTime={server_time['serverTime']}")
    print(f"symbol={SYMBOL}")
    print(f"buy_order_id={buy['orderId']} executedQty={buy['executedQty']}")
    print(f"buy_ws_status={buy_event['X']} ws_execType={buy_event['x']}")
    print(f"sell_order_id={sell['orderId']} executedQty={sell['executedQty']}")
    print(f"sell_ws_status={sell_event['X']} ws_execType={sell_event['x']}")
    print(f"order_recheck_status={order_check['status']}")
    print("REST order acceptance + WebSocket execution + post-trade account read: VERIFIED")


if __name__ == "__main__":
    asyncio.run(main())
