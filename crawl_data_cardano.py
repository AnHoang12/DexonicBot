import os
import json
import requests
import time
import sys
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
load_dotenv()


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database Configuration
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

BLOCKFROST_API_KEY = "mainnet7DhJrjV9S7SH9FllpKANoAFvnD1EQoMX" 
BLOCKFROST_BASE_URL = "https://cardano-mainnet.blockfrost.io/api/v0"
MINSWAP_POOL_ADDRESS = "addr1z8snz7c4974vzdpxu65ruphl3zjdvtxw8strf2c2tmqnxz2j2c79gy9l76sdg0xwhd7r0c0kna0tycz4y5s6mlenh8pq0xmsha"  # Minswap router address
PRICE_API_URL = "https://api.coingecko.com/api/v3/simple/price?ids=cardano&vs_currencies=usd"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

TOKEN_REGISTRY = {
    
    # Cardano Native Tokens
    "lovelace": ("ADA", 6),
    
    # DeFi & DEX Tokens
    "9a9693a9a37912a5097918f97918d15240c92ab729a0b7c4aa144d77_MIN": ("MIN", 6),  # Minswap
    "29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c6_4d494e": ("MIN", 6),  # Alternative MIN
    "c0ee29a85b13209423b10447d3c2e6a50641a15c57770e27cb9d507e_MILK": ("MILK", 6),  # MuesliSwap
    "1d7f33bd23d85e1a25d87d86fac4f199c3197a2f7afeb662a0f34e1e_DJED": ("DJED", 6),  # Djed stablecoin
    "02aa5a414945e89d6bb8f83ac2d7a4e5c04340ba254e2491792bc4bf_SHEN": ("SHEN", 6),  # Shen (Djed reserve coin)
    "1f7a58a1aa1e6b047a42109ade331ce26c9c2cce124cmc5e4e6152f4_LENFI": ("LENFI", 6),  # Lenfi
    "af2e27f580f7f08e93190a81f72462f153026d06450924726645891b_44524950": ("DRIP", 6),  # Dripdropz
    "b6a7467ea1deb012808ef4e87b5ff371e85f7142d7b356a40d9b42a0_IAG": ("IAG", 6),  # Indigo
    "8a1cfae21368b8bebbbed9800fec304e95cce39a2a57dc35e2e3ebaa_HOSKY": ("HOSKY", 0),  # Hosky
    "da8c30857834c6ae7203935b89278c532b3995245295456f993e1d24_4c51": ("LQ", 6),  # Liqwid Finance
    "da8c30857834c6ae7203935b89278c532b3995245295456f993e1d24_5154": ("LQ", 6),  # Alternative LQ
    "533bb94a8850ee79473fd20c90118fa0b3d61537f2774c0632230504_CNYX": ("CNYX", 6),  # CENNZNET
    "c29a5e31a486b48cfce517fafdb2f9fee8756befe5ac178fc25e2f60_444542": ("DEP", 6),  # DEP
    "d9312da562da182b02322fd8acb536f37eb9d29fba7c49ca9a5427ad_COPI": ("COPI", 6),  # Copious
    "776e3f291b3eb2f9557513fe8796e909, 0f9e61b, c7f3952b7c048c12_DANA": ("DANA", 6),  # DANA
    
    # USDT and stablecoin entries
    "a0028f350aaabe0545fdcb56b039bfb08e4bb4d8c4d7c3c7d481c235_USDT": ("USDT", 6),
    "a0028f350aaabe0545fdcb56b039bfb08e4bb4d8c4d7c3c7d481c235_USDC": ("USDC", 6),
    "b34b3ea80060ace9427bda98690a73d33840e27aaa8d6edb7f0c757a634e554443": ("iUSD", 6),
    "e4214b7cce62ac6fbba385d164df48e157eae5863521b4b67ca71d716d41": ("DJED", 6),
    "fb3a3a4abf4b0e197a784dafbd13d4c21c2b5bf3bb74c0443b3306f2555344": ("USDW", 6),
    "dfa95fba39f127a6947048a45140059619e3a4c73c37ce055762d69e4755344": ("USDA", 6),
    "b52eac4b2bd1e62cf1c23d1fd987065d690ed867dafe7d3d61ef9c59535452": ("STRM", 6),
}

STABLECOINS = ["USDT", "USDC", "iUSD", "USDW", "USDA", "DJED"]

def init_database():
    try:
        engine = create_engine(DATABASE_URL)
        logger.info("Database connection established successfully")
        
        with engine.connect() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS ada_prices (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    open_time DATETIME NOT NULL,
                    symbol VARCHAR(10) NOT NULL,
                    price DECIMAL(20, 8) NOT NULL,
                    volume DECIMAL(20, 8) NOT NULL,
                    INDEX (symbol, open_time)
                )
            """))
            connection.commit()
            logger.info("Table token_prices ensured")
        
        return engine
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        sys.exit(1)

def get_ada_usd_price() -> float:
    """Get the current ADA to USD price from CoinGecko API."""
    try:
        response = requests.get(PRICE_API_URL)
        response.raise_for_status()
        data = response.json()
        return data.get("cardano", {}).get("usd", 0)
    except Exception as e:
        logger.error(f"Error fetching ADA/USD price: {e}")
        return 0

def get_token_info(asset_id: str) -> Tuple[str, int]:
    """Get token symbol and decimals from asset ID."""
    if asset_id == "lovelace":
        return "ADA", 6
    
    if asset_id in TOKEN_REGISTRY:
        return TOKEN_REGISTRY[asset_id]
    
    try:
        response = make_blockfrost_request(f"/assets/{asset_id}")
        metadata = response.get("metadata", {})
        ticker = metadata.get("ticker", asset_id[:10] + "...")
        decimals = metadata.get("decimals", 6)
        if decimals is None:
            decimals = 6  
        return ticker, decimals
    except Exception as e:
        logger.error(f"Error getting token info for {asset_id}: {e}")
        return asset_id[:10] + "...", 6  

def is_stablecoin(token_symbol: str) -> bool:
    """Check if a token symbol is a stablecoin."""
    return token_symbol in STABLECOINS

def make_blockfrost_request(endpoint: str, params: Dict = None) -> Dict:
    """Make a request to Blockfrost API with retry logic."""
    url = f"{BLOCKFROST_BASE_URL}{endpoint}"
    headers = {"project_id": BLOCKFROST_API_KEY}
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                raise

def get_minswap_transactions(limit: int = 100) -> List[Dict]:
    """Get recent transactions involving the Minswap contract."""
    transactions = []
    page = 1
    per_page = 100  
    
    logger.info(f"Fetching Minswap transactions...")
    
    while len(transactions) < limit:
        try:
            endpoint = f"/addresses/{MINSWAP_POOL_ADDRESS}/transactions"
            params = {"page": page, "count": per_page, "order": "desc"}
            response = make_blockfrost_request(endpoint, params)
            
            if not response:
                break
                
            transactions.extend(response)
            logger.info(f"Fetched {len(response)} transactions (total: {len(transactions)})")
            
            if len(response) < per_page:
                break
                
            page += 1
            
        except Exception as e:
            logger.error(f"Error fetching transactions: {e}")
            break
    
    return transactions[:limit]

def get_transaction_details(tx_hash: str) -> Dict:
    """Get detailed information about a transaction including UTXOs."""
    logger.info(f"Fetching details for transaction: {tx_hash}")
    
    try:
        tx_info = make_blockfrost_request(f"/txs/{tx_hash}")
        utxos = make_blockfrost_request(f"/txs/{tx_hash}/utxos")
        
        return {
            "hash": tx_hash,
            "block_height": tx_info.get("block_height"),
            "block_time": tx_info.get("block_time"),
            "fee": tx_info.get("fees"),
            "inputs": utxos.get("inputs", []),
            "outputs": utxos.get("outputs", [])
        }
    except Exception as e:
        logger.error(f"Error fetching transaction details: {e}")
        return {}

def find_stablecoin_swaps(swap_results: List[Dict]) -> Dict[str, float]:
    """
    Find and analyze stablecoin swaps to determine ADA to USD rates.
    Returns a dictionary of stablecoin symbols to ADA price.
    """
    stablecoin_rates = {}
    
    for swap in swap_results:
        token_symbol = swap.get("token_symbol")
        
        if token_symbol and is_stablecoin(token_symbol):
            if swap.get("direction") == "TOKEN => ADA":
                stablecoin_rates[token_symbol] = swap.get("price_in_ada", 0)
            else:
                token_per_ada = swap.get("price_token_per_ada", 0)
                if token_per_ada > 0:
                    stablecoin_rates[token_symbol] = 1 / token_per_ada
    
    if stablecoin_rates:
        avg_rate = sum(stablecoin_rates.values()) / len(stablecoin_rates)
        stablecoin_rates["AVERAGE"] = avg_rate
    
    return stablecoin_rates

def analyze_minswap_transaction(tx_details: Dict) -> Optional[Dict]:
    """
    Analyze a Minswap transaction to identify swap details.
    Returns None if not a swap transaction.
    """
    if not tx_details or "inputs" not in tx_details or "outputs" not in tx_details:
        return None
    
    minswap_inputs = [
        utxo for utxo in tx_details["inputs"] 
        if utxo.get("address") == MINSWAP_POOL_ADDRESS
    ]
    
    minswap_outputs = [
        utxo for utxo in tx_details["outputs"] 
        if utxo.get("address") == MINSWAP_POOL_ADDRESS
    ]
    
    if not minswap_inputs or not minswap_outputs:
        return None
    
    tokens_in = {}
    for utxo in minswap_inputs:
        for amount in utxo.get("amount", []):
            unit = amount.get("unit", "")
            quantity = int(amount.get("quantity", 0))
            tokens_in[unit] = tokens_in.get(unit, 0) + quantity
    
    tokens_out = {}
    for utxo in minswap_outputs:
        for amount in utxo.get("amount", []):
            unit = amount.get("unit", "")
            quantity = int(amount.get("quantity", 0))
            tokens_out[unit] = tokens_out.get(unit, 0) + quantity
    
    token_diff = {}
    all_units = set(tokens_in.keys()) | set(tokens_out.keys())
    
    for unit in all_units:
        diff = tokens_out.get(unit, 0) - tokens_in.get(unit, 0)
        if diff != 0:
            token_diff[unit] = diff
    
    if len(token_diff) < 2:
        return None
    
    if "lovelace" not in token_diff:
        return None
    
    ada_diff = token_diff.get("lovelace", 0) / 1e6 
    
    other_tokens = [unit for unit in token_diff.keys() if unit != "lovelace"]
    if not other_tokens:
        return None
    
    other_token = other_tokens[0]
    
    try:
        token_symbol, token_decimals = get_token_info(other_token)
        
        if token_decimals is None:
            logger.warning(f"No decimals found for {other_token}, using default of 6")
            token_decimals = 6
            
    except Exception as e:
        logger.error(f"Error getting token info for {other_token}: {e}")
        token_symbol = other_token[:10] + "..."
        token_decimals = 6  
        
    token_diff_value = token_diff.get(other_token, 0) / (10 ** token_decimals)
    
    if ada_diff > 0:  
        direction = "TOKEN => ADA"
        price_in_ada = abs(ada_diff / token_diff_value) if token_diff_value != 0 else 0
        price_token_per_ada = 1 / price_in_ada if price_in_ada != 0 else 0
    else:  
        direction = "ADA => TOKEN"
        price_in_ada = abs(token_diff_value / abs(ada_diff)) if ada_diff != 0 else 0  # Fixed calculation
        price_token_per_ada = abs(token_diff_value / ada_diff) if ada_diff != 0 else 0
    
    return {
        "transaction_hash": tx_details["hash"],
        "timestamp": datetime.fromtimestamp(tx_details["block_time"]).isoformat(),
        "token_symbol": token_symbol,
        "token_id": other_token,
        "direction": direction,
        "price_in_ada": price_in_ada,
        "price_token_per_ada": price_token_per_ada,
        "ada_amount": abs(ada_diff),
        "token_amount": abs(token_diff_value)
    }

def calculate_usd_prices(price_data: Dict, ada_usd_price: float, stablecoin_rates: Dict) -> Dict:
    """
    Calculate USD prices for all tokens based on ADA price and stablecoin rates.
    """
    usd_conversion_rate = ada_usd_price
    
    if "AVERAGE" in stablecoin_rates:
        stable_ada_per_usd = stablecoin_rates["AVERAGE"]
        usd_per_ada = 1 / stable_ada_per_usd if stable_ada_per_usd > 0 else 0
        
        if usd_per_ada > 0:
            logger.info(f"Using stablecoin-derived USD price: 1 ADA = ${usd_per_ada:.4f}")
            usd_conversion_rate = usd_per_ada
        else:
            logger.info(f"Using CoinGecko USD price: 1 ADA = ${ada_usd_price:.4f}")
    else:
        logger.info(f"Using CoinGecko USD price: 1 ADA = ${ada_usd_price:.4f}")
    
    for token_symbol, data in price_data.items():
        price_in_ada = data.get("latest_price_in_ada", 0)
        price_in_usd = price_in_ada * usd_conversion_rate
        
        data["latest_price_in_usd"] = price_in_usd
        data["usd_per_token"] = price_in_usd
        data["token_per_usd"] = 1 / price_in_usd if price_in_usd > 0 else 0
    
    return price_data

def insert_prices_to_db(engine, price_data: Dict, current_time: datetime):
    """
    Insert token price data into the database.
    """
    logger.info("Inserting price data into database...")
    
    if "ADA" not in price_data and "lovelace" in price_data:
        price_data["ADA"] = price_data["lovelace"]
    
    with engine.connect() as connection:
        try:
            for token, data in price_data.items():
                if data.get("latest_price_in_usd", 0) <= 0:
                    continue
                
                query = text("""
                    INSERT INTO token_prices (open_time, symbol, price, volume)
                    VALUES (:open_time, :symbol, :price, :volume)
                """)
                
                connection.execute(query, {
                    "open_time": current_time,
                    "symbol": token,
                    "price": data.get("latest_price_in_usd", 0),
                    "volume": data.get("volume_ada", 0)
                })
            
            connection.commit()
            logger.info(f"Successfully inserted prices for {len(price_data)} tokens")
        
        except Exception as e:
            logger.error(f"Error inserting data into database: {e}")
            connection.rollback()

def main():
    """Main function to retrieve and analyze Minswap transactions and store prices in database."""
    logger.info("Starting Cardano price tracker...")
    
    if BLOCKFROST_API_KEY == "YOUR_BLOCKFROST_API_KEY":
        logger.error("Error: Please set your Blockfrost API key in the script.")
        return
    
    engine = init_database()
    
    ada_usd_price = get_ada_usd_price()
    logger.info(f"Current ADA/USD price from API: ${ada_usd_price:.4f}")
    
    current_time = datetime.now()
    
    num_transactions = 50  
    transactions = get_minswap_transactions(num_transactions)
    
    if not transactions:
        logger.warning("No transactions found.")
        return
    
    logger.info(f"Found {len(transactions)} transactions. Analyzing swaps...")
    
    swap_results = []
    price_data = {}
    
    for tx in transactions:
        tx_hash = tx.get("tx_hash")
        tx_details = get_transaction_details(tx_hash)
        swap_info = analyze_minswap_transaction(tx_details)
        
        if swap_info:
            swap_results.append(swap_info)
            
            token_symbol = swap_info["token_symbol"]
            if token_symbol not in price_data:
                price_data[token_symbol] = {
                    "token_id": swap_info["token_id"],
                    "latest_price_in_ada": swap_info["price_in_ada"],
                    "latest_price_token_per_ada": swap_info["price_token_per_ada"],
                    "latest_transaction": swap_info["transaction_hash"],
                    "latest_timestamp": swap_info["timestamp"],
                    "swap_count": 1,
                    "volume_ada": swap_info["ada_amount"]
                }
            else:
                price_data[token_symbol]["swap_count"] += 1
                price_data[token_symbol]["volume_ada"] += swap_info["ada_amount"]
                
                if swap_info["timestamp"] > price_data[token_symbol]["latest_timestamp"]:
                    price_data[token_symbol]["latest_price_in_ada"] = swap_info["price_in_ada"]
                    price_data[token_symbol]["latest_price_token_per_ada"] = swap_info["price_token_per_ada"]
                    price_data[token_symbol]["latest_transaction"] = swap_info["transaction_hash"]
                    price_data[token_symbol]["latest_timestamp"] = swap_info["timestamp"]
    
    price_data["ADA"] = {
        "token_id": "lovelace",
        "latest_price_in_ada": 1.0,
        "latest_price_token_per_ada": 1.0,
        "latest_timestamp": current_time.isoformat(),
        "swap_count": len(swap_results),
        "volume_ada": sum(swap["ada_amount"] for swap in swap_results)
    }
    
    stablecoin_rates = find_stablecoin_swaps(swap_results)
    
    price_data = calculate_usd_prices(price_data, ada_usd_price, stablecoin_rates)
    
    insert_prices_to_db(engine, price_data, current_time)
    
    logger.info(f"Analysis complete. Found {len(swap_results)} swaps.")
    
    logger.info("\nPrice Summary:")
    for token, data in price_data.items():
        ada_price = data.get('latest_price_in_ada', 0)
        usd_price = data.get('latest_price_in_usd', 0)
        logger.info(f"{token}: {ada_price:.6f} ADA (${usd_price:.4f} USD)")

if __name__ == "__main__":
    main()