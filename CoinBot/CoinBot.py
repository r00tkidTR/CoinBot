# main.py
from pkgutil import get_loader
import requests
import pandas as pd
import joblib
import json
import atexit
import signal
import sys
from binance.client import Client
from binance.enums import *
from telegram import Bot
import schedule
import time
import os
import traceback
import numpy as np
import threading
import ta
import warnings
warnings.filterwarnings("ignore", message="python-telegram-bot is using upstream urllib3.*")

# === Ayarlar ===
BINANCE_API_KEY = "oGzSEClmbwGvnnXP25s8nWc5TPaUVPr3AfvJ30pLZvlscpUwX4Pkm8cwbzB4YUaN"
BINANCE_SECRET = "uXQf6tjSFcO11p0uBTE90LYVOpOI9AYEZRnLhI0VZdWb23yQekI1eu73JH8JBo84"
TELEGRAM_TOKEN = "7869953064:AAHmBKtVL18HDUw9TR1eHqehK4PxQsm1uAU"
TELEGRAM_CHAT_ID = "1559265898"
CRYPTO_PANIC_KEY = "e50d3fd378d7719a4bd0fd602047ca0c91c0d420"
RISK_LIMIT_PER_SYMBOL = 100  # Maksimum risk USDT cinsinden

client = Client(BINANCE_API_KEY, BINANCE_SECRET)
bot = Bot(token=TELEGRAM_TOKEN)

position_data = {}
long_count = 0
short_count = 0
max_trade = 0

# === Programdan çıkarken Telegram'a mesaj gönder ===
def notify_exit():
    try:
        send_telegram("🚨 Bot kapatıldı veya sonlandırıldı.")
    except:
        pass

atexit.register(notify_exit)

# CTRL+C (SIGINT) veya kill (SIGTERM) gibi sinyallerde çalışır
def handle_signal(sig, frame):
    notify_exit()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# === JSON Logla ===
def log_json(data, filename="log.json"):
    data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

# === Telegram Bildir ===
def send_telegram(msg):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

send_telegram("Bot başlatıldı")

# === Teknik Analiz Fonksiyonları ===
def get_rsi(client, symbol, interval='5m', period=14):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=period + 1)
    closes = [float(kline[4]) for kline in klines]
    deltas = pd.Series(closes).diff()
    gain = deltas[deltas > 0].mean()
    loss = -deltas[deltas < 0].mean()
    rs = gain / loss if loss != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_volatility(symbol, interval='5m', period=20):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=period)
    closes = [float(kline[4]) for kline in klines]
    volatility = np.std(closes)
    return volatility

def get_technical_signals(symbol):
    df = pd.DataFrame(client.get_klines(symbol=symbol, interval='5m', limit=100))
    df = df[[0, 1, 2, 3, 4, 5]]
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df['close'] = df['close'].astype(float)
    df['EMA20'] = df['close'].ewm(span=20).mean()
    df['EMA50'] = df['close'].ewm(span=50).mean()
    df['MACD'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['Upper'] = df['close'].rolling(window=20).mean() + 2 * df['close'].rolling(window=20).std()
    df['Lower'] = df['close'].rolling(window=20).mean() - 2 * df['close'].rolling(window=20).std()
    return df.iloc[-1]

# === Yardımcı Fonksiyonlar ===
def update_symbol_config(symbol, key, value):
    symbol_config[symbol][key] = value
    with open("symbol_config.json", "w", encoding="utf-8") as f:
        json.dump(symbol_config, f, ensure_ascii=False, indent=4)

def remove_symbol_config_key(symbol, key):
    if key in symbol_config[symbol]:
        del symbol_config[symbol][key]
        with open("symbol_config.json", "w", encoding="utf-8") as f:
            json.dump(symbol_config, f, ensure_ascii=False, indent=4)

# === Karar Ver ===
def rsi_decision(symbol):
    global long_count, short_count
    rsi = get_rsi(client, symbol)
    volatility = get_volatility(symbol)
    tech = get_technical_signals(symbol)
    macd_signal = ""

    if tech['MACD'] > tech['Signal']:
        macd_signal = "LONG"
    elif tech['MACD'] < tech['Signal']:
        macd_signal = "SHORT"

    final_decision = "PASS"
    config = symbol_config.get(symbol, {})
    rsi_buy = config.get("rsi_buy", 35)
    rsi_sell = config.get("rsi_sell", 65)
    min_vol = config.get("min_volatility", 0)

    if volatility < min_vol:
        final_decision = "PASS"
    elif rsi < rsi_buy and macd_signal == "LONG":
        final_decision = "LONG"
        long_count += 1
        send_telegram(f"{symbol} için Long pozisyon")
    elif rsi > rsi_sell and macd_signal == "SHORT":
        final_decision = "SHORT"
        short_count += 1
        send_telegram(f"{symbol} için Short pozisyon")

    log_json({
        "event": "decision",
        "symbol": symbol,
        "rsi": rsi,
        "volatility": volatility,
        "macd": tech['MACD'],
        "macd_signal": tech['Signal'],
        "final_decision": final_decision
    })

    return final_decision

# === Saatlik Rapor ===
def hourly_summary():
    global long_count, short_count, max_trade
    balance = get_usdt_balance()
    send_telegram(f"⏰ Saatlik Özet:\nLong pozisyon: {long_count}\nShort pozisyon: {short_count}\n Bakiye:{balance}\n Toplam Açık Trade:{max_trade}")
    long_count = 0
    short_count = 0

# === JSON'dan Coin ve Parametreleri Yükle ===
def load_symbol_config(path="symbol_config.json"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise FileNotFoundError(f"'{path}' bulunamadı.")

def get_futures_symbols():
    exchange_info = client.futures_exchange_info()
    return [s["symbol"] for s in exchange_info["symbols"] if s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"]

futures_symbols = set(get_futures_symbols())
symbol_config = load_symbol_config()
symbol_list = [s for s in symbol_config.keys() if s in futures_symbols]

for symbol in symbol_list:
    if symbol not in symbol_config:
        symbol_config[symbol] = {}

# === USDT Bakiyesi Al ===
def get_usdt_balance():
    balances = client.futures_account_balance()
    for b in balances:
        if b['asset'] == 'USDT':
            return float(b['balance'])
    raise Exception("USDT bakiyesi bulunamadı.")

# === İşlem Aç ===
def open_position(symbol, side):
    global max_trade
  
    balance = get_usdt_balance()

    leverage = 5
    client.futures_change_leverage(symbol=symbol, leverage=leverage)

    qty = round((balance * 0.2), 2)
    price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
    quantity = round(qty / price, 3)
    order = client.futures_create_order(
        symbol=symbol,
        side=SIDE_BUY if side == "LONG" else SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=quantity
    )
    position_data[symbol] = {
        "side": side,
        "entry_price": price,
        "quantity": quantity
    }
    update_symbol_config(symbol, "entry_price", price)
    max_trade += 1
    send_telegram(f"{symbol} için {side} pozisyon açıldı: {quantity} adet @ {price}")

# === İşlem Kapat ===
def close_position(symbol):
    global max_trade
    if symbol not in position_data:
        return
    info = position_data[symbol]
    side = SIDE_SELL if info["side"] == "LONG" else SIDE_BUY
    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type=ORDER_TYPE_MARKET,
        quantity=info["quantity"]
    )
    current_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
    pnl = (current_price - info["entry_price"]) * info["quantity"]
    pnl = pnl if info["side"] == "LONG" else -pnl
    message = f"{symbol} pozisyon kapatıldı. Kar/Zarar: {round(pnl, 2)} USDT"
    send_telegram(message)
    log_json({
        "event": "position_closed",
        "symbol": symbol,
        "entry_price": info["entry_price"],
        "close_price": current_price,
        "quantity": info["quantity"],
        "pnl": round(pnl, 2),
        "message": message
    })
    del position_data[symbol]
    max_trade -= 1
    remove_symbol_config_key(symbol, "entry_price")

# === Ana Döngü ===
def job():
   if max_trade < 4:
    for symbol in symbol_list:
        try:
            decision = rsi_decision(symbol)
            if symbol not in position_data and decision in ["LONG", "SHORT"]:
                if "entry_price" not in symbol_config.get(symbol, {}):
                    open_position(symbol, decision)
        except Exception as e:
            error_message = f"⚠ Hata oluştu! {symbol} için işlem yapılamadı.\n\nHata: {str(e)}"
            send_telegram(error_message)
            log_json({"event": "error", "symbol": symbol, "error": str(e)})
            traceback.print_exc()


# === Canlı Takip Thread ===
def live_price_monitor():
    while True:
        try:
            for symbol, info in list(position_data.items()):
                current = float(client.futures_symbol_ticker(symbol=symbol)['price'])
                entry = info["entry_price"]
                pnl_pct = ((current - entry) / entry) * 100
                pnl_pct = pnl_pct if info["side"] == "LONG" else -pnl_pct

                if pnl_pct <= -2 or pnl_pct >= 5:
                    close_position(symbol)
        except Exception as e:
            error_message = f"⚠ Canlı fiyat takip hatası! Hata mesajı:\n{traceback.format_exc()}"
            send_telegram(error_message)
            log_json({"event": "live_monitor_error", "error": str(e)})
            traceback.print_exc()
        time.sleep(5)

# === Günlük Kar-Zarar Bildirimi ===
def daily_report():
    total_pnl = 0.0
    if os.path.exists("log.json"):
        with open("log.json", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("event") == "position_closed":
                        total_pnl += entry.get("pnl", 0.0)
                except:
                    continue
    send_telegram(f"Günlük kar/zarar özeti: {round(total_pnl, 2)} USDT")

# === Başlat ===
schedule.every(5).minutes.do(job)
schedule.every().day.at("23:59").do(daily_report)
schedule.every().hour.at(":15").do(hourly_summary)

monitor_thread = threading.Thread(target=live_price_monitor, daemon=True)
monitor_thread.start()

while True:
    schedule.run_pending()
    time.sleep(1)

