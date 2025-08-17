#!/usr/bin/env python
"""Master test runner for all options wheel tests"""

import sys
import os
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_test_module(module_name, description):
    """Run a single test module and return results"""
    print("\n" + "=" * 70)
    print(f"Running: {description}")
    print("=" * 70)
    
    start_time = time.time()
    
    try:
        module = __import__(module_name)
        result = module.main()
        elapsed = time.time() - start_time
        
        return {
            'name': description,
            'module': module_name,
            'passed': result == 0,
            'time': elapsed,
            'error': None
        }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n[ERROR] Test module failed to run: {e}")
        
        return {
            'name': description,
            'module': module_name,
            'passed': False,
            'time': elapsed,
            'error': str(e)
        }

def main():
    """Run all test suites"""
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#" + " " * 15 + "OPTIONS WHEEL STRATEGY TEST SUITE" + " " * 19 + "#")
    print("#" + " " * 68 + "#")
    print("#" * 70)
    
    print(f"\nTest run started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python version: {sys.version.split()[0]}")
    print(f"Working directory: {os.getcwd()}")
    
    # Define test modules to run in order
    test_modules = [
        ('test_setup', 'Setup & Environment Tests'),
        ('test_configuration', 'Configuration Validation'),
        ('test_database', 'Database Integrity Tests'),
        ('test_strategy_logic', 'Strategy Logic Tests'),
        ('test_risk_management', 'Risk Management Tests'),
        ('test_market_data', 'Market Data Validation'),
    ]
    
    # Check if we're in the tests directory
    if Path.cwd().name != 'tests':
        os.chdir('tests')
        print(f"Changed to tests directory: {os.getcwd()}")
    
    # Run all tests
    results = []
    total_start = time.time()
    
    for module, description in test_modules:
        result = run_test_module(module, description)
        results.append(result)
        
        # Brief pause between test suites
        time.sleep(0.5)
    
    total_time = time.time() - total_start
    
    # Generate summary report
    print("\n" + "#" * 70)
    print("#" + " " * 25 + "TEST SUITE SUMMARY" + " " * 25 + "#")
    print("#" * 70)
    
    # Detailed results
    print("\nDetailed Results:")
    print("-" * 70)
    print(f"{'Test Suite':<35} {'Status':<10} {'Time':<10} {'Notes':<15}")
    print("-" * 70)
    
    passed_count = 0
    failed_tests = []
    
    for result in results:
        status = "[PASS]" if result['passed'] else "[FAIL]"
        time_str = f"{result['time']:.2f}s"
        notes = "" if result['passed'] else (result['error'][:12] + "..." if result['error'] else "Failed")
        
        print(f"{result['name']:<35} {status:<10} {time_str:<10} {notes:<15}")
        
        if result['passed']:
            passed_count += 1
        else:
            failed_tests.append(result['name'])
    
    print("-" * 70)
    
    # Overall summary
    print(f"\nOverall Results:")
    print(f"  Total test suites: {len(results)}")
    print(f"  Passed: {passed_count}")
    print(f"  Failed: {len(results) - passed_count}")
    print(f"  Success rate: {(passed_count/len(results)*100):.1f}%")
    print(f"  Total time: {total_time:.2f} seconds")
    
    # Critical checks
    print("\n" + "=" * 70)
    print("Critical System Checks:")
    print("-" * 70)
    
    critical_checks = [
        ("Environment", 'test_setup' in [r['module'] for r in results if r['passed']]),
        ("Configuration", 'test_configuration' in [r['module'] for r in results if r['passed']]),
        ("Database", 'test_database' in [r['module'] for r in results if r['passed']]),
    ]
    
    all_critical_passed = True
    for check_name, passed in critical_checks:
        status = "[OK]" if passed else "[CRITICAL]"
        print(f"  {check_name:<20} {status}")
        if not passed:
            all_critical_passed = False
    
    # Final verdict
    print("\n" + "=" * 70)
    
    if passed_count == len(results):
        print("[SUCCESS] All tests passed! System is ready for trading.")
        print("\nYou can now run the strategy with: run-strategy")
        return 0
    elif all_critical_passed:
        print("[WARNING] Some tests failed, but critical systems are operational.")
        print("\nFailed test suites:")
        for test in failed_tests:
            print(f"  - {test}")
        print("\nThe system can run but review the failures above.")
        return 1
    else:
        print("[FAILURE] Critical system tests failed. Do not run the strategy.")
        print("\nCritical issues must be resolved before trading.")
        print("Failed test suites:")
        for test in failed_tests:
            print(f"  - {test}")
        return 2

if __name__ == "__main__":
    exit_code = main()
    
    # Provide guidance based on results
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("Next steps:")
        print("  1. Review your configuration in config/strategy_config.json")
        print("  2. Ensure you're comfortable with the risk parameters")
        print("  3. Run: run-strategy --help for execution options")
        print("  4. Start with: run-strategy (paper trading mode)")
    elif exit_code == 1:
        print("Recommended actions:")
        print("  1. Review the failed test output above")
        print("  2. Run individual test files for more details")
        print("  3. Fix any configuration or data issues")
        print("  4. Re-run this test suite")
    else:
        print("Required actions:")
        print("  1. Fix critical issues identified above")
        print("  2. Ensure API keys are configured in .env")
        print("  3. Verify database integrity")
        print("  4. Re-run: python run_all_tests.py")
    
    print("=" * 70)
    exit(exit_code)