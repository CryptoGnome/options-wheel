#!/usr/bin/env python
"""Tests for database integrity and operations"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import sqlite3

def test_database_structure():
    """Test database tables and schema"""
    print("\n[TEST] Database Structure")
    print("-" * 40)
    
    from core.database import WheelDatabase
    
    db = WheelDatabase()
    
    try:
        with db.get_connection() as conn:
            # Check all required tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            required_tables = ['positions', 'premiums', 'cost_basis', 'trade_history']
            
            print(f"[OK] Found {len(tables)} tables")
            
            missing = []
            for table in required_tables:
                if table in tables:
                    print(f"  [OK] Table '{table}' exists")
                else:
                    print(f"  [FAIL] Table '{table}' missing")
                    missing.append(table)
            
            if missing:
                print(f"[FAIL] Missing tables: {missing}")
                return False
            
            # Check table schemas
            for table in required_tables:
                cursor = conn.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                print(f"\n  {table} columns: {len(columns)}")
                
                # Verify critical columns
                col_names = [col[1] for col in columns]
                
                if table == 'positions':
                    required = ['id', 'symbol', 'position_type', 'quantity', 'entry_price']
                    for col in required:
                        if col not in col_names:
                            print(f"    [FAIL] Missing column '{col}'")
                            return False
                    print(f"    [OK] All required columns present")
            
        return True
        
    except Exception as e:
        print(f"[FAIL] Database structure test failed: {e}")
        return False

def test_transaction_integrity():
    """Test database transaction handling"""
    print("\n[TEST] Transaction Integrity")
    print("-" * 40)
    
    from core.database import WheelDatabase
    
    db = WheelDatabase()
    test_symbol = "TEST_TRANS"
    
    try:
        # Start a transaction
        with db.get_connection() as conn:
            # Insert test position
            cursor = conn.execute(
                """INSERT INTO positions 
                   (symbol, position_type, quantity, entry_price, entry_date, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (test_symbol, 'test', 100, 50.00, datetime.now(), 'test')
            )
            position_id = cursor.lastrowid
            
            # Insert related premium
            conn.execute(
                """INSERT INTO premiums
                   (symbol, option_type, strike_price, premium, contracts, collected_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (test_symbol, 'put', 50.00, 1.50, 1, datetime.now())
            )
            
            # Verify within transaction
            cursor = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE symbol = ?",
                (test_symbol,)
            )
            count = cursor.fetchone()[0]
            
            if count == 1:
                print("[OK] Transaction insert successful")
            else:
                print("[FAIL] Transaction insert failed")
                return False
        
        # Verify after commit
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE symbol = ?",
                (test_symbol,)
            )
            count = cursor.fetchone()[0]
            
            if count == 1:
                print("[OK] Transaction committed successfully")
            else:
                print("[FAIL] Transaction not committed")
                return False
            
            # Clean up test data
            conn.execute("DELETE FROM positions WHERE symbol = ?", (test_symbol,))
            conn.execute("DELETE FROM premiums WHERE symbol = ?", (test_symbol,))
            conn.commit()
            print("[OK] Test data cleaned up")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Transaction test failed: {e}")
        # Clean up on failure
        try:
            with db.get_connection() as conn:
                conn.execute("DELETE FROM positions WHERE symbol = ?", (test_symbol,))
                conn.execute("DELETE FROM premiums WHERE symbol = ?", (test_symbol,))
                conn.commit()
        except:
            pass
        return False

def test_data_consistency():
    """Test data consistency and relationships"""
    print("\n[TEST] Data Consistency")
    print("-" * 40)
    
    from core.database import WheelDatabase
    
    db = WheelDatabase()
    
    try:
        with db.get_connection() as conn:
            # Check for orphaned records
            
            # Check cost_basis references valid positions
            cursor = conn.execute("""
                SELECT cb.symbol, cb.position_id 
                FROM cost_basis cb
                LEFT JOIN positions p ON cb.position_id = p.id
                WHERE p.id IS NULL
            """)
            orphaned = cursor.fetchall()
            
            if orphaned:
                print(f"[WARNING] Found {len(orphaned)} orphaned cost_basis records")
                for symbol, pos_id in orphaned:
                    print(f"    Symbol: {symbol}, Position ID: {pos_id}")
            else:
                print("[OK] No orphaned cost_basis records")
            
            # Check for positions without cost basis tracking
            cursor = conn.execute("""
                SELECT p.id, p.symbol, p.position_type
                FROM positions p
                LEFT JOIN cost_basis cb ON p.id = cb.position_id
                WHERE p.position_type = 'long_shares' 
                AND p.status = 'open'
                AND cb.position_id IS NULL
            """)
            missing_cb = cursor.fetchall()
            
            if missing_cb:
                print(f"[WARNING] {len(missing_cb)} positions missing cost basis")
                for pos_id, symbol, pos_type in missing_cb:
                    print(f"    ID: {pos_id}, Symbol: {symbol}, Type: {pos_type}")
            else:
                print("[OK] All long positions have cost basis tracking")
            
            # Check data types and ranges
            cursor = conn.execute("""
                SELECT COUNT(*) FROM positions 
                WHERE entry_price <= 0 OR quantity <= 0
            """)
            invalid_count = cursor.fetchone()[0]
            
            if invalid_count > 0:
                print(f"[FAIL] Found {invalid_count} positions with invalid prices/quantities")
                return False
            else:
                print("[OK] All positions have valid prices and quantities")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Consistency test failed: {e}")
        return False

def test_query_performance():
    """Test database query performance"""
    print("\n[TEST] Query Performance")
    print("-" * 40)
    
    from core.database import WheelDatabase
    import time
    
    db = WheelDatabase()
    
    try:
        # Test common query performance
        queries = [
            ("Active positions", "SELECT * FROM positions WHERE status = 'open'"),
            ("Recent premiums", "SELECT * FROM premiums WHERE collected_date > date('now', '-30 days')"),
            ("Cost basis join", """
                SELECT p.*, cb.adjusted_cost_basis 
                FROM positions p 
                LEFT JOIN cost_basis cb ON p.id = cb.position_id
                WHERE p.status = 'open'
            """),
            ("Summary stats", """
                SELECT 
                    COUNT(DISTINCT symbol) as symbols,
                    COUNT(*) as total_trades,
                    SUM(premium * contracts * 100) as total_premium
                FROM premiums
            """)
        ]
        
        print("[OK] Testing query performance")
        
        with db.get_connection() as conn:
            for name, query in queries:
                start = time.time()
                cursor = conn.execute(query)
                results = cursor.fetchall()
                elapsed = (time.time() - start) * 1000
                
                status = "[OK]" if elapsed < 100 else "[SLOW]"
                print(f"  {status} {name}: {elapsed:.1f}ms ({len(results)} rows)")
                
                if elapsed > 100:
                    print(f"    [WARNING] Query taking >100ms")
        
        # Check for indexes
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row[0] for row in cursor.fetchall()]
            
            print(f"\n  Database indexes: {len(indexes)}")
            if len(indexes) == 0:
                print("    [WARNING] No indexes found - queries may be slow")
            else:
                for idx in indexes:
                    print(f"    - {idx}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Performance test failed: {e}")
        return False

def test_backup_restore():
    """Test database backup and restore capability"""
    print("\n[TEST] Backup & Restore")
    print("-" * 40)
    
    from core.database import WheelDatabase
    import shutil
    from pathlib import Path
    
    db = WheelDatabase()
    
    try:
        # Get database path
        db_path = Path("data/wheel_strategy.db")
        backup_path = Path("data/wheel_strategy_test_backup.db")
        
        # Create backup
        if db_path.exists():
            shutil.copy2(db_path, backup_path)
            print(f"[OK] Database backed up to {backup_path}")
            
            # Verify backup
            if backup_path.exists():
                backup_size = backup_path.stat().st_size
                original_size = db_path.stat().st_size
                
                if backup_size == original_size:
                    print(f"[OK] Backup verified ({backup_size:,} bytes)")
                else:
                    print(f"[WARNING] Backup size mismatch")
                
                # Test backup is readable
                test_conn = sqlite3.connect(backup_path)
                cursor = test_conn.execute("SELECT COUNT(*) FROM positions")
                count = cursor.fetchone()[0]
                test_conn.close()
                
                print(f"[OK] Backup readable ({count} positions)")
                
                # Clean up test backup
                backup_path.unlink()
                print("[OK] Test backup cleaned up")
            else:
                print("[FAIL] Backup file not created")
                return False
        else:
            print("[SKIP] No database to backup")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Backup test failed: {e}")
        # Clean up on failure
        try:
            if backup_path.exists():
                backup_path.unlink()
        except:
            pass
        return False

def test_concurrent_access():
    """Test concurrent database access"""
    print("\n[TEST] Concurrent Access")
    print("-" * 40)
    
    from core.database import WheelDatabase
    import threading
    import time
    
    results = []
    errors = []
    
    def concurrent_read(thread_id):
        try:
            db = WheelDatabase()
            with db.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM positions")
                count = cursor.fetchone()[0]
                results.append((thread_id, count))
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    try:
        # Create multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=concurrent_read, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=5)
        
        if errors:
            print(f"[FAIL] Concurrent access errors: {len(errors)}")
            for thread_id, error in errors:
                print(f"    Thread {thread_id}: {error}")
            return False
        else:
            print(f"[OK] {len(threads)} concurrent reads successful")
            
            # Verify all threads got same result
            if results:
                counts = [count for _, count in results]
                if len(set(counts)) == 1:
                    print(f"[OK] All threads read consistent data")
                else:
                    print(f"[WARNING] Inconsistent reads: {counts}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Concurrent access test failed: {e}")
        return False

def main():
    """Run all database tests"""
    print("=" * 60)
    print("Database Integrity Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Database Structure", test_database_structure()))
    results.append(("Transaction Integrity", test_transaction_integrity()))
    results.append(("Data Consistency", test_data_consistency()))
    results.append(("Query Performance", test_query_performance()))
    results.append(("Backup & Restore", test_backup_restore()))
    results.append(("Concurrent Access", test_concurrent_access()))
    
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
        print("\n[SUCCESS] All database tests passed!")
    else:
        print("\n[WARNING] Some tests failed - review database integrity")
    
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    exit(main())