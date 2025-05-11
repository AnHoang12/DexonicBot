import asyncio
import json
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from openai import OpenAI
import os
from dotenv import load_dotenv
import re
import tweepy
import ast
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import time

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

openai_key = os.getenv("OPENAI_API_KEY")  
openai_client = OpenAI(api_key=openai_key)

def insert_table_signal(symbol, timeframe, signal, score):
    unix_time = int(time.time())
    insert_sql = text(f"""
        INSERT INTO test.tmp_signal_scores (symbol, update_time, timeframe, `signal`, score)
        VALUES ('{symbol}', {unix_time}, '{timeframe}', '{signal}', {score})
    """)
    print(insert_sql)
    with engine.begin() as conn:
        conn.execute(insert_sql)
        print(f" Inserted into DB: {symbol}, {signal}, {score}")


class SentimentAnalyzer:
    def __init__(self, user_id="test_user"):
        self.user_id = user_id 
        self.trends = {}

    async def scrape_web_sentiment(self, token):
        url = f"https://cointelegraph.com/search?query={token}"
        print(f"start {token}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=15000)
                await page.wait_for_selector("h2:has(a)", timeout=10000)

                article_links = await page.locator("h2:has(a) a").evaluate_all(
                    "(els) => els.map(e => e.href)"
                )
                await browser.close()

            article_links = article_links[:5]
            articles = []

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                for link in article_links:
                    try:
                        await page.goto(link, timeout=15000)
                        await page.wait_for_selector("h1", timeout=10000)
                        title = await page.locator("h1").text_content()
                        paragraphs = await page.locator("article p").all_text_contents()
                        top_content = "\n".join(paragraphs[:5])
                        articles.append(f"{title}\n{top_content}")
                    except Exception as inner_e:
                        print(f"Skip one article due to error: {inner_e}")
                        continue
                await browser.close()

            print("Fetched articles:", articles)
            if not articles:
                return 0.0
            messages = [
                {
                    "role": "system",
                    "content": 
                        """
                        Analyze sentiment of these article titles. Score -5 (negative) to 5 (positive). 
                        Score each article with a number. 
                        Return a list of score only. Example: [0, 1, 2, 3, 4].
                        """
                    },
                {"role": "user", "content": "\n".join(articles)}
            ]
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            raw_output = response.choices[0].message.content.strip()
            print(raw_output)
            try:
                scores = ast.literal_eval(raw_output)
                sentiment_score = sum(scores) / len(scores)
            except Exception as e:
                # fallback nếu fail
                # scores = [int(s) for s in re.findall(r'-?\d+', raw_output)]
                # sentiment_score = sum(scores) / len(scores)
                print("error")
            print(scores)
            if not scores:
                sentiment_score = 0
            else:
                sentiment_score = sum(scores) 

            self.trends["market"] = sentiment_score / 5
            logging.info(json.dumps({
                "event": "web_sentiment",
                "user_id": self.user_id,
                "token": token,
                "score": sentiment_score
            }))
            return sentiment_score 
        except Exception as e:
            logging.error(json.dumps({
                "event": "web_sentiment_failed",
                "user_id": self.user_id,
                "token": token,
                "error": str(e)
            }))
            return 0.0
        
    async def scrape_x_sentiment(self, token):
        try:
            bearer_token = os.getenv("X_BEARER_TOKEN")
            if not bearer_token:
                raise Exception("Missing X_BEARER_TOKEN")

            client = tweepy.Client(bearer_token=bearer_token)
            query = f"{token} lang:en -is:retweet"

            result = client.search_recent_tweets(query=query, max_results=10)
            tweets = [tweet.text for tweet in result.data] if result.data else []
            print(tweets)
            if not tweets:
                return 0

            messages = [
                {
                    "role": "system", 
                    "content": 
                        """
                        Analyze sentiment of these X posts. 
                        Score -5 (very negative) to 5 (very positive). 
                        Only return the number. Example: [0, 1, 2, 3, 4].
                        """
                        },
                {"role": "user", "content": "\n".join(tweets)}
            ]

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            raw_output = response.choices[0].message.content.strip()
            scores = [int(s) for s in re.findall(r'-?\d+', raw_output)]
            print(scores)
            if not scores:
                sentiment_score = 0
            else:
                sentiment_score = sum(scores)
            self.trends["social"] = sentiment_score / 5

            logging.info(json.dumps({
                "event": "x_sentiment",
                "user_id": self.user_id,
                "token": token,
                "score": sentiment_score
            }))
            return sentiment_score 

        except Exception as e:
            logging.error(json.dumps({
                "event": "x_sentiment_failed",
                "user_id": self.user_id,
                "token": token,
                "error": str(e)
            }))
            return 0

async def main():
    analyzer = SentimentAnalyzer()
    token = "CARDANO"
    score = await analyzer.scrape_web_sentiment(token)
    insert_table_signal(f"{token}USDT", "all", "social", score)

    x_score = await analyzer.scrape_x_sentiment(token)
    print(f"X Sentiment (Twitter): {x_score:.2f}")

if __name__ == "__main__":
    asyncio.run(main())
