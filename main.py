import os
import sqlite3
import requests
from datetime import date, datetime
from flask import Flask, request, abort
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler

# 環境變數
TOKEN = os.getenv("TELEGRAM_TOKEN")
FINMIND_TOKEN = os.getenv("FINMIND_API_TOKEN")
PORT = int(os.getenv("PORT", "5000"))

bot = Bot(token=TOKEN)
app = Flask(__name__)

# 建資料庫、查價／查息函式同之前
# …（略，沿用之前 main.py 的 fetch_price、fetch_dividends、add_stock、show_portfolio）

# 建立 Dispatcher
dp = Dispatcher(bot, None, workers=0)
dp.add_handler(CommandHandler('add', add_stock))
dp.add_handler(CommandHandler('portfolio', show_portfolio))
dp.add_handler(CommandHandler('start', lambda update, ctx: update.message.reply_text(
    '歡迎使用投資組合查詢機器人！\n使用 /add 和 /portfolio 指令')))

# Flask 接收 webhook 更新
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        dp.process_update(update)
        return "OK"
    else:
        abort(403)

if __name__ == "__main__":
    # 啟動 Flask
    app.run(host="0.0.0.0", port=PORT)
