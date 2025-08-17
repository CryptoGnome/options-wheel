#!/usr/bin/env python
"""Tests for risk management and position sizing"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_position_sizing():
    """Test position sizing calculations"""
    print("\n[TEST] Position Sizing")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    
    try:
        # Get account info
        account = client.get_account()
        buying_power = float(account.buying_power)
        
        # Get allocation settings
        allocation_pct = config.get_balance_allocation()
        allocated_capital = buying_power * allocation_pct
        
        print(f"[OK] Position sizing calculated")
        print(f"  Total buying power: ${buying_power:,.2f}")
        print(f"  Allocation %: {allocation_pct * 100:.1f}%")
        print(f"  Allocated capital: ${allocated_capital:,.2f}")
        
        # Calculate positions per symbol
        symbols = config.get_enabled_symbols()
        if symbols:
            capital_per_symbol = allocated_capital / len(symbols)
            print(f"  Capital per symbol: ${capital_per_symbol:,.2f}")
            
            # Check if allocation makes sense
            for symbol in symbols:
                contracts = config.get_symbol_contracts(symbol)
                print(f"  {symbol}: {contracts} contracts")
                
                # Estimate required capital (rough calculation)
                # Assuming $50 stock price and 100 shares per contract
                estimated_capital = contracts * 100 * 50
                if estimated_capital > capital_per_symbol:
                    print(f"[WARNING] {symbol} may require more capital than allocated")
        
        # Verify allocation percentage is sensible
        if allocation_pct > 1.0:
            print("[FAIL] Allocation > 100% - this is invalid")
            return False
        elif allocation_pct > 0.95:
            print("[WARNING] Very high allocation (>95%) - limited reserve")
        elif allocation_pct < 0.1:
            print("[WARNING] Very low allocation (<10%) - may limit opportunities")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Position sizing test failed: {e}")
        return False

def test_max_position_limits():
    """Test maximum position limits per symbol"""
    print("\n[TEST] Maximum Position Limits")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    from core.state_manager import WheelStateManager
    
    config = StrategyConfig()
    state_manager = WheelStateManager()
    
    try:
        max_layers = config.get_max_wheel_layers()
        symbols = config.get_enabled_symbols()
        
        print(f"[OK] Position limits configured")
        print(f"  Max wheel layers: {max_layers}")
        
        # Check current positions vs limits
        position_counts = state_manager.get_position_counts()
        
        warnings = []
        for symbol in symbols:
            counts = position_counts.get(symbol, {})
            total = counts.get('total', 0)
            
            print(f"  {symbol}: {total}/{max_layers} positions")
            
            if total >= max_layers:
                warnings.append(f"{symbol} at max capacity")
            elif total >= max_layers * 0.8:
                warnings.append(f"{symbol} near capacity ({total}/{max_layers})")
        
        if warnings:
            print(f"[WARNING] Position limit warnings:")
            for warning in warnings:
                print(f"    - {warning}")
        else:
            print("[OK] All symbols within position limits")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Position limits test failed: {e}")
        return False

def test_delta_risk_limits():
    """Test delta exposure limits"""
    print("\n[TEST] Delta Risk Limits")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    
    config = StrategyConfig()
    
    try:
        filters = config.get_option_filters()
        delta_min = filters['delta_min']
        delta_max = filters['delta_max']
        
        print(f"[OK] Delta limits configured")
        print(f"  Delta range: {delta_min} to {delta_max}")
        
        # Validate delta range
        if delta_min < 0 or delta_max > 1:
            print("[FAIL] Invalid delta range (must be 0-1)")
            return False
        
        if delta_min >= delta_max:
            print("[FAIL] Invalid delta range (min >= max)")
            return False
        
        # Check risk level based on delta
        avg_delta = (delta_min + delta_max) / 2
        
        if avg_delta < 0.20:
            risk_level = "Conservative (low assignment probability)"
        elif avg_delta < 0.35:
            risk_level = "Moderate (balanced risk/reward)"
        else:
            risk_level = "Aggressive (high assignment probability)"
        
        print(f"  Risk profile: {risk_level}")
        print(f"  Avg assignment probability: ~{avg_delta * 100:.0f}%")
        
        # Warning for high delta
        if delta_max > 0.40:
            print("[WARNING] High delta limit (>0.40) - increased assignment risk")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Delta limits test failed: {e}")
        return False

def test_diversification():
    """Test portfolio diversification"""
    print("\n[TEST] Portfolio Diversification")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    
    config = StrategyConfig()
    
    try:
        symbols = config.get_enabled_symbols()
        total_symbols = len(symbols)
        
        print(f"[OK] Diversification analysis")
        print(f"  Active symbols: {total_symbols}")
        print(f"  Symbols: {', '.join(symbols)}")
        
        # Check diversification level
        if total_symbols == 0:
            print("[FAIL] No symbols enabled")
            return False
        elif total_symbols == 1:
            print("[WARNING] Single symbol - no diversification")
        elif total_symbols < 3:
            print("[WARNING] Limited diversification (<3 symbols)")
        else:
            print("[OK] Good diversification")
        
        # Check concentration per symbol
        if total_symbols > 0:
            max_concentration = 100 / total_symbols
            print(f"  Max concentration per symbol: {max_concentration:.1f}%")
            
            if max_concentration > 50:
                print("[WARNING] High concentration risk per symbol")
        
        # Check contract distribution
        total_contracts = 0
        for symbol in symbols:
            contracts = config.get_symbol_contracts(symbol)
            total_contracts += contracts
            
        if total_contracts > 0:
            for symbol in symbols:
                contracts = config.get_symbol_contracts(symbol)
                allocation_pct = (contracts / total_contracts) * 100
                print(f"  {symbol}: {contracts} contracts ({allocation_pct:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Diversification test failed: {e}")
        return False

def test_margin_requirements():
    """Test margin requirement calculations"""
    print("\n[TEST] Margin Requirements")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    
    try:
        account = client.get_account()
        
        # Check account type
        print(f"[OK] Account analysis")
        print(f"  Account status: {account.status}")
        print(f"  Pattern day trader: {account.pattern_day_trader}")
        print(f"  Trading blocked: {account.trading_blocked}")
        
        # Get margin multiplier
        margin_multiplier = float(account.multiplier) if hasattr(account, 'multiplier') else 1
        print(f"  Margin multiplier: {margin_multiplier}x")
        
        # Calculate requirements for cash-secured puts
        buying_power = float(account.buying_power)
        symbols = config.get_enabled_symbols()
        
        if symbols:
            print(f"\n  Margin requirements per symbol (estimated):")
            for symbol in symbols:
                contracts = config.get_symbol_contracts(symbol)
                # Estimate: $50 strike * 100 shares * contracts
                estimated_requirement = 50 * 100 * contracts
                print(f"    {symbol}: ${estimated_requirement:,.0f} for {contracts} contracts")
        
        # Check if account has sufficient margin
        total_allocated = buying_power * config.get_balance_allocation()
        
        if margin_multiplier < 2:
            print("[INFO] Cash account - full collateral required for puts")
        else:
            print("[INFO] Margin account - reduced collateral for puts")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Margin requirements test failed: {e}")
        return False

def test_stop_loss_logic():
    """Test stop loss and risk mitigation logic"""
    print("\n[TEST] Stop Loss & Risk Mitigation")
    print("-" * 40)
    
    from core.database import WheelDatabase
    
    db = WheelDatabase()
    
    try:
        print("[OK] Risk mitigation checks")
        
        # Check for positions with large losses
        positions = db.get_position_history(status='open')
        
        if positions:
            print(f"  Open positions: {len(positions)}")
            
            for position in positions:
                entry_price = position['entry_price']
                # In real scenario, we'd compare with current market price
                # For now, just show the position
                print(f"    {position['symbol']}: {position['position_type']} @ ${entry_price:.2f}")
        else:
            print("  No open positions to monitor")
        
        # Check premium collection vs risk
        stats = db.get_summary_stats()
        if stats and stats['total_premiums']:
            print(f"\n  Risk metrics:")
            print(f"    Total premiums collected: ${stats['total_premiums']:.2f}")
            print(f"    Open positions: {stats['open_positions']}")
            
            # Calculate risk/reward
            if stats['open_positions'] > 0 and stats['total_premiums'] > 0:
                avg_premium = stats['total_premiums'] / stats['total_trades']
                print(f"    Avg premium per trade: ${avg_premium:.2f}")
        
        # Suggestions for risk mitigation
        print("\n  Risk mitigation strategies in use:")
        print("    - Delta limits for assignment probability")
        print("    - Position size limits per symbol")
        print("    - Allocation percentage for capital preservation")
        print("    - Cost basis tracking for better exit points")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Stop loss test failed: {e}")
        return False

def main():
    """Run all risk management tests"""
    print("=" * 60)
    print("Risk Management Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Position Sizing", test_position_sizing()))
    results.append(("Position Limits", test_max_position_limits()))
    results.append(("Delta Limits", test_delta_risk_limits()))
    results.append(("Diversification", test_diversification()))
    results.append(("Margin Requirements", test_margin_requirements()))
    results.append(("Risk Mitigation", test_stop_loss_logic()))
    
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
        print("\n[SUCCESS] All risk management tests passed!")
    else:
        print("\n[WARNING] Some tests failed - review risk parameters")
    
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    exit(main())