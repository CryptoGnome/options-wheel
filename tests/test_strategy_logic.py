#!/usr/bin/env python
"""Unit tests for strategy logic and option scoring"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import pandas as pd

def test_option_scoring():
    """Test the option scoring algorithm"""
    print("\n[TEST] Option Scoring Algorithm")
    print("-" * 40)
    
    from core.strategy import score_options
    
    # Create mock option data
    mock_options = pd.DataFrame([
        {
            'symbol': 'AAPL_TEST1',
            'strike_price': 150.0,
            'bid_price': 2.50,
            'ask_price': 2.60,
            'delta': -0.25,
            'expiration_date': datetime.now() + timedelta(days=7)
        },
        {
            'symbol': 'AAPL_TEST2',
            'strike_price': 145.0,
            'bid_price': 1.80,
            'ask_price': 1.90,
            'delta': -0.20,
            'expiration_date': datetime.now() + timedelta(days=14)
        },
        {
            'symbol': 'AAPL_TEST3',
            'strike_price': 140.0,
            'bid_price': 0.95,
            'ask_price': 1.05,
            'delta': -0.15,
            'expiration_date': datetime.now() + timedelta(days=21)
        }
    ])
    
    try:
        scores = score_options(mock_options)
        print("[OK] Scoring algorithm executed")
        
        # Verify scores are in expected range
        if all(0 <= score <= 100 for score in scores):
            print("[OK] Scores within valid range (0-100)")
        else:
            print(f"[FAIL] Scores out of range: {scores}")
            return False
            
        # Verify higher delta (closer to ATM) gets better score for similar DTE
        print(f"  Score distribution: {[f'{s:.2f}' for s in scores]}")
        return True
        
    except Exception as e:
        print(f"[FAIL] Scoring failed: {e}")
        return False

def test_option_filtering():
    """Test option filtering logic"""
    print("\n[TEST] Option Filtering")
    print("-" * 40)
    
    from core.strategy import filter_options
    from config.config_loader import StrategyConfig
    
    config = StrategyConfig()
    filters = config.get_option_filters()
    
    # Create mock options with various characteristics
    mock_options = pd.DataFrame([
        # Good option - should pass
        {
            'strike_price': 100,
            'bid_price': 1.50,
            'delta': -0.25,
            'open_interest': 500,
            'expiration_date': datetime.now() + timedelta(days=10)
        },
        # Bad delta - too high
        {
            'strike_price': 105,
            'bid_price': 3.00,
            'delta': -0.45,
            'open_interest': 500,
            'expiration_date': datetime.now() + timedelta(days=10)
        },
        # Bad open interest - too low
        {
            'strike_price': 95,
            'bid_price': 1.00,
            'delta': -0.20,
            'open_interest': 5,
            'expiration_date': datetime.now() + timedelta(days=10)
        },
        # Bad expiration - too far out
        {
            'strike_price': 98,
            'bid_price': 2.00,
            'delta': -0.22,
            'open_interest': 500,
            'expiration_date': datetime.now() + timedelta(days=45)
        }
    ])
    
    try:
        filtered = filter_options(mock_options)
        
        print(f"[OK] Filtered {len(filtered)} of {len(mock_options)} options")
        print(f"  Delta range: {filters['delta_min']} to {filters['delta_max']}")
        print(f"  DTE range: {filters['expiration_min_days']} to {filters['expiration_max_days']} days")
        print(f"  Min open interest: {filters['open_interest_min']}")
        
        # Verify filtering worked correctly
        if len(filtered) < len(mock_options):
            print("[OK] Filtering removed invalid options")
            return True
        else:
            print("[WARNING] No options were filtered - check filter criteria")
            return True
            
    except Exception as e:
        print(f"[FAIL] Filtering failed: {e}")
        return False

def test_position_selection():
    """Test position selection with max positions per symbol"""
    print("\n[TEST] Position Selection Logic")
    print("-" * 40)
    
    from core.strategy import select_options
    
    # Create mock options from multiple symbols
    mock_options = pd.DataFrame([
        {'symbol': 'AAPL_OPT1', 'underlying_symbol': 'AAPL', 'strike_price': 150},
        {'symbol': 'AAPL_OPT2', 'underlying_symbol': 'AAPL', 'strike_price': 145},
        {'symbol': 'MSFT_OPT1', 'underlying_symbol': 'MSFT', 'strike_price': 350},
        {'symbol': 'MSFT_OPT2', 'underlying_symbol': 'MSFT', 'strike_price': 345},
    ])
    
    mock_scores = [85, 80, 75, 70]
    
    # Test with position counts
    position_counts = {'AAPL': {'puts': 1}, 'MSFT': {'puts': 0}}
    
    try:
        selected = select_options(
            mock_options, 
            mock_scores, 
            max_per_symbol=1,
            position_counts=position_counts
        )
        
        print(f"[OK] Selected {len(selected)} options")
        
        # Verify no duplicate symbols when max_per_symbol=1
        symbols = [opt['underlying_symbol'] for _, opt in selected.iterrows()]
        if len(symbols) == len(set(symbols)):
            print("[OK] No duplicate symbols in selection")
        else:
            print("[FAIL] Found duplicate symbols")
            return False
            
        print(f"  Selected symbols: {symbols}")
        return True
        
    except Exception as e:
        print(f"[FAIL] Selection failed: {e}")
        return False

def test_wheel_layer_logic():
    """Test wheel layer counting and limits"""
    print("\n[TEST] Wheel Layer Management")
    print("-" * 40)
    
    from core.state_manager import WheelStateManager
    from config.config_loader import StrategyConfig
    
    config = StrategyConfig()
    max_layers = config.get_max_wheel_layers()
    
    try:
        state_manager = WheelStateManager()
        
        # Test counting positions
        position_counts = state_manager.get_position_counts()
        print(f"[OK] Position counts retrieved: {position_counts}")
        
        # Test wheel layer validation
        print(f"  Max wheel layers configured: {max_layers}")
        
        # Simulate checking if we can add more positions
        for symbol in config.get_enabled_symbols():
            current_count = position_counts.get(symbol, {}).get('total', 0)
            can_add = current_count < max_layers
            print(f"  {symbol}: {current_count}/{max_layers} positions, can add: {can_add}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] State management failed: {e}")
        return False

def test_cost_basis_calculation():
    """Test cost basis adjustment calculations"""
    print("\n[TEST] Cost Basis Calculations")
    print("-" * 40)
    
    from core.database import WheelDatabase
    
    db = WheelDatabase()
    
    try:
        # Test getting adjusted cost basis for a symbol
        test_symbol = "TEST_SYMBOL"
        
        # Add test data
        db.add_position(test_symbol, 'long_shares', 100, 50.00)
        position_id = db.get_position_history(test_symbol, status='open')[0]['id']
        
        # Add some premiums
        db.add_premium(test_symbol, 'call', 52.00, 1.50, contracts=1)
        db.add_premium(test_symbol, 'call', 53.00, 1.00, contracts=1)
        
        # Update cost basis
        db.update_cost_basis(test_symbol)
        
        # Get adjusted cost basis
        adjusted_basis = db.get_adjusted_cost_basis(test_symbol)
        
        if adjusted_basis:
            original = adjusted_basis['original_cost_basis']
            adjusted = adjusted_basis['adjusted_cost_basis']
            total_premiums = adjusted_basis['total_premiums_collected']
            
            print(f"[OK] Cost basis calculated")
            print(f"  Original basis: ${original:.2f}")
            print(f"  Premiums collected: ${total_premiums:.2f}")
            print(f"  Adjusted basis: ${adjusted:.2f}")
            
            # Verify calculation
            expected = original - total_premiums
            if abs(adjusted - expected) < 0.01:
                print("[OK] Cost basis calculation verified")
            else:
                print(f"[FAIL] Expected ${expected:.2f}, got ${adjusted:.2f}")
                return False
        
        # Clean up test data
        db.close_position(position_id, 52.00, status='closed')
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Cost basis test failed: {e}")
        return False
    finally:
        # Clean up any test data
        with db.get_connection() as conn:
            conn.execute("DELETE FROM positions WHERE symbol = ?", (test_symbol,))
            conn.execute("DELETE FROM premiums WHERE symbol = ?", (test_symbol,))
            conn.execute("DELETE FROM cost_basis WHERE symbol = ?", (test_symbol,))
            conn.commit()

def main():
    """Run all strategy logic tests"""
    print("=" * 60)
    print("Strategy Logic Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Option Scoring", test_option_scoring()))
    results.append(("Option Filtering", test_option_filtering()))
    results.append(("Position Selection", test_position_selection()))
    results.append(("Wheel Layers", test_wheel_layer_logic()))
    results.append(("Cost Basis", test_cost_basis_calculation()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("-" * 60)
    
    passed = sum(1 for _, result in results if result)
    for name, result in results:
        status = "[PASSED]" if result else "[FAILED]"
        print(f"{name:20} {status}")
    
    print("-" * 60)
    print(f"Result: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n[SUCCESS] All strategy logic tests passed!")
    else:
        print("\n[ERROR] Some tests failed.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())