# tradebot_v2.py
import numpy as np
import pandas as pd
import asyncio
from telegram import Bot
from datetime import datetime

class TradeBot:
    def __init__(self, telegram_token, chat_id):
        self.bot = Bot(token=telegram_token)
        self.chat_id = chat_id
        self.outside_bar_results = {'win_rates': {}, 'total_signals': 0, 'signals': pd.DataFrame()}
        self.fourth_signal_results = {'win_rates': {}, 'total_signals': 0, 'signals': pd.DataFrame()}
        
    def detect_outside_bar(self, df):
        """ Detect Outside Bar signal and determine BUY/SELL """
        if len(df) < 2:
            return None, None
            
        prev_candle = df.iloc[-2]
        current_candle = df.iloc[-1]
        
        is_outside_bar = (current_candle["high"] > prev_candle["high"]) and \
                         (current_candle["low"] < prev_candle["low"])
                         
        if is_outside_bar:
            if (current_candle["close"] > current_candle["open"]) and (prev_candle["close"] < prev_candle["open"]):
                return "BULLISH", current_candle  # Bullish Outside Bar -> BUY
            elif (current_candle["close"] < current_candle["open"]) and (prev_candle["close"] > prev_candle["open"]):
                return "BEARISH", current_candle  # Bearish Outside Bar -> SELL
                
        return None, None
        
    def detect_fourth_signal(self, df):
        """ Detect fourth signal and wash-out signal """
        if len(df) < 3:
            return None, None, None
            
        candle3 = df.iloc[-3]
        candle2 = df.iloc[-2]
        candle1 = df.iloc[-1]
        
        all_green = (
            candle1["open"] < candle1["close"] and
            candle2["open"] < candle2["close"] and
            candle3["open"] < candle3["close"]
        )
        
        all_rsi_above = (
            candle1["rsi7"] > 70 and
            candle2["rsi7"] > 70 and
            candle3["rsi7"] > 70
        )
        
        all_red = (
            candle1["open"] > candle1["close"] and
            candle2["open"] > candle2["close"] and
            candle3["open"] > candle3["close"]
        )
        
        all_rsi_below = (
            candle1["rsi7"] < 30 and
            candle2["rsi7"] < 30 and
            candle3["rsi7"] < 30
        )
        
        if all_green and all_rsi_above:
            return "Fourth Distribution Signal", candle1, "SELL"
        if all_red and all_rsi_below:
            return "Wash-out Signal", candle1, "BUY"
            
        return None, None, None
    
    def collect_outside_bar_signals(self, df):
        """Collect all outside bar signals from historical data with profits after 1, 2, 4, and 6 candles"""
        signals = []
        
        for i in range(1, len(df) - 6):
            prev_candle = df.iloc[i-1]
            current_candle = df.iloc[i]
            
            # Get future candles for profit calculation
            next_candle_1 = df.iloc[i+1]
            next_candle_2 = df.iloc[i+2]
            next_candle_4 = df.iloc[i+4]
            next_candle_6 = df.iloc[i+6]
            
            is_outside_bar = (current_candle["high"] > prev_candle["high"]) and \
                             (current_candle["low"] < prev_candle["low"])
                             
            if is_outside_bar:
                signal_data = {
                    "time": current_candle["open_time"],
                    "symbol": current_candle["symbol"],
                    "entry_price": next_candle_1["open"],  # Entry price is next candle's open
                    "signal_type": "Outside Bar"
                }
                
                if (current_candle["close"] > current_candle["open"]) and (prev_candle["close"] < prev_candle["open"]):
                    signal_data["order"] = "BUY"
                    # Calculate profits for different exit times
                    signal_data["exit_price_1"] = next_candle_1["close"]
                    signal_data["exit_price_2"] = next_candle_2["close"]
                    signal_data["exit_price_4"] = next_candle_4["close"]
                    signal_data["exit_price_6"] = next_candle_6["close"]
                    
                    # Calculate profit percentages for BUY
                    signal_data["profit_1"] = (next_candle_1["close"] - next_candle_1["open"]) / next_candle_1["open"] * 100
                    signal_data["profit_2"] = (next_candle_2["close"] - next_candle_1["open"]) / next_candle_1["open"] * 100
                    signal_data["profit_4"] = (next_candle_4["close"] - next_candle_1["open"]) / next_candle_1["open"] * 100
                    signal_data["profit_6"] = (next_candle_6["close"] - next_candle_1["open"]) / next_candle_1["open"] * 100
                    
                    signals.append(signal_data)
                    
                elif (current_candle["close"] < current_candle["open"]) and (prev_candle["close"] > prev_candle["open"]):
                    signal_data["order"] = "SELL"
                    # Calculate profits for different exit times
                    signal_data["exit_price_1"] = next_candle_1["close"]
                    signal_data["exit_price_2"] = next_candle_2["close"]
                    signal_data["exit_price_4"] = next_candle_4["close"]
                    signal_data["exit_price_6"] = next_candle_6["close"]
                    
                    # Calculate profit percentages for SELL
                    signal_data["profit_1"] = (next_candle_1["open"] - next_candle_1["close"]) / next_candle_1["open"] * 100
                    signal_data["profit_2"] = (next_candle_1["open"] - next_candle_2["close"]) / next_candle_1["open"] * 100
                    signal_data["profit_4"] = (next_candle_1["open"] - next_candle_4["close"]) / next_candle_1["open"] * 100
                    signal_data["profit_6"] = (next_candle_1["open"] - next_candle_6["close"]) / next_candle_1["open"] * 100
                    
                    signals.append(signal_data)
        
        return pd.DataFrame(signals) if signals else pd.DataFrame()
    
    def collect_fourth_signals(self, df):
        """Collect all fourth signals from historical data with profits after 1, 2, 4, and 6 candles"""
        signals = []

        for i in range(3, len(df) - 6):  
            candle3 = df.iloc[i-3]
            candle2 = df.iloc[i-2]
            candle1 = df.iloc[i-1]
            signal_candle = df.iloc[i]
            
            # Get future candles for profit calculation
            next_candle_1 = df.iloc[i+1]
            next_candle_2 = df.iloc[i+2]
            next_candle_4 = df.iloc[i+4]
            next_candle_6 = df.iloc[i+6]
            
            all_green = (
                candle1["open"] < candle1["close"] and
                candle2["open"] < candle2["close"] and
                candle3["open"] < candle3["close"]
            )
            
            all_rsi_above = (
                candle1["rsi7"] > 70 and
                candle2["rsi7"] > 70 and
                candle3["rsi7"] > 70 
            )
            
            all_red = (
                candle1["open"] > candle1["close"] and
                candle2["open"] > candle2["close"] and
                candle3["open"] > candle3["close"]
            )
            
            all_rsi_below = (
                candle1["rsi7"] < 30 and
                candle2["rsi7"] < 30 and
                candle3["rsi7"] < 30
            )

            signal_data = {
                "time": signal_candle["open_time"],
                "symbol": signal_candle["symbol"],
                "entry_price": signal_candle["open"],
                "exit_price_1": next_candle_1["close"],
                "exit_price_2": next_candle_2["close"],
                "exit_price_4": next_candle_4["close"],
                "exit_price_6": next_candle_6["close"],
            }

            if all_green and all_rsi_above:
                signal_data["order"] = "SELL"
                signal_data["signal_type"] = "Fourth Distribution"
                
                # Calculate profit percentages for SELL
                signal_data["profit_1"] = (signal_candle["open"] - next_candle_1["close"]) / signal_candle["open"] * 100
                signal_data["profit_2"] = (signal_candle["open"] - next_candle_2["close"]) / signal_candle["open"] * 100
                signal_data["profit_4"] = (signal_candle["open"] - next_candle_4["close"]) / signal_candle["open"] * 100
                signal_data["profit_6"] = (signal_candle["open"] - next_candle_6["close"]) / signal_candle["open"] * 100
                
                signals.append(signal_data)
                
            if all_red and all_rsi_below:
                signal_data["order"] = "BUY"
                signal_data["signal_type"] = "Wash-out"
                
                # Calculate profit percentages for BUY
                signal_data["profit_1"] = (next_candle_1["close"] - signal_candle["open"]) / signal_candle["open"] * 100
                signal_data["profit_2"] = (next_candle_2["close"] - signal_candle["open"]) / signal_candle["open"] * 100
                signal_data["profit_4"] = (next_candle_4["close"] - signal_candle["open"]) / signal_candle["open"] * 100
                signal_data["profit_6"] = (next_candle_6["close"] - signal_candle["open"]) / signal_candle["open"] * 100
                
                signals.append(signal_data)

        return pd.DataFrame(signals) if signals else pd.DataFrame()
    
    def calculate_win_rates_by_candle(self, signals_df):
        """Calculate win rates for each candle timeframe (1, 2, 4, 6)"""
        if signals_df.empty:
            return {1: 0, 2: 0, 4: 0, 6: 0}, 0
            
        total_trades = len(signals_df)
        win_rates = {}
        
        # Calculate win rate for each timeframe
        for candle_num in [1, 2, 4, 6]:
            profit_col = f"profit_{candle_num}"
            profitable_trades = (signals_df[profit_col] > 0).sum()
            win_rates[candle_num] = profitable_trades / total_trades if total_trades > 0 else 0
            
        return win_rates, total_trades
    
    def analyze_historical_performance(self, df):
        """Analyze historical performance of both strategies with multiple timeframes"""
        # Make sure datetime is proper format
        if isinstance(df['open_time'].iloc[0], (int, float)):
            df['open_time'] = pd.to_datetime(df['open_time'], unit='s')
        
        # Collect signals
        outside_signals = self.collect_outside_bar_signals(df)
        fourth_signals = self.collect_fourth_signals(df)
        
        # Calculate win rates for each timeframe
        outside_win_rates, outside_total = self.calculate_win_rates_by_candle(outside_signals)
        fourth_win_rates, fourth_total = self.calculate_win_rates_by_candle(fourth_signals)
        
        return {
            'Outside Bar': {
                'win_rates': outside_win_rates,
                'total_signals': outside_total,
                'signals': outside_signals
            },
            'Fourth Signal': {
                'win_rates': fourth_win_rates,
                'total_signals': fourth_total,
                'signals': fourth_signals
            }
        }
    
    async def send_trade_signal(self, action, candle, signal_type=None):
        """Send trade signal via Telegram with win rate information for different timeframes"""
        if action:
            # Determine order type
            order_type = None
            if action == "BULLISH" or action == "Wash-out Signal":
                order_type = "BUY"
            elif action == "BEARISH" or action == "Fourth Distribution Signal":
                order_type = "SELL"
            
            message = (
                f"Token: {candle['symbol']}\n"
                f"{action} Signal Detected!\n"
            )
            
            message += (
                f"Order: {order_type}\n"
                f"Open Price: ${candle['open']}\n"
                f"Close Price: ${candle['close']}\n"
                f"Entry Price: ${candle['close']}\n"
                f"Time: {datetime.fromtimestamp(candle['open_time'])}\n"
                "Swap here: [Minswap](https://minswap.org)"
                "***"
            )

            if signal_type == "Outside Bar":
                win_rates = self.outside_bar_results.get('win_rates', {})
                message += "Historical Win Rates of Last 30 days:\n"
                message += f"- 1 Session: {win_rates.get(1, 0):.2%}\n"
                message += f"- 2 Sessions: {win_rates.get(2, 0):.2%}\n"
                message += f"- 4 Sessions: {win_rates.get(4, 0):.2%}\n"
                message += f"- 6 Sessions: {win_rates.get(6, 0):.2%}\n"
            elif signal_type == "Fourth Signal":
                win_rates = self.fourth_signal_results.get('win_rates', {})
                message += "Historical Win Rates of Last 30 days:\n"
                message += f"- 1 Session: {win_rates.get(1, 0):.2%}\n"
                message += f"- 2 Sessions: {win_rates.get(2, 0):.2%}\n"
                message += f"- 4 Sessions: {win_rates.get(4, 0):.2%}\n"
                message += f"- 6 Sessions: {win_rates.get(6, 0):.2%}\n"
            
            
            await self.bot.send_message(chat_id=self.chat_id, text=message)