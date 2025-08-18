from .utils import parse_option_symbol
from .premium_tracker import PremiumTracker
from alpaca.trading.enums import AssetClass
from collections import defaultdict

class WheelStateManager:
    """Manager for tracking wheel strategy state"""
    
    def __init__(self):
        self.state = {}
    
    def update_state(self, all_positions, premium_tracker=None):
        """Update state based on current positions"""
        self.state = update_state(all_positions, premium_tracker)
        return self.state
    
    def get_state(self):
        """Get current state"""
        return self.state

def calculate_risk(positions):
    """Calculate total risk from all positions"""
    risk = 0
    for p in positions:
        if p.asset_class == AssetClass.US_EQUITY:
            risk += float(p.avg_entry_price) * abs(int(p.qty))
        elif p.asset_class == AssetClass.US_OPTION:
            _, option_type, strike_price = parse_option_symbol(p.symbol)
            if option_type == 'P':
                risk += 100 * strike_price * abs(int(p.qty))

    return risk

def count_positions_by_symbol(positions):
    """Count the number of positions (puts, calls, shares) for each underlying symbol"""
    position_counts = defaultdict(lambda: {'puts': 0, 'calls': 0, 'shares': 0})
    
    for p in positions:
        if p.asset_class == AssetClass.US_EQUITY:
            underlying = p.symbol
            position_counts[underlying]['shares'] += abs(int(p.qty)) // 100  # Count in lots of 100
        elif p.asset_class == AssetClass.US_OPTION:
            underlying, option_type, _ = parse_option_symbol(p.symbol)
            if option_type == 'P':
                position_counts[underlying]['puts'] += abs(int(p.qty))
            elif option_type == 'C':
                position_counts[underlying]['calls'] += abs(int(p.qty))
    
    return dict(position_counts)

def update_state(all_positions, premium_tracker=None):    
    """
    Given the current positions, return a state dictionary describing where in the wheel each symbol is.
    Now supports multiple positions per symbol for averaging down.
    Includes premium-adjusted cost basis for better covered call strikes.
    """

    state = {}

    for p in all_positions:
        if p.asset_class == AssetClass.US_EQUITY:
            if int(p.qty) <= 0:
                raise ValueError(f"Only long stock positions allowed! Got {p.symbol} with qty {p.qty}")

            underlying = p.symbol
            if underlying in state:
                if state[underlying]["type"] != "short_call_awaiting_stock":
                    raise ValueError(f"Unexpected state for {underlying}: {state[underlying]}")
                state[underlying]["type"] = "short_call"
            else:
                avg_price = float(p.avg_entry_price)
                qty = int(p.qty)
                
                # Calculate adjusted cost basis if premium tracker is available
                if premium_tracker:
                    adjusted_price = premium_tracker.get_adjusted_cost_basis(underlying, avg_price, qty)
                else:
                    adjusted_price = avg_price
                
                state[underlying] = {
                    "type": "long_shares", 
                    "price": avg_price,  # Original entry price
                    "adjusted_price": adjusted_price,  # Premium-adjusted price
                    "qty": qty
                }

        elif p.asset_class == AssetClass.US_OPTION:
            if int(p.qty) >= 0:
                raise ValueError(f"Only short option positions allowed! Got {p.symbol} with qty {p.qty}")

            underlying, option_type, _ = parse_option_symbol(p.symbol)

            if underlying in state:
                # Handle multiple puts (allowed for averaging down with max_wheel_layers)
                if state[underlying]["type"] == "short_put" and option_type == 'P':
                    # Multiple puts are allowed - keep the short_put state
                    pass
                elif state[underlying]["type"] == "long_shares" and option_type == 'C':
                    # Shares + covered call = short_call state
                    state[underlying]["type"] = "short_call"
                else:
                    raise ValueError(f"Unexpected state for {underlying}: {state[underlying]} with option {option_type}")
            else:
                if option_type == "C":
                    state[underlying] = {"type": "short_call_awaiting_stock", "price": None}
                elif option_type == "P":
                    state[underlying] = {"type": "short_put", "price": None}
                else:
                    raise ValueError(f"Unknown option type: {option_type}")

    # Final validation and add position counts
    position_counts = count_positions_by_symbol(all_positions)
    
    for underlying, st in state.items():
        if st["type"] not in {"short_put", "long_shares", "short_call"}:
            raise ValueError(f"Invalid final state for {underlying}: {st}")
        
        # Add position counts to state
        if underlying in position_counts:
            st["position_counts"] = position_counts[underlying]
        else:
            st["position_counts"] = {'puts': 0, 'calls': 0, 'shares': 0}
        
    return state