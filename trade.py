# High-performance event loop for asyncio
import uvloop

# Standard libraries
import os, sys, time, hmac, hashlib, base64, json, uuid, asyncio

# HTTP + WebSocket client
import aiohttp

# Load environment variables from .env file
from dotenv import load_dotenv

# Use uvloop for faster async operations
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Load credentials and config from file
load_dotenv("apikey.env")

# Retrieve credentials and endpoints from environment
API_KEY        = os.getenv("API_KEY")
api_secret_str = os.getenv("API_SECRET")
API_SECRET     = base64.b64decode(api_secret_str)  # decode secret from base64
BASE_URL       = os.getenv("BASE_URL",    "https://arkm.com/api")
BASE_WS_URL    = os.getenv("BASE_WS_URL", "wss://arkm.com/ws")

# Trading parameters
SPREAD_THRESHOLD    = 0.0111  # max allowed spread for trading
SPREAD_LOG_INTERVAL = 1.0     # log spread every X seconds
SLEEP_DELAY         = 0.131   # delay between checks (throttling)

# Order book structure (price: size)
orderbook_data      = {"bids": {}, "asks": {}}
current_spread      = None
last_spread_log     = 0.0

# Volume goals
TARGET_VOLUME_USD    = 505_000
BTC_PRICE_FOR_TARGET = 105000.0
TARGET_VOLUME_BTC    = TARGET_VOLUME_USD / BTC_PRICE_FOR_TARGET

# Track total traded volume and time
total_traded_volume = 0.0
total_traded_usd    = 0.0
last_trade_time     = time.time()

# Timestamp helper
def ts():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

# HMAC signature generator for API requests
def sign_request(method, path, body=""):
    expires = str(int(time.time() * 1_000_000) + 300_000_000)
    msg     = API_KEY + expires + method + path + body
    sig     = hmac.new(API_SECRET, msg.encode(), hashlib.sha256).digest()
    return expires, base64.b64encode(sig).decode()

# WebSocket auth headers generator
def ws_auth_headers():
    method = "GET"; path = "/ws"
    expires = str(int(time.time()) + 300) + "000000"
    msg     = API_KEY + expires + method + path
    sig     = hmac.new(API_SECRET, msg.encode(), hashlib.sha256).digest()
    return {
        "Arkham-API-Key":   API_KEY,
        "Arkham-Expires":   expires,
        "Arkham-Signature": base64.b64encode(sig).decode()
    }

# Submit market order (buy or sell)
async def place_order(session, symbol, side, size, subaccount_id=0):
    path    = "/orders/new"; method = "POST"
    payload = {
        "clientOrderId": str(uuid.uuid4()),
        "postOnly": False,
        "price": "0",
        "reduceOnly": False,
        "side": side,
        "size": f"{float(size):.5f}",
        "subaccountId": subaccount_id,
        "symbol": symbol,
        "type": "market"
    }
    body = json.dumps(payload)
    expires, signature = sign_request(method, path, body)
    headers = {
        "Content-Type":       "application/json",
        "Arkham-API-Key":     API_KEY,
        "Arkham-Expires":     expires,
        "Arkham-Signature":   signature
    }
    try:
        async with session.post(BASE_URL + path, headers=headers, json=payload, timeout=5) as resp:
            if resp.status == 200:
                return True
            print(f"{ts()} [DEBUG] Order failed {resp.status}")
            return False
    except Exception as e:
        print(f"{ts()} [DEBUG] Exception placing order: {e}")
        return False

# Calculate the spread from best bid and ask
def recalc_spread():
    global current_spread, last_spread_log
    bids = orderbook_data["bids"]
    asks = orderbook_data["asks"]
    if bids and asks:
        best_bid = max(bids)
        best_ask = min(asks)
        current_spread = best_ask - best_bid
        now = time.time()
        if now - last_spread_log >= SPREAD_LOG_INTERVAL:
            print(f"{ts()} [SPREAD] {current_spread:.2f}")
            last_spread_log = now
    else:
        current_spread = None

# Replace full orderbook with snapshot data
def process_snapshot(data):
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    orderbook_data["bids"].clear()
    orderbook_data["asks"].clear()
    for e in bids:
        try:
            price = float(e["price"]) if isinstance(e, dict) else float(e[0])
            size  = float(e["size"])  if isinstance(e, dict) else float(e[1])
        except Exception:
            continue
        orderbook_data["bids"][price] = size
    for e in asks:
        try:
            price = float(e["price"]) if isinstance(e, dict) else float(e[0])
            size  = float(e["size"])  if isinstance(e, dict) else float(e[1])
        except Exception:
            continue
        orderbook_data["asks"][price] = size
    recalc_spread()

# Apply incremental update to orderbook
def process_update(data):
    updates = data if isinstance(data, list) else [data]
    for item in updates:
        try:
            price = float(item["price"]) if isinstance(item, dict) else float(item[0])
            size  = float(item["size"])  if isinstance(item, dict) else float(item[1])
            side  = item.get("side")     if isinstance(item, dict) else (item[2] if len(item) > 2 else None)
        except Exception:
            continue
        book = orderbook_data["bids"] if side == "buy" else orderbook_data["asks"]
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size
        recalc_spread()

# Listen for live orderbook updates via WebSocket
async def ws_orderbook_listener(symbol, session):
    sub_msg = {
        "args": {"channel": "l2_updates", "params": {"group": "0.01", "snapshot": True, "symbol": symbol}},
        "confirmationId": "abc123",
        "method": "subscribe"
    }
    retry_count = 0

    while True:
        headers = ws_auth_headers()
        try:
            async with session.ws_connect(BASE_WS_URL, heartbeat=30, headers=headers) as ws:
                retry_count = 0
                await ws.send_json(sub_msg)
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("channel") == "l2_updates" and "data" in data:
                            if data.get("type") == "snapshot":
                                process_snapshot(data["data"])
                            else:
                                process_update(data["data"])
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        break
        except aiohttp.WSServerHandshakeError as e:
            if e.status == 403:
                print(f"{ts()} [WS ERROR] 403 Forbidden – check your API key/secret/permissions and aborting.")
                break
            delay = min(60, 2**retry_count)
            print(f"{ts()} [WS ERROR] handshake {e.status}, retrying in {delay}s")
            await asyncio.sleep(delay)
            retry_count += 1
        except Exception as e:
            print(f"{ts()} [WS ERROR] {type(e).__name__}: {e}, retrying in 5s")
            await asyncio.sleep(5)
        await asyncio.sleep(1)

# Auto-trading logic triggered when spread is tight
async def auto_trade(symbol="BTC_USDT_PERP"):
    global total_traded_volume, total_traded_usd, last_trade_time
    fixed_order_size   = 0.00371  # target size per leg
    min_trade_size     = 0.00006  # fallback size for illiquid book
    spread_valid_since = None

    async with aiohttp.ClientSession() as order_session:
        while total_traded_volume < TARGET_VOLUME_BTC:
            if current_spread is None or current_spread > SPREAD_THRESHOLD:
                spread_valid_since = None
                await asyncio.sleep(SLEEP_DELAY)
                continue

            if spread_valid_since is None:
                spread_valid_since = time.time()
            if time.time() - spread_valid_since < 0.51:
                await asyncio.sleep(SLEEP_DELAY)
                continue

            # Calculate best prices and available volumes
            best_bid = max(orderbook_data["bids"])
            best_ask = min(orderbook_data["asks"])
            avail_bid = orderbook_data["bids"][best_bid]
            avail_ask = orderbook_data["asks"][best_ask]
            size = min(fixed_order_size, avail_bid, avail_ask)

            # If value too small, use minimal fallback size
            if size * best_bid < 5:
                size = min_trade_size

            # Place simultaneous buy/sell market orders
            buy_ok, sell_ok = await asyncio.gather(
                place_order(order_session, symbol, "buy",  size),
                place_order(order_session, symbol, "sell", size),
            )
            if buy_ok and sell_ok:
                last_trade_time = time.time()
                total_traded_volume += size * 2
                trade_usd = size * (best_bid + best_ask)
                total_traded_usd += trade_usd
                print(f"{ts()} [VOLUME] {total_traded_usd:.2f} USD")
                spread_valid_since = None

            await asyncio.sleep(SLEEP_DELAY)

        print(f"{ts()} [TARGET] reached {total_traded_volume:.5f} BTC")
        os._exit(0)

# Entrypoint: starts both orderbook listener and trading loop
async def main():
    symbol = "BTC_USDT_PERP"
    connector = aiohttp.TCPConnector(limit=100, keepalive_timeout=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(
            ws_orderbook_listener(symbol, session),
            auto_trade(symbol),
        )

# Run the event loop
if __name__ == "__main__":
    asyncio.run(main())
