"""
Track premiums collected from options to adjust cost basis for better exit strategies.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

class PremiumTracker:
    """Tracks premiums collected from covered calls and puts to adjust cost basis"""
    
    def __init__(self, filepath=None):
        if filepath is None:
            filepath = Path(__file__).parent.parent / "data" / "premium_history.json"
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.history = self.load_history()
    
    def load_history(self):
        """Load premium history from file"""
        if self.filepath.exists():
            with open(self.filepath, 'r') as f:
                return json.load(f)
        return {}
    
    def save_history(self):
        """Save premium history to file"""
        with open(self.filepath, 'w') as f:
            json.dump(self.history, f, indent=2, default=str)
    
    def add_premium(self, symbol, premium_amount, option_type, strike, expiry, timestamp=None):
        """Record premium collected from selling an option"""
        if symbol not in self.history:
            self.history[symbol] = {
                "total_call_premium": 0.0,
                "total_put_premium": 0.0,
                "transactions": []
            }
        
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        transaction = {
            "timestamp": timestamp,
            "type": option_type,
            "premium": premium_amount,
            "strike": strike,
            "expiry": expiry
        }
        
        self.history[symbol]["transactions"].append(transaction)
        
        if option_type.upper() == 'C':
            self.history[symbol]["total_call_premium"] += premium_amount
        elif option_type.upper() == 'P':
            self.history[symbol]["total_put_premium"] += premium_amount
        
        self.save_history()
    
    def get_total_premium(self, symbol, option_type=None):
        """Get total premium collected for a symbol"""
        if symbol not in self.history:
            return 0.0
        
        if option_type is None:
            return (self.history[symbol]["total_call_premium"] + 
                   self.history[symbol]["total_put_premium"])
        elif option_type.upper() == 'C':
            return self.history[symbol]["total_call_premium"]
        elif option_type.upper() == 'P':
            return self.history[symbol]["total_put_premium"]
        else:
            return 0.0
    
    def get_adjusted_cost_basis(self, symbol, current_cost_basis, shares_qty):
        """
        Calculate adjusted cost basis after accounting for premiums collected.
        This helps determine better strike prices for covered calls.
        
        Args:
            symbol: Stock symbol
            current_cost_basis: Current average entry price per share
            shares_qty: Number of shares owned
        
        Returns:
            Adjusted cost basis per share
        """
        if shares_qty <= 0:
            return current_cost_basis
        
        # Get total call premiums (reduces cost basis when held)
        total_call_premium = self.get_total_premium(symbol, 'C')
        
        # Calculate premium per share
        premium_per_share = (total_call_premium * 100) / shares_qty  # *100 because options are per 100 shares
        
        # Adjusted cost = original cost - premiums collected
        adjusted_cost = current_cost_basis - premium_per_share
        
        return max(0, adjusted_cost)  # Ensure non-negative
    
    def reset_symbol(self, symbol):
        """Reset premium history for a symbol (use when position is closed)"""
        if symbol in self.history:
            del self.history[symbol]
            self.save_history()
    
    def get_history(self, symbol=None):
        """Get premium history for a symbol or all symbols"""
        if symbol:
            return self.history.get(symbol, {})
        return self.history