
import os
import requests
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FINMIND_TOKEN = os.environ.get("FINMIND_API_TOKEN")

STOCK_ID = "00940"
BUY_DATE = "2024-03-29"
BUY_PRICE = 10.0
SHARES = 10000

def fetch_price():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": STOCK_ID,
        "start_date": BUY_DATE,
        "token": FINMIND_TOKEN
    }
    response = requests.get(url, params=params)
    data = response.json()
    if "data" not in data or not data["data"]:
        return None, None
    latest = data["data"][-1]
    return latest["close"], latest["date"]

def fetch_dividend():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockDividend",
        "data_id": STOCK_ID,
        "token": FINMIND_TOKEN
    }
    response = requests.get(url, params=params)
    data = response.json()
    if "data" not in data or not data["data"]:
        return 0
    total_cash = sum([d["cash_dividend"] for d in data["data"] if d["cash_dividend"]])
    return total_cash

def build_report():
    close_price, date = fetch_price()
    if not close_price:
        return "查詢失敗或資料尚未更新"

    holding_days = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(BUY_DATE, "%Y-%m-%d")).days
    price_diff = close_price - BUY_PRICE
    profit = price_diff * SHARES
    return_pct = (price_diff / BUY_PRICE) * 100

    total_dividend = fetch_dividend() * SHARES
    total_with_dividend = profit + total_dividend
    return_with_dividend_pct = (total_with_dividend / (BUY_PRICE * SHARES)) * 100

    msg = f"""
台股每日回報（{date}）

元大台灣價值高息（00940）
- 入手日：{BUY_DATE}（持有 {holding_days} 天）
- 入手價：{BUY_PRICE:.2f} 元
- 現價：{close_price:.2f} 元

不含股利損益：{profit:+,.0f} 元（{return_pct:+.2f}%）
含股利損益：{total_with_dividend:+,.0f} 元（{return_with_dividend_pct:+.2f}%）

持股數量：{SHARES:,} 股
"""
    return msg.strip()

def send_report():
    message = build_report()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)

@app.route("/", methods=["GET"], strict_slashes=False)
def index():
    return "🐷 Telegram 股市回報機器人運行中"

@app.route("/run", methods=["GET", "POST"])
def run():
    try:
        send_report()
        return "報告發送完成"
    except Exception as e:
        return f"錯誤：{str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
