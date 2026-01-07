import yfinance as yf
import pandas as pd
import requests
import os
import time
from datetime import datetime
import pytz

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# 核心追蹤（就算排行榜沒出現也要跑）
CORE_LIST = ["2330.TW", "NVDA", "TSLA"]

def get_trending_stocks():
    """自動從 Yahoo 財經抓取台股成交值排行榜前 10 名"""
    url = "https://tw.stock.yahoo.com/ranking/value?exchange=TAI"
    headers = {'User-Agent': 'Mozilla/5.0'}
    trending = []
    try:
        response = requests.get(url, headers=headers)
        dfs = pd.read_html(response.text)
        df = dfs[0]
        # 抓取代號列，並轉換為 .TW 格式
        codes = df['代號'].astype(str).str.extract(r'(\d+)')[0].dropna().tolist()
        for code in codes[:10]:
            trending.append(f"{code}.TW")
    except Exception as e:
        print(f"動態抓取失敗: {e}")
        trending = ["2317.TW", "1513.TW", "2359.TW", "3231.TW", "2603.TW"]
    return list(set(CORE_LIST + trending))

def calculate_indicators(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df['Close']
    ema12, ema26 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    low_min, high_max = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    df['K'] = rsv.ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    df['MA20'] = close.rolling(20).mean()
    return df

def get_report(ticker):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="1y", interval="1d")
        if df.empty or len(df) < 30: return None
        df = calculate_indicators(df)
        latest = df.iloc[-1]
        price, k, macd, sig, ma20 = latest['Close'], latest['K'], latest['MACD'], latest['Signal'], latest['MA20']
        
        # 爆量判斷
        vol_avg = df['Volume'].iloc[-6:-1].mean()
        is_vol_spike = "🔥爆量" if latest['Volume'] > vol_avg * 1.5 else ""
        
        # 建議邏輯
        status = "⚪ 觀望"
        if macd > sig and k > latest['D']:
            status = "🚀 強勢" if price > ma20 else "⚡ 短多"
        elif price > ma20:
            status = "📈 持有"
            
        return f"🏢 *{ticker}* {is_vol_spike}\n💰 價: `{price:.2f}` | {status} | K:{k:.1f}"
    except: return None

if __name__ == "__main__":
    stocks = get_trending_stocks()
    reports = [get_report(s) for s in stocks if get_report(s)]
    if reports:
        tw_now = datetime.now(pytz.timezone('Asia/Taipei')).strftime('%m/%d %H:%M')
        msg = f"🔥 *今日大流量獵殺報告* ({tw_now})\n" + "\n\n".join(reports)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                      data={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
