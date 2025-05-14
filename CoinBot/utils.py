from binance.client import Client
from binance.enums import *
import pandas as pd
import ta

def get_rsi(client, symbol, interval="15m", limit=100):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=['timestamp','o','h','l','c','v','1','2','3','4','5','6'])
    df['c'] = df['c'].astype(float)
    rsi = ta.momentum.RSIIndicator(pd.Series(df['c']), window=14)
    return rsi.rsi().iloc[-1]
