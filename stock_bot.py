import yfinance as yf
import pandas as pd
import requests
import os
import time
from datetime import datetime
import pytz

# 從 GitHub Secrets 讀取
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# 你的狙擊清單
STOCK_LIST = [
    "6116.TW", "NVDA", "MSFT", "AVGO", "2330.TW", 
    "2454.TW", "2382.TW", "2317.TW", "3231.TW", 
    "3017.TW", "2409.TW", "3481.TW"
]

# --- 僅保留台股中文對照表 ---
CHINESE_NAME_MAP = {
    "6116.TW": "彩晶",
    "2330.TW": "台積電",
    "2454.TW": "聯發科",
    "2382.TW": "廣達",
    "2317.TW": "鴻海",
    "3231.TW": "緯創",
    "3017.TW": "奇鋐",
    "2409.TW": "友達",
    "3481.TW": "群創"
}

def calculate_indicators(df):
    """計算 MACD, KD, 均線指標 (原本邏輯不動)"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    close = df['Close']
    
    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # KD (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # 均線 (用於長線判斷)
    df['MA20'] = close.rolling(window=20).mean()
    
    return df

def run_backtest(df, fee=0.001425):
    """回測邏輯 (原本邏輯不動)"""
    df = df.copy()
    df['Position'] = 0
    condition = (df['MACD'] > df['Signal_Line']) & (df['K'] > df['D'])
    df.loc[condition, 'Position'] = 1
    df['Trade_Signal'] = df['Position'].diff().abs()
    df['Daily_Return'] = df['Close'].pct_change()
    df['Strategy_Return'] = (df['Daily_Return'] * df['Position'].shift(1)) - (df['Trade_Signal'] * fee)
    df['Equity_Curve'] = (1 + df['Strategy_Return'].fillna(0)).cumprod()
    total_profit = (float(df['Equity_Curve'].iloc[-1]) - 1) * 100
    trades = df[df['Strategy_Return'] != 0]
    win_rate = (len(trades[trades['Strategy_Return'] > 0]) / len(trades) * 100) if len(trades) > 0 else 0
    return total_profit, win_rate

def get_analysis_report(ticker):
    """生成單一股票報告 (台股中文名稱、美股代號)"""
    try:
        t = yf.Ticker(ticker)
        
        # --- 修改點：台股用中文，美股維持代號 ---
        name = CHINESE_NAME_MAP.get(ticker, ticker)
        
        df = t.history(period="1y", interval="1d")
        if df.empty or len(df) < 30: return None

        df = calculate_indicators(df)
        profit, win = run_backtest(df)

        latest = df.iloc[-1]
        price = float(latest['Close'])
        k_val = float(latest['K'])
        macd_val = float(latest['MACD'])
        sig_val = float(latest['Signal_Line'])
        ma20 = float(latest['MA20'])
        
        # --- 判斷邏輯 ---
        is_short_buy = (macd_val > sig_val) and (k_val > float(latest['D']))
        # 長線趨勢：股價在月線上，且月線（MA20）趨勢向上
        is_long_trend = (price > ma20) and (ma20 > df['MA20'].iloc[-5]) 

        if is_short_buy and is_long_trend:
            status = "🚀 *強勢噴發 (建議買入)*"
        elif is_short_buy:
            status = "⚡ *短線轉強 (快進快出)*"
        elif is_long_trend:
            status = "📈 *趨勢看多 (長期持有)*"
        else:
            status = "⚪ *盤整觀望*"

        if k_val > 80: status += " 🔥過熱"
        elif k_val < 20: status += " ❄️超跌"

        return (f"🏢 *{name}* ({ticker})\n"
                f"💰 現價: `{price:.2f}` | 建議: {status}\n"
                f"📊 回測勝率: {win:.1f}% | 累積報酬: {profit:+.1f}%")
    except Exception as e:
        print(f"分析 {ticker} 失敗: {e}")
        return None

def send_to_tg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

if __name__ == "__main__":
    reports = []
    for stock in STOCK_LIST:
        res = get_analysis_report(stock)
        if res: reports.append(res)
        time.sleep(1)

    if reports:
        tw_now = datetime.now(pytz.timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')
        full_msg = f"🔍 *RICHROY 獵殺報告* ({tw_now})\n" + "—"*15 + "\n" + "\n\n".join(reports)
        send_to_tg(full_msg)
