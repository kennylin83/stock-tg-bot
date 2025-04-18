import os
import sqlite3
import requests
from datetime import datetime, date
from flask import Flask, request, abort
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler
from dotenv import load_dotenv

# 載入 .env 與環境變數
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
FINMIND_TOKEN = os.getenv("FINMIND_API_TOKEN")
PORT = int(os.getenv("PORT", "5000"))
# RENDER_EXTERNAL_HOSTNAME 是 Render 自動注入的 domain
HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

bot = Bot(token=TOKEN)
app = Flask(__name__)

# SQLite 資料庫初始化
conn = sqlite3.connect('stocks.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS holdings (
  chat_id INTEGER,
  symbol  TEXT,
  price   REAL,
  date    TEXT
)
''')
conn.commit()

# FinMind 收盤價函式
def fetch_price(symbol: str, date_str: str = None):
    query_date = date_str or date.today().strftime('%Y-%m-%d')
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {
        'dataset': 'TaiwanStockPrice',
        'data_id': symbol,
        'start_date': query_date,
        'end_date': query_date,
        'token': FINMIND_TOKEN
    }
    data = requests.get(url, params=params).json().get('data', [])
    return float(data[-1]['close']) if data else None

# FinMind 股利函式
def fetch_dividends(symbol: str, after: str):
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {
        'dataset': 'TaiwanStockDividend',
        'data_id': symbol,
        'token': FINMIND_TOKEN
    }
    data = requests.get(url, params=params).json().get('data', [])
    return sum(float(d.get('dividend', 0)) for d in data if d['record_date'] >= after)

# /add 指令：新增持股
def add_stock(update, context):
    chat_id = update.effective_chat.id
    try:
        symbol, price, buy_date = context.args
        price = float(price)
        datetime.strptime(buy_date, '%Y-%m-%d')
    except:
        return update.message.reply_text(
            '格式錯誤：/add 股票代號 價格(數字) 買入日期(YYYY-MM-DD)'
        )
    c.execute(
        'INSERT INTO holdings VALUES (?, ?, ?, ?)',
        (chat_id, symbol.upper(), price, buy_date)
    )
    conn.commit()
    update.message.reply_text(f'已新增：{symbol.upper()} 買入價 {price}，日期 {buy_date}')

# /portfolio 指令：顯示持股損益
def show_portfolio(update, context):
    chat_id = update.effective_chat.id
    rows = c.execute(
        'SELECT symbol, price, date FROM holdings WHERE chat_id=?',
        (chat_id,)
    ).fetchall()
    if not rows:
        return update.message.reply_text('目前無持股資料，請先用 /add 新增。')

    msgs = []
    total_cost = 0.0
    total_pnl = 0.0
    for sym, cost, buy_date in rows:
        current = fetch_price(sym)
        divs = fetch_dividends(sym, buy_date)
        pnl = (current - cost) + divs
        total_cost += cost
        total_pnl += pnl
        msgs.append(
            f"{sym}: 今收 {current}，含息損益 {pnl:.2f} (不含息 {current-cost:.2f})"
        )
    pct = (total_pnl / total_cost * 100) if total_cost else 0
    msgs.append(f"\n總損益：{total_pnl:.2f} （約 {pct:.2f}%）")
    update.message.reply_text("\n".join(msgs))

# 建立 Dispatcher 並註冊 handlers
dp = Dispatcher(bot, None, use_context=True)
dp.add_handler(CommandHandler('start',
    lambda u, c: u.message.reply_text(
        '歡迎使用投資組合查詢機器人！\n使用 /add 和 /portfolio 指令')))
dp.add_handler(CommandHandler('add', add_stock))
dp.add_handler(CommandHandler('portfolio', show_portfolio))

# Flask 路由：接收 Telegram Webhook
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        dp.process_update(update)
        return "OK"
    else:
        abort(403)

# 部署時自動設定 Webhook
if HOSTNAME:
    webhook_url = f"https://{HOSTNAME}/{TOKEN}"
    bot.delete_webhook()
    bot.set_webhook(url=webhook_url)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
