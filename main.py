import os
import sqlite3
import requests
from datetime import datetime, date
from flask import Flask, request, abort
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TOKEN        = os.getenv("TELEGRAM_TOKEN")
FINMIND_TOKEN = os.getenv("FINMIND_API_TOKEN")
PORT         = int(os.getenv("PORT", "5000"))
HOSTNAME     = os.getenv("RENDER_EXTERNAL_HOSTNAME")  # Render 自動注入域名

bot = Bot(token=TOKEN)
app = Flask(__name__)

# 資料庫：重建 holdings 表，多了一個 quantity 欄位
conn = sqlite3.connect('stocks.db', check_same_thread=False)
c = conn.cursor()
c.execute('DROP TABLE IF EXISTS holdings')
c.execute('''
CREATE TABLE IF NOT EXISTS holdings (
  chat_id   INTEGER,
  symbol    TEXT,
  price     REAL,
  date      TEXT,
  quantity  INTEGER
)
''')
conn.commit()

# FinMind：取得單日收盤價
def fetch_price(symbol: str, date_str: str = None):
    query_date = date_str or date.today().strftime('%Y-%m-%d')
    resp = requests.get(
        'https://api.finmindtrade.com/api/v4/data',
        params={
            'dataset': 'TaiwanStockPrice',
            'data_id': symbol,
            'start_date': query_date,
            'end_date': query_date,
            'token': FINMIND_TOKEN
        }
    ).json().get('data', [])
    return float(resp[-1]['close']) if resp else None

# FinMind：計算買入日以後累積股利
def fetch_dividends(symbol: str, after: str):
    resp = requests.get(
        'https://api.finmindtrade.com/api/v4/data',
        params={
            'dataset': 'TaiwanStockDividend',
            'data_id': symbol,
            'token': FINMIND_TOKEN
        }
    ).json().get('data', [])
    return sum(float(d.get('dividend', 0)) for d in resp if d['record_date'] >= after)

# /add：新增持股，多一個張數參數
def add_stock(update, context):
    chat_id = update.effective_chat.id
    try:
        symbol, price, buy_date, qty = context.args
        price = float(price)
        qty = int(qty)
        datetime.strptime(buy_date, '%Y-%m-%d')
    except:
        return update.message.reply_text(
            '格式錯誤：/add 股票代號 買入價(數字) 買入日期(YYYY-MM-DD) 張數(整數)'
        )

    c.execute(
        'INSERT INTO holdings VALUES (?, ?, ?, ?, ?)',
        (chat_id, symbol.upper(), price, buy_date, qty)
    )
    conn.commit()
    update.message.reply_text(
        f'已新增：{symbol.upper()} 買入價 {price}，日期 {buy_date}，張數 {qty}'
    )

# /portfolio：顯示持股、乘上張數後的損益
def show_portfolio(update, context):
    chat_id = update.effective_chat.id
    rows = c.execute(
        'SELECT symbol, price, date, quantity FROM holdings WHERE chat_id=?',
        (chat_id,)
    ).fetchall()
    if not rows:
        return update.message.reply_text('目前無持股資料，請先用 /add 指令新增。')

    msgs = []
    total_cost = 0.0
    total_pnl  = 0.0

    for sym, cost, buy_date, qty in rows:
        current = fetch_price(sym)
        divs    = fetch_dividends(sym, buy_date)
        # 假設 1 張 = 1000 股，如果張數即為股數，改成 shares = qty
        shares = qty
        per_share_pnl    = (current - cost) + divs
        pnl_for_symbol   = per_share_pnl * shares
        cost_for_symbol  = cost * shares

        total_pnl  += pnl_for_symbol
        total_cost += cost_for_symbol

        msgs.append(
            f"{sym} ×{qty} 張（{shares} 股）：今收 {current}，"
            f"每股損益 {per_share_pnl:.2f}，"
            f"總損益 {pnl_for_symbol:.2f}"
        )

    overall_pct = (total_pnl / total_cost * 100) if total_cost else 0
    msgs.append(f"\n整體總損益：{total_pnl:.2f} （回報率 {overall_pct:.2f}%）")

    update.message.reply_text("\n".join(msgs))

# 建立 Dispatcher 並註冊指令
dp = Dispatcher(bot, None, use_context=True)
dp.add_handler(CommandHandler('start',
    lambda u, c: u.message.reply_text(
        '歡迎使用投資組合查詢機器人！\n使用 /add 和 /portfolio 指令')))
dp.add_handler(CommandHandler('add', add_stock))
dp.add_handler(CommandHandler('portfolio', show_portfolio))

# Flask 路由：Telegram Webhook 的接收端點
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        dp.process_update(update)
        return "OK"
    else:
        abort(403)

# 啟動時自動設定 webhook（只要 HOSTNAME 有值就執行）
if HOSTNAME:
    webhook_url = f"https://{HOSTNAME}/{TOKEN}"
    bot.delete_webhook()
    bot.set_webhook(url=webhook_url)

if __name__ == "__main__":
    # Flask 監聽 Render 給的 PORT
    app.run(host="0.0.0.0", port=PORT)
