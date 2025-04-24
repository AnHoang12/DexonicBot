import os
import json
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Load Database credentials
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# Load supported coins
with open("supported_coins.json", "r") as file:
    data = json.load(file)
    support_coins = set(data['supported_coins'])  

class ChatBot:
    def __init__(self, api_key, client):
        self.api_key = api_key
        self.client = client

    def classify_user_intent(self, user_query):
        """ Xác định ý định của người dùng """
        completion = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """ 
                        You are an AI assistant for Vistia, a platform that delivers real-time AI-powered signals about the cryptocurrency market.
                        When a user asks a question unrelated to trading or the crypto market, respond politely to their inquiry while kindly reminding them that the topic isn't connected to trading or crypto.
                        Always maintain a helpful and courteous tone.

                        If the user's query give details information about a specific coin, you should give only the information below: 
                            - symbol

                        Below are examples of question answers 
                            "What is the price of bitcoin?", you should answer "BTC" not "BTC." or "BTC is $50,000".
                            "Should I buy Ethereum now?", you should answer "ETH" not "eth" or "ETH is $3,000".
                            "What is the price of Bitcoin and Algorand?", you should answer "BTC, ALGO". not "BTC and ALGO" or "BTC and ALGO are $50,000 and $1.00".
                            "How is the market today?", you should answer "all" not "all coins" or "All."
                        
                        You should not provide any other information than the symbol of the coin.
                    """
                },
                {
                    "role": "user",
                    "content": user_query,
                },
            ]
        )
        return completion.choices[0].message.content.strip()

    def fetch_real_time_data(self, db: Session, coins_list):
        """ Lấy dữ liệu 14 phiên gần nhất của coin từ database """
        table = "proddb.f_coin_signal_1h"
        real_time_data = ""

        try:
            for coin in coins_list:
                query = f"SELECT * FROM {table} WHERE symbol = '{coin}' ORDER BY open_time DESC LIMIT 14"
                result = db.execute(text(query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                real_time_data += f"\n\n{coin}:\n"
                real_time_data += df.to_string(index=False)
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None
        return real_time_data

    def generate_detailed_response(self, user_query, db: Session):
        """ Phân tích kỹ thuật và đưa ra phản hồi """
        classification = self.classify_user_intent(user_query)

        if len(classification) > 15:  
            return classification

        coins_list = []
        coins_str = []
        classification = classification.upper()

        if "all" in classification.lower():
            coins_list = ["XRPUSDT"]
            coins_str = "XRP"
        else:
            coins_list = [coin.strip() + "USDT" for coin in classification.split(",")]
            coins_str = classification

        not_supported = set(coins_list) - set(support_coins)
        if not_supported:
            not_supported_string = ", ".join(not_supported)
            return f"Sorry, I don't have information on the following coins: {not_supported_string}. Check the '/list_coin' command for supported coins."

        real_time_data = self.fetch_real_time_data(db, coins_list)
        if not real_time_data:
            return "I couldn't retrieve market data at this time."

        sys_prompt = f""" 
            You are an AI providing technical analysis on cryptocurrency. 
            Provide an analysis of the current market situation for {coins_str}. Include short-term trends, and key technical indicators.
            Is the symbol currently in a buying range, or should the user wait for a better entry point? Please provide an analysis based on the technical indicators provided, such as moving averages, RSI, and support/resistance levels.
            You should answer me in raw text format. The markdown format is not allowed.
            Based on the following real-time data interval 1 day for the symbol with the open_time in GMT+7 timezone: \n
            You have powerful knowledge about Cardano and ADA tokens. If the question about "what is Cardano", you should share your knowledge aout it. 
            Response MUST be in 4-5 lines. 
        """
        sys_prompt += real_time_data

        completion = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_query}
            ]
        )

        return completion.choices[0].message.content.strip()


