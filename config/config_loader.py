"""
Load and manage strategy configuration from JSON file.
"""
import json
from pathlib import Path
from typing import Dict, Any

class StrategyConfig:
    """Handles loading and accessing strategy configuration"""
    
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent / "strategy_config.json"
        
        self.config_path = config_path
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        if not self.config_path.exists():
            # Create default config if it doesn't exist
            default_config = {
                "balance_settings": {
                    "allocation_percentage": 0.5,
                    "max_wheel_layers": 2
                },
                "option_filters": {
                    "delta_min": 0.15,
                    "delta_max": 0.30,
                    "yield_min": 0.04,
                    "yield_max": 1.00,
                    "expiration_min_days": 0,
                    "expiration_max_days": 21,
                    "open_interest_min": 100,
                    "score_min": 0.05
                },
                "symbols": {},
                "default_contracts": 1
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            
            return default_config
        
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()
    
    def get_enabled_symbols(self) -> list:
        """Get list of enabled symbols"""
        return [
            symbol for symbol, settings in self.config.get("symbols", {}).items()
            if settings.get("enabled", True)
        ]
    
    def get_contracts_for_symbol(self, symbol: str) -> int:
        """Get number of contracts to trade for a specific symbol"""
        symbol_config = self.config.get("symbols", {}).get(symbol, {})
        return symbol_config.get("contracts", self.config.get("default_contracts", 1))
    
    def get_symbol_contracts(self, symbol: str) -> int:
        """Alias for get_contracts_for_symbol for backward compatibility"""
        return self.get_contracts_for_symbol(symbol)
    
    def get_balance_allocation(self) -> float:
        """Get balance allocation percentage"""
        return self.config.get("balance_settings", {}).get("allocation_percentage", 0.5)
    
    def get_max_wheel_layers(self) -> int:
        """Get maximum wheel layers per symbol"""
        return self.config.get("balance_settings", {}).get("max_wheel_layers", 2)
    
    def get_option_filters(self) -> dict:
        """Get all option filter parameters"""
        return self.config.get("option_filters", {
            "delta_min": 0.15,
            "delta_max": 0.30,
            "yield_min": 0.04,
            "yield_max": 1.00,
            "expiration_min_days": 0,
            "expiration_max_days": 21,
            "open_interest_min": 100,
            "score_min": 0.05
        })
    
    def get_rolling_settings(self) -> dict:
        """Get global rolling settings"""
        return self.config.get("rolling_settings", {
            "enabled": False,
            "days_before_expiry": 1,
            "min_premium_to_roll": 0.05,
            "roll_delta_target": 0.25
        })
    
    def is_rolling_enabled_for_symbol(self, symbol: str) -> bool:
        """Check if rolling is enabled for a specific symbol"""
        global_enabled = self.get_rolling_settings().get("enabled", False)
        symbol_config = self.config.get("symbols", {}).get(symbol, {})
        symbol_rolling = symbol_config.get("rolling", {})
        return symbol_rolling.get("enabled", global_enabled)
    
    def get_rolling_strategy_for_symbol(self, symbol: str) -> str:
        """Get rolling strategy for a specific symbol (forward, down, or both)"""
        symbol_config = self.config.get("symbols", {}).get(symbol, {})
        symbol_rolling = symbol_config.get("rolling", {})
        return symbol_rolling.get("strategy", "forward")
    
    def update_symbol(self, symbol: str, enabled: bool = None, contracts: int = None):
        """Update symbol configuration"""
        if symbol not in self.config["symbols"]:
            self.config["symbols"][symbol] = {}
        
        if enabled is not None:
            self.config["symbols"][symbol]["enabled"] = enabled
        if contracts is not None:
            self.config["symbols"][symbol]["contracts"] = contracts
        
        self.save()
    
    def save(self):
        """Save current configuration to file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def __repr__(self):
        return f"StrategyConfig(symbols={len(self.get_enabled_symbols())}, allocation={self.get_balance_allocation():.0%})"