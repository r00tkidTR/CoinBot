import os
import time
import csv
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *
from utils import get_rsi

load_dotenv()
api_key = os.getenv("API_KEY")
api_secret = os.getenv("API_SECRET")
client = Client(api_key, api_secret)
client.FUTURES_DEFAULT_TYPE = 'USD-M'

symbol_list = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def open_trade(symbol, side, amount=10, leverage=10):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        price = float(client.futures_mark_price(symbol=symbol)["markPrice"])
        quantity = round(amount / price, 3)
        order_side = SIDE_BUY if side == "LONG" else SIDE_SELL

        # Pozisyon aç
        order = client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type=FUTURE_ORDER_TYPE_MARKET,
            quantity=quantity
        )

        # SL - TP
        sl_price = round(price * (0.98 if side == "LONG" else 1.02), 2)
        tp_price = round(price * (1.05 if side == "LONG" else 0.95), 2)
        close_side = SIDE_SELL if side == "LONG" else SIDE_BUY

        # SL
        client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=sl_price,
            closePosition=True,
            timeInForce='GTC'
        )

        # TP
        client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
            stopPrice=tp_price,
            closePosition=True,
            timeInForce='GTC'
        )

        print(f"✅ {symbol} için {side} pozisyon açıldı | Giriş: {price}, SL: {sl_price}, TP: {tp_price}")
        log_trade(symbol, side, price, sl_price, tp_price)

    except Exception as e:
        print(f"❌ Hata: {symbol} - {e}")

def log_trade(symbol, side, entry, sl, tp):
    with open("trade_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), symbol, side, entry, sl, tp])

while True:
    for symbol in symbol_list:
        try:
            rsi = get_rsi(client, symbol)
            if rsi < 30:
                open_trade(symbol, "LONG")
            elif rsi > 70:
                open_trade(symbol, "SHORT")
        except Exception as e:
            print(f"{symbol} için RSI alınamadı: {e}")
        time.sleep(5)  # Binance rate limit'e takılmamak için
    time.sleep(900)  # Her 15 dakikada bir tekrar çalışır
