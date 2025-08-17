#!/usr/bin/env python3
"""
Interactive configuration manager for the wheel strategy.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config.config_loader import StrategyConfig
import json

def main():
    config = StrategyConfig()
    
    while True:
        print("\n=== Wheel Strategy Configuration ===")
        print(f"Balance Allocation: {config.get_balance_allocation():.0%}")
        print(f"Max Wheel Layers: {config.get_max_wheel_layers()}")
        print(f"Default Contracts: {config.config.get('default_contracts', 1)}")
        
        filters = config.get_option_filters()
        print(f"\nOption Filters:")
        print(f"  Delta: {filters['delta_min']:.2f} - {filters['delta_max']:.2f}")
        print(f"  DTE: {filters['expiration_min_days']} - {filters['expiration_max_days']} days")
        print(f"  Min OI: {filters['open_interest_min']}")
        print("\nEnabled Symbols:")
        
        symbols = config.config.get("symbols", {})
        for symbol, settings in symbols.items():
            if settings.get("enabled", True):
                contracts = settings.get("contracts", config.config.get("default_contracts", 1))
                print(f"  {symbol}: {contracts} contract(s)")
        
        print("\n1. Add/Edit Symbol")
        print("2. Remove Symbol")
        print("3. Change Balance Settings")
        print("4. Change Option Filters")
        print("5. Change Default Contracts")
        print("6. View Full JSON Config")
        print("0. Exit")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == "1":
            symbol = input("Enter symbol: ").upper().strip()
            contracts = input(f"Contracts for {symbol} (default 1): ").strip()
            contracts = int(contracts) if contracts else 1
            config.update_symbol(symbol, enabled=True, contracts=contracts)
            print(f"✓ Added/Updated {symbol} with {contracts} contract(s)")
            
        elif choice == "2":
            symbol = input("Enter symbol to remove: ").upper().strip()
            if symbol in config.config["symbols"]:
                config.update_symbol(symbol, enabled=False)
                print(f"✓ Disabled {symbol}")
            else:
                print(f"Symbol {symbol} not found")
                
        elif choice == "3":
            print("\nBalance Settings:")
            print("1. Allocation Percentage")
            print("2. Max Wheel Layers")
            sub_choice = input("Enter choice: ").strip()
            
            if sub_choice == "1":
                pct = input("Enter allocation percentage (0-100): ").strip()
                try:
                    pct = float(pct) / 100
                    if 0 <= pct <= 1:
                        config.config["balance_settings"]["allocation_percentage"] = pct
                        config.save()
                        print(f"✓ Set allocation to {pct:.0%}")
                except ValueError:
                    print("Invalid input")
            elif sub_choice == "2":
                layers = input("Enter max wheel layers (1-5): ").strip()
                try:
                    layers = int(layers)
                    if 1 <= layers <= 5:
                        config.config["balance_settings"]["max_wheel_layers"] = layers
                        config.save()
                        print(f"✓ Set max wheel layers to {layers}")
                except ValueError:
                    print("Invalid input")
                
        elif choice == "4":
            print("\nOption Filters:")
            print("1. Delta Range")
            print("2. DTE Range")
            print("3. Minimum Open Interest")
            sub_choice = input("Enter choice: ").strip()
            
            if sub_choice == "1":
                min_d = input("Enter min delta (e.g. 0.15): ").strip()
                max_d = input("Enter max delta (e.g. 0.30): ").strip()
                try:
                    min_d, max_d = float(min_d), float(max_d)
                    if 0 < min_d < max_d < 1:
                        config.config["option_filters"]["delta_min"] = min_d
                        config.config["option_filters"]["delta_max"] = max_d
                        config.save()
                        print(f"✓ Set delta range to {min_d:.2f} - {max_d:.2f}")
                except ValueError:
                    print("Invalid input")
            elif sub_choice == "2":
                min_dte = input("Enter min DTE days: ").strip()
                max_dte = input("Enter max DTE days: ").strip()
                try:
                    min_dte, max_dte = int(min_dte), int(max_dte)
                    if 0 <= min_dte < max_dte:
                        config.config["option_filters"]["expiration_min_days"] = min_dte
                        config.config["option_filters"]["expiration_max_days"] = max_dte
                        config.save()
                        print(f"✓ Set DTE range to {min_dte} - {max_dte} days")
                except ValueError:
                    print("Invalid input")
            elif sub_choice == "3":
                oi = input("Enter minimum open interest: ").strip()
                try:
                    oi = int(oi)
                    if oi >= 0:
                        config.config["option_filters"]["open_interest_min"] = oi
                        config.save()
                        print(f"✓ Set minimum OI to {oi}")
                except ValueError:
                    print("Invalid input")
                
        elif choice == "5":
            contracts = input("Enter default contracts: ").strip()
            try:
                contracts = int(contracts)
                if contracts > 0:
                    config.config["default_contracts"] = contracts
                    config.save()
                    print(f"✓ Set default contracts to {contracts}")
                else:
                    print("Must be positive")
            except ValueError:
                print("Invalid input")
                
        elif choice == "6":
            print("\n" + json.dumps(config.config, indent=2))
            input("\nPress Enter to continue...")
            
        elif choice == "0":
            break
        
        config.reload()

if __name__ == "__main__":
    main()