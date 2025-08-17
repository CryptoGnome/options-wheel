#!/usr/bin/env python
"""Simple comprehensive test for options wheel strategy"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("\n" + "=" * 60)
    print("Options Wheel Strategy - Comprehensive Test")
    print("=" * 60)
    
    test_results = []
    
    # Test 1: Imports
    print("\n[1/6] Testing imports...")
    try:
        from core.broker_client import BrokerClient
        from core.database import WheelDatabase
        from core.strategy import select_options, score_options
        from core.execution import sell_puts, sell_calls
        from config.config_loader import StrategyConfig
        from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
        print("  [OK] All modules imported successfully")
        test_results.append(True)
    except Exception as e:
        print(f"  [FAIL] Import error: {e}")
        test_results.append(False)
    
    # Test 2: Configuration
    print("\n[2/6] Testing configuration...")
    try:
        config = StrategyConfig()
        allocation = config.get_balance_allocation()
        symbols = config.get_enabled_symbols()
        print(f"  [OK] Config loaded - {len(symbols)} symbols, {allocation*100:.1f}% allocation")
        test_results.append(True)
    except Exception as e:
        print(f"  [FAIL] Config error: {e}")
        test_results.append(False)
    
    # Test 3: API Connection
    print("\n[3/6] Testing API connection...")
    try:
        from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
        from core.broker_client import BrokerClient
        
        client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        account = client.get_account()
        print(f"  [OK] Connected - Account status: {account.status}")
        print(f"      Buying power: ${float(account.buying_power):,.2f}")
        test_results.append(True)
    except Exception as e:
        print(f"  [FAIL] API error: {e}")
        test_results.append(False)
    
    # Test 4: Database
    print("\n[4/6] Testing database...")
    try:
        from core.database import WheelDatabase
        
        db = WheelDatabase()
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
        print(f"  [OK] Database operational - {len(tables)} tables found")
        test_results.append(True)
    except Exception as e:
        print(f"  [FAIL] Database error: {e}")
        test_results.append(False)
    
    # Test 5: Strategy Logic
    print("\n[5/6] Testing strategy logic...")
    try:
        import pandas as pd
        from datetime import datetime, timedelta
        from core.strategy import score_options, filter_options
        
        # Create minimal mock data
        mock_df = pd.DataFrame([{
            'symbol': 'TEST',
            'strike_price': 100,
            'bid_price': 1.5,
            'ask_price': 1.6,
            'delta': -0.25,
            'open_interest': 200,
            'expiration_date': datetime.now() + timedelta(days=7)
        }])
        
        filtered = filter_options(mock_df)
        scores = score_options(filtered)
        print(f"  [OK] Strategy logic working - scored {len(scores)} options")
        test_results.append(True)
    except Exception as e:
        print(f"  [FAIL] Strategy error: {e}")
        test_results.append(False)
    
    # Test 6: Risk Parameters
    print("\n[6/6] Testing risk parameters...")
    try:
        from config.config_loader import StrategyConfig
        
        config = StrategyConfig()
        filters = config.get_option_filters()
        
        # Validate risk parameters
        checks = [
            ('Delta range', 0 <= filters['delta_min'] < filters['delta_max'] <= 1),
            ('DTE range', 0 <= filters['expiration_min_days'] < filters['expiration_max_days']),
            ('Allocation', 0 < config.get_balance_allocation() <= 1),
            ('Max layers', config.get_max_wheel_layers() > 0)
        ]
        
        all_valid = True
        for name, valid in checks:
            if not valid:
                print(f"  [FAIL] Invalid {name}")
                all_valid = False
        
        if all_valid:
            print("  [OK] All risk parameters valid")
        test_results.append(all_valid)
    except Exception as e:
        print(f"  [FAIL] Risk parameter error: {e}")
        test_results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("-" * 60)
    
    test_names = [
        "Module Imports",
        "Configuration",
        "API Connection",
        "Database",
        "Strategy Logic",
        "Risk Parameters"
    ]
    
    passed = sum(test_results)
    total = len(test_results)
    
    for name, result in zip(test_names, test_results):
        status = "[PASS]" if result else "[FAIL]"
        print(f"{name:20} {status}")
    
    print("-" * 60)
    print(f"Result: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed! System ready for trading.")
        print("Run the strategy with: run-strategy")
        return 0
    elif passed >= 4:
        print("\n[WARNING] Some tests failed but core systems operational.")
        print("Review failures before trading.")
        return 1
    else:
        print("\n[FAILURE] Critical tests failed. Fix issues before trading.")
        return 2

if __name__ == "__main__":
    exit(main())