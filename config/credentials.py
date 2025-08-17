from dotenv import load_dotenv
import os
from .config_loader import StrategyConfig

load_dotenv(override=True)  # Load from .env file in root

# API Credentials (kept in .env for security)
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
IS_PAPER = os.getenv("IS_PAPER", "true").lower() == "true"

# Strategy Configuration (loaded from JSON)
strategy_config = StrategyConfig()

# Export commonly used settings for backward compatibility
BALANCE_ALLOCATION = strategy_config.get_balance_allocation()
MAX_WHEEL_LAYERS = strategy_config.get_max_wheel_layers()
