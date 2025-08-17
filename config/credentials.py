from dotenv import load_dotenv
import os

load_dotenv(override=True)  # Load from .env file in root

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
IS_PAPER = os.getenv("IS_PAPER", "true").lower() == "true"

# Balance Management Settings
BALANCE_ALLOCATION = float(os.getenv("BALANCE_ALLOCATION", "0.5"))  # Default to 50% of balance
MAX_POSITIONS_PER_SYMBOL = int(os.getenv("MAX_POSITIONS_PER_SYMBOL", "2"))  # Default to 2 positions per symbol
