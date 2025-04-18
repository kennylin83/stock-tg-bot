import os
import sqlite3
import requests
from datetime import datetime, date
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TELE_TOKEN = os.getenv('TELEGRAM_TOKEN')
FINMIND_TOKEN = os.getenv('FINMIND_API_TOKEN')

# 建立 SQLite 資料庫
conn = sqlite3.connect('stocks.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS holdings (
        chat_id INTEGER,
        symbol TEXT,
        price REAL,
        date TEXT
    )
''')
conn.commit()

# FinMind 查詢函式
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
    r = requests.get(url, params=params)
    data = r.json().get('data', [])
    return float(data[-1]['close']) if data else None

def fetch_dividends(symbol: str, after: str):
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {
        'dataset': 'TaiwanStockDividend',
        'data_id': symbol,
        'token': FINMIND_TOKEN
    }
    r = requests.get(url, params=params)
    total_div = 0.0
    for d in r.json().get('data', []):
        if d['record_date'] >= after:
            total_div += float(d.get('dividend', 0))
    return total_div

# /add 指令：新增持股
def add_stock(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    try:
        symbol, price, date_str = context.args
        price = float(price)
        datetime.strptime(date_str, '%Y-%m-%d')
    except Exception:
        update.message.reply_text('格式：/add 股票代號 價格(數字) 買入日期(YYYY-MM-DD)')
        return

    c.execute('INSERT INTO holdings VALUES (?, ?, ?, ?)',
              (chat_id, symbol.upper(), price, date_str))
    conn.commit()
    update.message.reply_text(f'已新增：{symbol.upper()} 買入價 {price}，日期 {date_str}')

# /portfolio 指令：顯示當前持股狀況
def show_portfolio(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    rows = c.execute('SELECT symbol, price, date FROM holdings WHERE chat_id=?', (chat_id,)).fetchall()
    if not rows:
        update.message.reply_text('目前無持股資料，使用 /add 新增。')
        return

    msg = []
    total_pnl = 0.0
    total_cost = 0.0
    for sym, cost, buy_date in rows:
        current = fetch_price(sym)
        divs = fetch_dividends(sym, buy_date)
        pnl = (current - cost) + divs
        total_pnl += pnl
        total_cost += cost
        msg.append(f"{sym}: 今收 {current}，含息損益 {pnl:.2f} (不含息 {current - cost:.2f})")

    total_pct = total_pnl / total_cost * 100 if total_cost else 0
    msg.append(f"\n總損益：{total_pnl:.2f} (約 {total_pct:.2f}% )")
    update.message.reply_text("\n".join(msg))

# 主程式
def main():
    updater = Updater(TELE_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('add', add_stock))
    dp.add_handler(CommandHandler('portfolio', show_portfolio))
    dp.add_handler(CommandHandler('start', lambda u, c: u.message.reply_text(
        '歡迎使用投資組合查詢機器人！\n使用 /add 和 /portfolio 指令')))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
