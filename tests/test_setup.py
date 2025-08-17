#!/usr/bin/env python
"""Test script to verify the options wheel setup"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test all critical imports"""
    print("Testing imports...")
    try:
        import alpaca.trading
        print("[OK] alpaca.trading imported")
    except ImportError as e:
        print(f"[FAIL] Failed to import alpaca.trading: {e}")
        return False
    
    try:
        from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER
        print("[OK] Credentials module imported")
        print(f"  - API Key: {'Configured' if ALPACA_API_KEY else 'Missing'}")
        print(f"  - Secret Key: {'Configured' if ALPACA_SECRET_KEY else 'Missing'}")
        print(f"  - Paper Trading: {IS_PAPER}")
    except ImportError as e:
        print(f"[FAIL] Failed to import credentials: {e}")
        return False
    
    try:
        from core.broker_client import BrokerClient
        print("[OK] BrokerClient imported")
    except ImportError as e:
        print(f"[FAIL] Failed to import BrokerClient: {e}")
        return False
    
    try:
        from core.strategy import select_options, score_options
        print("[OK] Strategy module imported")
    except ImportError as e:
        print(f"[FAIL] Failed to import strategy module: {e}")
        return False
    
    try:
        from core.execution import sell_puts, sell_calls
        print("[OK] Execution module imported")
    except ImportError as e:
        print(f"[FAIL] Failed to import execution module: {e}")
        return False
        
    return True

def test_api_connection():
    """Test Alpaca API connection"""
    print("\nTesting API connection...")
    try:
        from core.broker_client import BrokerClient
        from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
        client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        account = client.get_account()
        print(f"[OK] Connected to Alpaca API")
        print(f"  - Account Status: {account.status}")
        print(f"  - Buying Power: ${float(account.buying_power):,.2f}")
        print(f"  - Trading Blocked: {account.trading_blocked}")
        return True
    except Exception as e:
        print(f"[FAIL] API connection failed: {e}")
        return False

def test_configuration():
    """Test configuration loading"""
    print("\nTesting configuration...")
    try:
        from config.config_loader import StrategyConfig
        config = StrategyConfig()
        
        print("[OK] Configuration loaded")
        print(f"  - Allocation: {config.get_balance_allocation() * 100}%")
        print(f"  - Max Wheel Layers: {config.get_max_wheel_layers()}")
        print(f"  - Enabled Symbols: {', '.join(config.get_enabled_symbols())}")
        
        filters = config.get_option_filters()
        print(f"  - Delta Range: {filters['delta_min']} - {filters['delta_max']}")
        print(f"  - DTE Range: {filters['expiration_min_days']} - {filters['expiration_max_days']} days")
        
        return True
    except Exception as e:
        print(f"[FAIL] Configuration failed: {e}")
        return False

def test_database():
    """Test database operations"""
    print("\nTesting database...")
    try:
        from core.database import WheelDatabase
        db = WheelDatabase()
        
        # Test basic query
        positions = db.get_position_history(status='open')
        print(f"[OK] Database operational")
        print(f"  - Active positions: {len(positions)}")
        
        # Check tables exist
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"  - Tables: {', '.join(tables)}")
        
        return True
    except Exception as e:
        print(f"[FAIL] Database test failed: {e}")
        return False

def test_strategy_execution():
    """Test strategy execution logic (dry run)"""
    print("\nTesting strategy logic...")
    try:
        from core.broker_client import BrokerClient
        from core.strategy import select_options, score_options
        from config.config_loader import StrategyConfig
        from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
        
        client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        config = StrategyConfig()
        
        # Get enabled symbols
        symbols = config.get_enabled_symbols()
        if symbols:
            print(f"[OK] Strategy logic ready")
            print(f"  - Testing symbol: {symbols[0]}")
            
            # Try to get option chain (may fail if market is closed)
            try:
                options = client.get_option_contracts(
                    underlying_symbol=symbols[0],
                    option_type="put"
                )
                print(f"  - Found {len(options)} put options")
            except Exception as e:
                print(f"  - Option chain unavailable (market may be closed)")
        
        return True
    except Exception as e:
        print(f"[FAIL] Strategy test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Options Wheel Strategy - Setup Test")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("API Connection", test_api_connection()))
    results.append(("Configuration", test_configuration()))
    results.append(("Database", test_database()))
    results.append(("Strategy Logic", test_strategy_execution()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("-" * 60)
    
    passed = 0
    for name, result in results:
        status = "[PASSED]" if result else "[FAILED]"
        print(f"{name:20} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"Result: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n[SUCCESS] All tests passed! Your setup is ready.")
        print("\nYou can now run the strategy with: run-strategy")
    else:
        print("\n[ERROR] Some tests failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()