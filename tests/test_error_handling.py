"""
Test error handling and thread safety improvements.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import threading
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.retry_decorator import retry_on_failure, CircuitBreaker, RetryException
from core.thread_safe_manager import ThreadSafeStateManager
from core.database import WheelDatabase
import tempfile
import sqlite3

class TestRetryDecorator(unittest.TestCase):
    """Test retry decorator functionality."""
    
    def test_retry_on_success(self):
        """Test that successful calls don't retry."""
        call_count = 0
        
        @retry_on_failure(max_attempts=3)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_function()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 1)
    
    def test_retry_on_failure_recovers(self):
        """Test that function recovers after transient failure."""
        call_count = 0
        
        @retry_on_failure(max_attempts=3, base_delay=0.01)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"
        
        result = flaky_function()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
    
    def test_retry_exhaustion(self):
        """Test that retries are exhausted after max attempts."""
        call_count = 0
        
        @retry_on_failure(max_attempts=3, base_delay=0.01)
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent error")
        
        with self.assertRaises(RetryException):
            failing_function()
        
        self.assertEqual(call_count, 3)

class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker functionality."""
    
    def test_circuit_breaker_opens(self):
        """Test that circuit breaker opens after threshold failures."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        
        def failing_function():
            raise ConnectionError("API error")
        
        # First two failures should work
        for i in range(2):
            with self.assertRaises(ConnectionError):
                breaker.call(failing_function)
        
        # Circuit should now be open
        self.assertEqual(breaker.state, "open")
        
        # Next call should fail immediately
        with self.assertRaises(RetryException):
            breaker.call(failing_function)
    
    def test_circuit_breaker_recovers(self):
        """Test that circuit breaker recovers after timeout."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        
        call_count = 0
        
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("First call fails")
            return "success"
        
        # First call fails, opening the circuit
        with self.assertRaises(ConnectionError):
            breaker.call(test_function)
        
        self.assertEqual(breaker.state, "open")
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Circuit should recover
        result = breaker.call(test_function)
        self.assertEqual(result, "success")
        self.assertEqual(breaker.state, "closed")

class TestThreadSafeStateManager(unittest.TestCase):
    """Test thread-safe state manager."""
    
    def setUp(self):
        self.manager = ThreadSafeStateManager()
    
    def test_concurrent_state_updates(self):
        """Test that concurrent state updates don't cause race conditions."""
        mock_positions = [
            Mock(asset_class=Mock(value="us_equity"), symbol="AAPL", qty=100, 
                 avg_entry_price=150.0, side=Mock(value="long"))
        ]
        
        errors = []
        
        def update_state_multiple_times():
            try:
                for _ in range(10):
                    self.manager.update_state(mock_positions)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=update_state_multiple_times)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check no errors occurred
        self.assertEqual(len(errors), 0)
    
    def test_position_counting_thread_safety(self):
        """Test thread-safe position counting."""
        mock_positions = [
            Mock(asset_class=Mock(value="us_option"), symbol="AAPL241220P00150000", 
                 qty=-1, side=Mock(value="short"))
        ]
        
        results = []
        
        def count_positions():
            result = self.manager.count_positions_by_symbol(mock_positions)
            results.append(result)
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=count_positions)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All results should be identical
        self.assertEqual(len(results), 10)
        first_result = results[0]
        for result in results[1:]:
            self.assertEqual(result, first_result)

class TestDatabaseThreadSafety(unittest.TestCase):
    """Test database thread safety improvements."""
    
    def setUp(self):
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db = WheelDatabase(db_path=self.temp_db.name)
    
    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_concurrent_writes(self):
        """Test that concurrent writes don't cause database locks."""
        from datetime import date, timedelta
        errors = []
        
        def add_premiums(thread_id):
            try:
                for i in range(5):
                    self.db.add_premium(
                        symbol=f"TEST{thread_id}",
                        option_type='P',
                        strike_price=100.0 + i,
                        premium=1.0 + i * 0.1,
                        contracts=1,
                        expiration_date=date.today() + timedelta(days=30)
                    )
                    time.sleep(0.01)
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=add_premiums, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Verify all records were added
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM premiums")
            result = cursor.fetchone()
            self.assertEqual(result['count'], 25)  # 5 threads * 5 premiums each
    
    def test_database_retry_on_lock(self):
        """Test that database retries on lock."""
        from datetime import date, timedelta
        # Simulate a locked database
        lock_conn = sqlite3.connect(self.temp_db.name)
        lock_conn.execute("BEGIN EXCLUSIVE")
        
        # Try to add a premium (should retry and eventually fail)
        start_time = time.time()
        
        try:
            # This should retry 3 times before failing
            self.db.add_premium(
                symbol="TEST",
                option_type='P',
                strike_price=100.0,
                premium=1.0,
                expiration_date=date.today() + timedelta(days=30)
            )
        except sqlite3.OperationalError:
            pass  # Expected
        
        elapsed = time.time() - start_time
        
        # Should have taken at least some time for retries
        self.assertGreater(elapsed, 0.1)
        
        # Release the lock
        lock_conn.rollback()
        lock_conn.close()
        
        # Now it should work
        result = self.db.add_premium(
            symbol="TEST",
            option_type='P',
            strike_price=100.0,
            premium=1.0,
            expiration_date=date.today() + timedelta(days=30)
        )
        self.assertIsNotNone(result)

class TestBrokerClientValidation(unittest.TestCase):
    """Test broker client API response validation."""
    
    @patch('core.broker_client.TradingClientSigned')
    @patch('core.broker_client.StockHistoricalDataClientSigned')
    @patch('core.broker_client.OptionHistoricalDataClientSigned')
    def test_invalid_account_response(self, mock_option, mock_stock, mock_trading):
        """Test handling of invalid account response."""
        from core.broker_client import BrokerClient
        
        # Setup mock
        mock_trading_instance = Mock()
        mock_trading.return_value = mock_trading_instance
        mock_stock.return_value = Mock()
        mock_option.return_value = Mock()
        
        # Create broker client
        client = BrokerClient("test_key", "test_secret", paper=True)
        
        # Test None response
        mock_trading_instance.get_account.return_value = None
        with self.assertRaises(RetryException):
            client.get_account()
        
        # Test missing attribute
        mock_account = Mock(spec=[])  # No attributes
        mock_trading_instance.get_account.return_value = mock_account
        with self.assertRaises(RetryException):
            client.get_account()
    
    @patch('core.broker_client.TradingClientSigned')
    @patch('core.broker_client.StockHistoricalDataClientSigned')
    @patch('core.broker_client.OptionHistoricalDataClientSigned')
    def test_negative_buying_power_validation(self, mock_option, mock_stock, mock_trading):
        """Test validation of buying power."""
        from core.broker_client import BrokerClient
        
        # Setup mock
        mock_trading_instance = Mock()
        mock_trading.return_value = mock_trading_instance
        mock_stock.return_value = Mock()
        mock_option.return_value = Mock()
        
        # Create broker client
        client = BrokerClient("test_key", "test_secret", paper=True)
        
        # Test negative buying power
        mock_account = Mock()
        mock_account.non_marginable_buying_power = -1000.0
        mock_trading_instance.get_account.return_value = mock_account
        
        with self.assertRaises(ValueError) as context:
            client.get_non_margin_buying_power()
        
        self.assertIn("Invalid buying power", str(context.exception))

def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestRetryDecorator))
    suite.addTests(loader.loadTestsFromTestCase(TestCircuitBreaker))
    suite.addTests(loader.loadTestsFromTestCase(TestThreadSafeStateManager))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseThreadSafety))
    suite.addTests(loader.loadTestsFromTestCase(TestBrokerClientValidation))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)