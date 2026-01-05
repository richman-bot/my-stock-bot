import yfinance as yf
import pandas as pd
import requests
import os
import time

# --- 1. 從 GitHub Secrets 自動讀取資訊 ---
# 在本地測試時，你可以暫時把 os.getenv 換成 "你的字串"
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# 整合 AI 供應鏈與 6116 的狙擊清單
STOCK_LIST = [
    # --- 你的特別關注標的 ---
    "6116.TW",  # 彩晶：面板題材，1.5萬可買整張
    
    # --- 美股 AI 領頭羊 ---
    "NVDA", "MSFT", "AVGO",
    
    # --- 台股 AI 核心 (買零股) ---
    "2330.TW", "2454.TW", 
    
    # --- 台股 AI 伺服器與散熱 ---
    "2382.TW",  # 廣達
    "2317.TW",  # 鴻海
    "3231.TW",  # 緯創
    "3017.TW",  # 奇鋐
    
    # --- 台股 AI 面板/周邊相關 ---
    "2409.TW",  # 友達 (與彩晶同產業參考)
    "3481.TW"   # 群創
]

def calculate_indicators(df):
    """計算 MACD, KD, 均線指標"""
    # 處理 yfinance 可能產生的多重索引問題
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
    
    # 均線 (5, 20)
    df['MA5'] = close.rolling(window=5).mean()
    df['MA20'] = close.rolling(window=20).mean()
    
    return df

def run_backtest(df, fee=0.001425):
    """回測邏輯：MACD黃金交叉且K>D時持有"""
    df = df.copy()
    df['Position'] = 0
    # 買入條件
    condition = (df['MACD'] > df['Signal_Line']) & (df['K'] > df['D'])
    df.loc[condition, 'Position'] = 1
    
    # 計算報酬 (扣除交易次數產生的手續費)
    df['Trade_Signal'] = df['Position'].diff().abs()
    df['Daily_Return'] = df['Close'].pct_change()
    df['Strategy_Return'] = (df['Daily_Return'] * df['Position'].shift(1)) - (df['Trade_Signal'] * fee)
    
    # 累積報酬
    df['Equity_Curve'] = (1 + df['Strategy_Return'].fillna(0)).cumprod()
    total_profit = (float(df['Equity_Curve'].iloc[-1]) - 1) * 100
    
    # 最大回撤 (MDD)
    mdd = (df['Equity_Curve'] / df['Equity_Curve'].cummax() - 1).min() * 100
    
    # 勝率
    trades = df[df['Strategy_Return'] != 0]
    win_rate = (len(trades[trades['Strategy_Return'] > 0]) / len(trades) * 100) if len(trades) > 0 else 0
    
    return total_profit, win_rate, mdd

def get_analysis_report(ticker):
    """抓取數據並生成單一股票報告"""
    try:
        # 下載過去一年數據
        df = yf.download(ticker, period="1y", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 30:
            return None

        df = calculate_indicators(df)
        profit, win, mdd = run_backtest(df)

        # 獲取最新狀態
        latest = df.iloc[-1]
        price = float(latest['Close'])
        k_val = float(latest['K'])
        macd_val = float(latest['MACD'])
        sig_val = float(latest['Signal_Line'])
        
        # 訊號判斷
        is_buy = (macd_val > sig_val) and (k_val > float(latest['D']))
        
        status = "🟢 *建議買入*" if is_buy else "⚪ 盤整/觀望"
        if k_val > 80: status = "🔥 *短線過熱*"
        elif k_val < 20: status = "❄️ *超跌反彈機會*"

        return (f"📍 *{ticker}* | 價格: {price:.2f}\n"
                f"   訊號: {status} (RSI: {k_val:.1f})\n"
                f"   📊 *回測(含費用): 勝率 {win:.1f}%* | 報酬: {profit:+.1f}%")
    except Exception as e:
        print(f"分析 {ticker} 失敗: {e}")
        return None

def send_to_tg(message):
    """發送訊息至 Telegram"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("錯誤：找不到 TG_TOKEN 或 TG_CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

# --- 3. 執行執行 ---
if __name__ == "__main__":
    print("🚀 啟動自動化掃描...")
    reports = []
    
    for stock in STOCK_LIST:
        res = get_analysis_report(stock)
        if res:
            reports.append(res)
        time.sleep(1) # 稍微延遲避免被鎖 IP

    if reports:
        full_msg = "📊 *GitHub 雲端股市報告*\n指標：MACD + KD + 均線\n" + "="*20 + "\n" + "\n---\n".join(reports)
        send_to_tg(full_msg)
        print("✅ 報告已送出！")
    else:
        print("❌ 未生成任何報告。")
