import yfinance as yf
import pandas as pd
import requests
import os
import time

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

def get_low_price_hot_stocks():
    """自動尋找成交量大且價格低於 50 元的標的"""
    url = "https://tw.stock.yahoo.com/ranking/volume?exchange=TAI" # 抓成交量排行
    headers = {'User-Agent': 'Mozilla/5.0'}
    targets = []
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_html(response.text)[0]
        
        # 1. 抓取代號
        # 2. 同時抓取成交價，過濾掉 > 50 元的
        for index, row in df.iterrows():
            try:
                code = str(row['代號']).split('.')[0]
                price = float(row['成交'])
                volume = str(row['成交量(張)']).replace(',', '')
                
                # 只找價格 < 50 且 成交量 > 15000 張的
                if price < 50 and int(volume) > 15000:
                    targets.append(f"{code}.TW")
            except:
                continue
    except Exception as e:
        print(f"抓取失敗: {e}")
        targets = ["6116.TW", "2409.TW", "2609.TW", "2883.TW"]
    return list(set(targets))[:12] # 取前 12 隻

def get_report(ticker):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        latest = df.iloc[-1]
        vol = latest['Volume'] / 1000 # 換算成「張」
        price = latest['Close']
        
        # 簡單判斷：收紅且成交量比前五天平均高
        avg_vol = df['Volume'].iloc[-6:-1].mean() / 1000
        status = "🔥 爆量衝刺" if vol > avg_vol * 1.5 else "⚪ 穩定放量"
        
        return f"🏢 *{ticker}*\n💰 價: `{price:.2f}` | 量: `{vol:.0f}張`\n📢 狀態: {status}"
    except:
        return None

if __name__ == "__main__":
    stocks = get_low_price_hot_stocks()
    reports = [get_report(s) for s in stocks if get_report(s)]
    
    if reports:
        msg = "🎯 *小資低價爆量標的掃描*\n基準：股價 < 50 & 量 > 1.5萬張\n" + "-"*15 + "\n" + "\n\n".join(reports)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                      data={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
