#!/usr/bin/env python
"""Tests for configuration validation and settings"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from pathlib import Path

def test_config_file_exists():
    """Test configuration files exist"""
    print("\n[TEST] Configuration Files")
    print("-" * 40)
    
    required_files = [
        ("../config/strategy_config.json", "Strategy configuration"),
        ("../.env", "API credentials")
    ]
    
    all_exist = True
    for file_path, description in required_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            print(f"[OK] {description}: {file_path} ({size} bytes)")
        else:
            print(f"[FAIL] Missing {description}: {file_path}")
            all_exist = False
    
    return all_exist

def test_json_validity():
    """Test JSON configuration is valid"""
    print("\n[TEST] JSON Configuration Validity")
    print("-" * 40)
    
    config_path = Path("../config/strategy_config.json")
    
    if not config_path.exists():
        print("[FAIL] Configuration file not found")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        print("[OK] JSON is valid and parseable")
        print(f"  Top-level keys: {', '.join(config.keys())}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"[FAIL] Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error reading config: {e}")
        return False

def test_required_settings():
    """Test all required settings are present"""
    print("\n[TEST] Required Settings")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    
    try:
        config = StrategyConfig()
        
        # Test required settings exist and are valid
        tests = [
            ("Balance Allocation", lambda: config.get_balance_allocation(), 
             lambda v: 0 <= v <= 1, "Must be between 0 and 1"),
            ("Max Wheel Layers", lambda: config.get_max_wheel_layers(),
             lambda v: v > 0, "Must be positive"),
            ("Enabled Symbols", lambda: config.get_enabled_symbols(),
             lambda v: len(v) > 0, "At least one symbol required"),
            ("Option Filters", lambda: config.get_option_filters(),
             lambda v: all(k in v for k in ['delta_min', 'delta_max']), "Must have delta limits")
        ]
        
        all_valid = True
        for name, getter, validator, error_msg in tests:
            try:
                value = getter()
                if validator(value):
                    print(f"[OK] {name}: {value}")
                else:
                    print(f"[FAIL] {name}: {error_msg} (got {value})")
                    all_valid = False
            except Exception as e:
                print(f"[FAIL] {name}: {e}")
                all_valid = False
        
        return all_valid
        
    except Exception as e:
        print(f"[FAIL] Config validation failed: {e}")
        return False

def test_symbol_configuration():
    """Test symbol-specific configuration"""
    print("\n[TEST] Symbol Configuration")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    
    try:
        config = StrategyConfig()
        symbols = config.get_enabled_symbols()
        
        if not symbols:
            print("[FAIL] No symbols configured")
            return False
        
        print(f"[OK] {len(symbols)} symbols configured")
        
        all_valid = True
        for symbol in symbols:
            # Check symbol format
            if not symbol or not symbol.isupper():
                print(f"[FAIL] Invalid symbol format: {symbol}")
                all_valid = False
                continue
            
            # Check contracts configuration
            contracts = config.get_symbol_contracts(symbol)
            
            if contracts <= 0:
                print(f"[FAIL] {symbol}: Invalid contracts ({contracts})")
                all_valid = False
            else:
                print(f"[OK] {symbol}: {contracts} contracts")
            
            # Check if symbol is actually enabled
            symbol_config = config.config.get('symbols', {}).get(symbol, {})
            if not symbol_config.get('enabled', False):
                print(f"[WARNING] {symbol}: In enabled list but marked disabled")
        
        return all_valid
        
    except Exception as e:
        print(f"[FAIL] Symbol config test failed: {e}")
        return False

def test_filter_ranges():
    """Test option filter ranges are valid"""
    print("\n[TEST] Option Filter Ranges")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    
    try:
        config = StrategyConfig()
        filters = config.get_option_filters()
        
        print("[OK] Option filters loaded")
        
        # Validate each filter
        validations = [
            ("Delta range", 
             filters.get('delta_min', 0), filters.get('delta_max', 1),
             lambda min_v, max_v: 0 <= min_v < max_v <= 1),
            ("DTE range",
             filters.get('expiration_min_days', 0), filters.get('expiration_max_days', 30),
             lambda min_v, max_v: 0 <= min_v < max_v <= 365),
            ("Strike range",
             filters.get('strike_min', 0), filters.get('strike_max', float('inf')),
             lambda min_v, max_v: min_v >= 0 and min_v < max_v)
        ]
        
        all_valid = True
        for name, min_val, max_val, validator in validations:
            if validator(min_val, max_val):
                print(f"  [OK] {name}: {min_val} to {max_val}")
            else:
                print(f"  [FAIL] {name}: Invalid range ({min_val} to {max_val})")
                all_valid = False
        
        # Check other filters
        oi_min = filters.get('open_interest_min', 0)
        if oi_min >= 0:
            print(f"  [OK] Min open interest: {oi_min}")
        else:
            print(f"  [FAIL] Invalid open interest minimum: {oi_min}")
            all_valid = False
        
        bid_min = filters.get('bid_min', 0)
        if bid_min >= 0:
            print(f"  [OK] Min bid price: ${bid_min}")
        else:
            print(f"  [FAIL] Invalid bid minimum: {bid_min}")
            all_valid = False
        
        return all_valid
        
    except Exception as e:
        print(f"[FAIL] Filter validation failed: {e}")
        return False

def test_environment_variables():
    """Test environment variables are set"""
    print("\n[TEST] Environment Variables")
    print("-" * 40)
    
    import os
    from dotenv import load_dotenv
    
    load_dotenv(override=True)
    
    required_vars = [
        ("ALPACA_API_KEY", "API Key"),
        ("ALPACA_SECRET_KEY", "Secret Key"),
        ("IS_PAPER", "Paper trading flag")
    ]
    
    all_set = True
    for var_name, description in required_vars:
        value = os.getenv(var_name)
        
        if value:
            # Don't print actual values for security
            if "KEY" in var_name:
                display = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            else:
                display = value
            print(f"[OK] {description}: {display}")
        else:
            print(f"[FAIL] Missing {description}: {var_name}")
            all_set = False
    
    # Validate IS_PAPER value
    is_paper = os.getenv("IS_PAPER", "true").lower()
    if is_paper not in ["true", "false"]:
        print(f"[FAIL] Invalid IS_PAPER value: {is_paper}")
        all_set = False
    elif is_paper == "false":
        print("[WARNING] Paper trading is DISABLED - using real money!")
    
    return all_set

def test_config_consistency():
    """Test configuration internal consistency"""
    print("\n[TEST] Configuration Consistency")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    
    try:
        config = StrategyConfig()
        
        # Check allocation vs wheel layers logic
        allocation = config.get_balance_allocation()
        max_layers = config.get_max_wheel_layers()
        symbols = config.get_enabled_symbols()
        
        if symbols:
            # Calculate effective allocation per position
            max_positions = len(symbols) * max_layers
            allocation_per_position = allocation / max_positions if max_positions > 0 else 0
            
            print(f"[OK] Configuration analysis:")
            print(f"  Total allocation: {allocation * 100:.1f}%")
            print(f"  Max positions: {max_positions} ({len(symbols)} symbols × {max_layers} layers)")
            print(f"  Allocation per position: {allocation_per_position * 100:.1f}%")
            
            # Warnings for potential issues
            if allocation_per_position < 0.01:
                print("[WARNING] Very low allocation per position (<1%)")
            elif allocation_per_position > 0.5:
                print("[WARNING] Very high allocation per position (>50%)")
            
            if allocation > 0.95 and max_layers > 1:
                print("[WARNING] High allocation with multiple layers - limited reserve")
        
        # Check filter consistency
        filters = config.get_option_filters()
        delta_range = filters['delta_max'] - filters['delta_min']
        
        if delta_range < 0.05:
            print("[WARNING] Very narrow delta range - may limit opportunities")
        elif delta_range > 0.5:
            print("[WARNING] Very wide delta range - inconsistent risk profile")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Consistency check failed: {e}")
        return False

def test_config_modifications():
    """Test configuration can be modified and reloaded"""
    print("\n[TEST] Configuration Modification")
    print("-" * 40)
    
    from config.config_loader import StrategyConfig
    import json
    import tempfile
    import shutil
    
    config_path = Path("../config/strategy_config.json")
    
    if not config_path.exists():
        print("[SKIP] No config file to test")
        return True
    
    # Create backup
    backup_path = config_path.with_suffix('.json.test_backup')
    
    try:
        # Backup original
        shutil.copy2(config_path, backup_path)
        print("[OK] Config backed up")
        
        # Load and modify
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Make a test modification
        original_allocation = config_data.get('balance_settings', {}).get('allocation_percentage', 0.5)
        test_allocation = 0.42
        config_data['balance_settings']['allocation_percentage'] = test_allocation
        
        # Save modification
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Reload and verify
        config = StrategyConfig()
        new_allocation = config.get_balance_allocation()
        
        if abs(new_allocation - test_allocation) < 0.001:
            print(f"[OK] Config modification successful ({test_allocation})")
        else:
            print(f"[FAIL] Config not reloaded properly")
            return False
        
        # Restore original
        shutil.copy2(backup_path, config_path)
        config = StrategyConfig()
        restored_allocation = config.get_balance_allocation()
        
        if abs(restored_allocation - original_allocation) < 0.001:
            print(f"[OK] Config restored ({original_allocation})")
        else:
            print(f"[WARNING] Config restore issue")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Modification test failed: {e}")
        # Try to restore on failure
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, config_path)
        except:
            pass
        return False
    finally:
        # Clean up backup
        if backup_path.exists():
            backup_path.unlink()

def main():
    """Run all configuration tests"""
    print("=" * 60)
    print("Configuration Validation Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Config Files", test_config_file_exists()))
    results.append(("JSON Validity", test_json_validity()))
    results.append(("Required Settings", test_required_settings()))
    results.append(("Symbol Config", test_symbol_configuration()))
    results.append(("Filter Ranges", test_filter_ranges()))
    results.append(("Environment Vars", test_environment_variables()))
    results.append(("Config Consistency", test_config_consistency()))
    results.append(("Config Modification", test_config_modifications()))
    
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
        print("\n[SUCCESS] All configuration tests passed!")
    else:
        print("\n[ERROR] Some tests failed - review configuration")
    
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    exit(main())