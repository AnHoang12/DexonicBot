import os
import pandas as pd
import asyncio
from telegram.ext import Application
from dotenv import load_dotenv
from tradebot import TradeBot  
from datetime import datetime
from sqlalchemy import create_engine
from openai import OpenAI
from ChatBot import ChatBot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram import Update

load_dotenv()

#Get OpenAPI Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)
chatbot = ChatBot(OPENAI_API_KEY, openai_client)

# Get Telegram token
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
trade_bot = TradeBot(TOKEN, CHANNEL_ID)

# Get Database information
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

SYMBOL = "ADAUSDT"

# SQL query for historical data 
HISTORICAL_QUERY = f"""
SELECT * FROM f_coin_signal_1h 
WHERE symbol = '{SYMBOL}' 
AND open_time > (UNIX_TIMESTAMP(now()) - 2592000)  -- Last 30 days 
ORDER BY open_time ASC;
"""

# SQL query for recent data 
RECENT_QUERY = f"""
SELECT * FROM f_coin_signal_1h 
WHERE symbol = '{SYMBOL}' 
AND open_time > (UNIX_TIMESTAMP(now()) - 86400)  -- Last 24 hours
ORDER BY open_time DESC 
LIMIT 10;
"""

def calculate_historical_win_rates():

    try:
        print("Calculating historical win rates...")
        df = pd.read_sql(HISTORICAL_QUERY, engine)
        
        if df.empty:
            print("No historical data found!")
            return
            
        print(f"Loaded {len(df)} historical candles for {SYMBOL}")
        
        results = trade_bot.analyze_historical_performance(df)
        
        trade_bot.outside_bar_results = results['Outside Bar']
        trade_bot.fourth_signal_results = results['Fourth Signal']
        
        outside_win_rates = results['Outside Bar']['win_rates']
        outside_total = results['Outside Bar']['total_signals']
        print(f"Outside Bar Win Rates ({outside_total} signals):")
        print(f"- 1 Candle: {outside_win_rates.get(1, 0):.2%}")
        print(f"- 2 Candles: {outside_win_rates.get(2, 0):.2%}")
        print(f"- 4 Candles: {outside_win_rates.get(4, 0):.2%}")
        print(f"- 6 Candles: {outside_win_rates.get(6, 0):.2%}")
        
        fourth_win_rates = results['Fourth Signal']['win_rates']
        fourth_total = results['Fourth Signal']['total_signals']
        print(f"Fourth Signal Win Rates ({fourth_total} signals):")
        print(f"- 1 Candle: {fourth_win_rates.get(1, 0):.2%}")
        print(f"- 2 Candles: {fourth_win_rates.get(2, 0):.2%}")
        print(f"- 4 Candles: {fourth_win_rates.get(4, 0):.2%}")
        print(f"- 6 Candles: {fourth_win_rates.get(6, 0):.2%}")
        
    except Exception as e:
        print(f"Error calculating historical win rates: {e}")

async def check_signals(context):

    try:
        calculate_historical_win_rates()
        
        df = pd.read_sql(RECENT_QUERY, engine)
        now = datetime.now()
        formatted_time = now.strftime("%d/%m/%Y %I:%M %p")
        print(f"Checking data at: {formatted_time}")
        
        if len(df) < 3:  
            print("Not enough data!")
            return
            
        outside_signal, candle = trade_bot.detect_outside_bar(df)
        if outside_signal:
            print(f"{outside_signal} Outside Bar Signal DETECTED at {candle['open_time']}!")
            await trade_bot.send_trade_signal(outside_signal, candle, "Outside Bar")
        
        fourth_signal, fourth_candle, order_type = trade_bot.detect_fourth_signal(df)
        if fourth_signal:
            print(f"{fourth_signal} DETECTED at {fourth_candle['open_time']}!")
            await trade_bot.send_trade_signal(fourth_signal, fourth_candle, "Fourth Signal")
            
        if not outside_signal and not fourth_signal:
            print("No signals detected.")
            
    except Exception as e:
        print(f"Error checking signals: {e}")

async def start(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    welcome_message = """
Welcome to DexonicBot! 👋

I can help you with:
- Real-time crypto market analysis
- Technical indicators and trade signals
- Market trends and recommendations

Try asking me about a specific coin like:
"How is ADA looking today?"
"What's your analysis on ADA?"

    """
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context: CallbackContext):
  
    user_message = update.message.text
    user_id = update.effective_user.id
    
    print(f"Received message from {user_id}: {user_message}")
    
    with engine.connect() as connection:
        response = chatbot.generate_detailed_response(user_message, connection)
        
        await update.message.reply_text(response)

def main():
    
    
    # Create the application
    application = Application.builder().token(TOKEN).build()
    
    job_queue = application.job_queue
    job_queue.run_repeating(check_signals, interval=3600, first=5)  

    application.add_handler(CommandHandler("start", start))
    # application.add_handler(CommandHandler("list_coin", list_coin))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print(f"Bot started! Monitoring {SYMBOL} for trade signals, calculating win rates for 1, 2, 4, and 6 candles...")
    print(f"Bot will recalculate every hour.")
    
    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
