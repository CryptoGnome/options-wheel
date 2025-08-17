from pathlib import Path
from datetime import datetime
from core.utils import get_ny_timestamp
import json

class StrategyLogger:
    def __init__(self, enabled=True, log_path="logs/strategy_log.json"):
        self.enabled = enabled
        self.log_file = Path(log_path)
        self.log_entry = {}

        if self.enabled:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_entry["datetime"] = get_ny_timestamp()

    def set_fresh_start(self, is_fresh_start: bool):
        if self.enabled:
            self.log_entry["fresh_start"] = is_fresh_start
            self.log_entry["current_positions"] = []

    def add_current_positions(self, positions: list):
        if self.enabled and not self.log_entry.get("fresh_start"):
            self.log_entry["current_positions"] = [
                {
                    "asset_class": pos.asset_class.title().lower(),
                    "symbol": pos.symbol,
                    "side": pos.side.title().lower(),
                    "qty": pos.qty,
                    "purchase_price": pos.avg_entry_price,
                    "current_price": pos.current_price,
                    "pnl": pos.unrealized_pl
                }
                for pos in positions
            ]

    def add_state_dict(self, state_dict: dict):
        if self.enabled:
            self.log_entry["state_dict"] = state_dict

    def set_buying_power(self, buying_power: float):
        if self.enabled:
            self.log_entry["buying_power"] = buying_power

    def set_allowed_symbols(self, symbols: list):
        if self.enabled:
            self.log_entry["allowed_symbols"] = symbols

    def set_filtered_symbols(self, symbols: list):
        if self.enabled:
            self.log_entry["filtered_symbols"] = symbols
    
    def log_call_options(self, call_options: list[dict]):
        if self.enabled:
            self.log_entry["call_options"] = call_options

    def log_put_options(self, put_options: list[dict]):
        if self.enabled:
            self.log_entry["put_options"] = put_options

    def log_sold_calls(self, call_dict: dict):
        if self.enabled:
            if self.log_entry.get("sold_calls") is None:
                self.log_entry["sold_calls"] = []
            self.log_entry["sold_calls"].append(call_dict)

    def log_sold_puts(self, put_dict: dict):
        if self.enabled:
            if self.log_entry.get("sold_puts") is None:
                self.log_entry["sold_puts"] = []
            self.log_entry["sold_puts"].append(put_dict)

    def save(self):
        if not self.enabled:
            return

        # Load existing log data if file exists
        if self.log_file.exists():
            with open(self.log_file, "r") as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        raise ValueError("Log file does not contain a list.")
                except json.JSONDecodeError:
                    data = []
        else:
            data = []

        # Append the new log entry
        data.append(self.log_entry)
        
        # Write the updated list back
        with open(self.log_file, "w") as f:
            json.dump(data, f, indent=2)
