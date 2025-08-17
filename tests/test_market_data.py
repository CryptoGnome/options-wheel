#!/usr/bin/env python
"""Tests for market data retrieval and validation"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import time

def test_market_hours():
    """Test market hours detection"""
    print("\n[TEST] Market Hours Detection")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    
    try:
        client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        clock = client.trading_client.get_clock()
        
        print(f"[OK] Market clock retrieved")
        print(f"  Market open: {clock.is_open}")
        print(f"  Current time: {clock.timestamp}")
        
        if clock.next_open:
            print(f"  Next open: {clock.next_open}")
        if clock.next_close:
            print(f"  Next close: {clock.next_close}")
            
        return True
        
    except Exception as e:
        print(f"[FAIL] Market hours check failed: {e}")
        return False

def test_stock_data_retrieval():
    """Test stock quote and price retrieval"""
    print("\n[TEST] Stock Data Retrieval")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    symbols = config.get_enabled_symbols()
    
    if not symbols:
        print("[SKIP] No symbols configured")
        return True
    
    test_symbol = symbols[0]
    
    try:
        # Get latest quote
        quote = client.get_latest_quote(test_symbol)
        
        if quote:
            print(f"[OK] Retrieved quote for {test_symbol}")
            print(f"  Bid: ${quote.bid_price:.2f} x {quote.bid_size}")
            print(f"  Ask: ${quote.ask_price:.2f} x {quote.ask_size}")
            print(f"  Spread: ${(quote.ask_price - quote.bid_price):.2f}")
            
            # Validate data quality
            if quote.bid_price > 0 and quote.ask_price > quote.bid_price:
                print("[OK] Quote data validated")
            else:
                print("[WARNING] Unusual quote data")
        else:
            print(f"[WARNING] No quote available for {test_symbol}")
            
        return True
        
    except Exception as e:
        print(f"[FAIL] Stock data retrieval failed: {e}")
        return False

def test_option_chain_retrieval():
    """Test option chain data retrieval"""
    print("\n[TEST] Option Chain Retrieval")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    symbols = config.get_enabled_symbols()
    
    if not symbols:
        print("[SKIP] No symbols configured")
        return True
    
    test_symbol = symbols[0]
    
    try:
        # Get option contracts
        puts = client.get_option_contracts(
            underlying_symbol=test_symbol,
            option_type="put"
        )
        
        calls = client.get_option_contracts(
            underlying_symbol=test_symbol,
            option_type="call"
        )
        
        print(f"[OK] Retrieved option chains for {test_symbol}")
        print(f"  Put contracts: {len(puts)}")
        print(f"  Call contracts: {len(calls)}")
        
        # Check if we have options with required data
        if len(puts) > 0:
            sample_put = puts.iloc[0]
            required_fields = ['symbol', 'strike_price', 'expiration_date', 'bid_price', 'ask_price']
            missing = [f for f in required_fields if f not in sample_put or pd.isna(sample_put[f])]
            
            if not missing:
                print("[OK] Option data contains all required fields")
            else:
                print(f"[WARNING] Missing fields: {missing}")
                
        # Test Greeks availability
        if len(puts) > 0 and 'delta' in puts.columns:
            deltas_available = puts['delta'].notna().sum()
            print(f"  Greeks available: {deltas_available}/{len(puts)} contracts")
        else:
            print("[WARNING] No Greeks data available")
            
        return True
        
    except Exception as e:
        print(f"[FAIL] Option chain retrieval failed: {e}")
        # If market is closed, this is expected
        if "market is closed" in str(e).lower():
            print("[INFO] Market is closed - this is expected outside market hours")
            return True
        return False

def test_option_quote_freshness():
    """Test option quote data freshness and validity"""
    print("\n[TEST] Option Quote Freshness")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    import pandas as pd
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    symbols = config.get_enabled_symbols()
    
    if not symbols:
        print("[SKIP] No symbols configured")
        return True
    
    try:
        # Check if market is open first
        clock = client.trading_client.get_clock()
        if not clock.is_open:
            print("[INFO] Market is closed - skipping freshness test")
            return True
            
        test_symbol = symbols[0]
        
        # Get options expiring soon (more liquid)
        target_date = datetime.now() + timedelta(days=7)
        puts = client.get_option_contracts(
            underlying_symbol=test_symbol,
            option_type="put"
        )
        
        if len(puts) == 0:
            print("[SKIP] No options available")
            return True
            
        # Filter to near-term options
        puts['days_to_expiry'] = (puts['expiration_date'] - datetime.now()).dt.days
        near_term = puts[(puts['days_to_expiry'] > 0) & (puts['days_to_expiry'] <= 30)]
        
        if len(near_term) > 0:
            # Check bid-ask spreads
            near_term['spread'] = near_term['ask_price'] - near_term['bid_price']
            near_term['spread_pct'] = (near_term['spread'] / near_term['ask_price']) * 100
            
            avg_spread = near_term['spread_pct'].mean()
            
            print(f"[OK] Analyzed {len(near_term)} near-term options")
            print(f"  Average spread: {avg_spread:.1f}%")
            
            # Check for stale quotes (0 bid)
            zero_bids = (near_term['bid_price'] == 0).sum()
            if zero_bids > 0:
                print(f"[WARNING] {zero_bids} options have zero bid (possibly stale)")
            
            # Check timestamp if available
            if 'timestamp' in near_term.columns:
                latest = near_term['timestamp'].max()
                age = (datetime.now() - latest).total_seconds() / 60
                print(f"  Quote age: {age:.1f} minutes")
                
                if age > 15:
                    print("[WARNING] Quotes may be stale (>15 min old)")
            
        return True
        
    except Exception as e:
        print(f"[FAIL] Quote freshness test failed: {e}")
        return False

def test_historical_data():
    """Test historical price data retrieval"""
    print("\n[TEST] Historical Data Retrieval")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    symbols = config.get_enabled_symbols()
    
    if not symbols:
        print("[SKIP] No symbols configured")
        return True
    
    test_symbol = symbols[0]
    
    try:
        # Get recent bars
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        bars = client.get_stock_bars(
            test_symbol,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            timeframe='1Day'
        )
        
        if bars is not None and not bars.empty:
            print(f"[OK] Retrieved {len(bars)} days of historical data")
            print(f"  Date range: {bars.index[0]} to {bars.index[-1]}")
            print(f"  Latest close: ${bars['close'].iloc[-1]:.2f}")
            
            # Check data quality
            if bars['close'].isna().sum() == 0:
                print("[OK] No missing data points")
            else:
                missing = bars['close'].isna().sum()
                print(f"[WARNING] {missing} missing data points")
                
            # Calculate simple metrics
            volatility = bars['close'].pct_change().std() * (252 ** 0.5) * 100
            print(f"  Annualized volatility: {volatility:.1f}%")
            
        else:
            print("[WARNING] No historical data available")
            
        return True
        
    except Exception as e:
        print(f"[FAIL] Historical data test failed: {e}")
        return False

def test_data_consistency():
    """Test data consistency across different endpoints"""
    print("\n[TEST] Data Consistency Check")
    print("-" * 40)
    
    from core.broker_client import BrokerClient
    from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY
    from config.config_loader import StrategyConfig
    
    client = BrokerClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    config = StrategyConfig()
    symbols = config.get_enabled_symbols()
    
    if not symbols:
        print("[SKIP] No symbols configured")
        return True
    
    test_symbol = symbols[0]
    
    try:
        # Get quote
        quote = client.get_latest_quote(test_symbol)
        
        # Get latest bar
        bars = client.get_stock_bars(
            test_symbol,
            start=(datetime.now() - timedelta(days=2)).isoformat(),
            end=datetime.now().isoformat(),
            timeframe='1Day'
        )
        
        if quote and bars is not None and not bars.empty:
            quote_mid = (quote.bid_price + quote.ask_price) / 2
            last_close = bars['close'].iloc[-1]
            
            price_diff = abs(quote_mid - last_close)
            price_diff_pct = (price_diff / last_close) * 100
            
            print(f"[OK] Data consistency checked")
            print(f"  Quote midpoint: ${quote_mid:.2f}")
            print(f"  Last close: ${last_close:.2f}")
            print(f"  Difference: ${price_diff:.2f} ({price_diff_pct:.1f}%)")
            
            # Large differences might indicate data issues or big moves
            if price_diff_pct > 10:
                print("[WARNING] Large price difference detected")
            else:
                print("[OK] Prices are consistent")
                
        return True
        
    except Exception as e:
        print(f"[FAIL] Consistency check failed: {e}")
        return False

def main():
    """Run all market data tests"""
    print("=" * 60)
    print("Market Data Validation Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Market Hours", test_market_hours()))
    results.append(("Stock Data", test_stock_data_retrieval()))
    results.append(("Option Chains", test_option_chain_retrieval()))
    results.append(("Quote Freshness", test_option_quote_freshness()))
    results.append(("Historical Data", test_historical_data()))
    results.append(("Data Consistency", test_data_consistency()))
    
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
        print("\n[SUCCESS] All market data tests passed!")
    else:
        print("\n[WARNING] Some tests failed - this may be normal outside market hours")
    
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    exit(main())