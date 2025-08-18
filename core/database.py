"""
SQLite database for tracking positions, premiums, and trade history.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import json
import threading
import logging
from typing import Optional, Dict, List, Any
import time

logger = logging.getLogger(f"strategy.{__name__}")

class WheelDatabase:
    """Thread-safe database for tracking options wheel strategy data"""
    
    def __init__(self, db_path=None, pool_size=5, timeout=30.0):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "wheel_strategy.db"
        self.db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection pool settings
        self.pool_size = pool_size
        self.timeout = timeout
        self._local = threading.local()
        self._lock = threading.RLock()
        
        # Initialize database schema
        self.init_database()
        
        # Enable WAL mode for better concurrency
        self._enable_wal_mode()
    
    def _enable_wal_mode(self):
        """Enable Write-Ahead Logging for better concurrency."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")  # 5 second timeout
            conn.commit()
            conn.close()
            logger.info("WAL mode enabled for database")
        except Exception as e:
            logger.warning(f"Could not enable WAL mode: {str(e)}")
    
    @contextmanager
    def get_connection(self, max_retries=3):
        """Thread-safe context manager for database connections with retry logic."""
        conn = None
        attempt = 0
        last_exception = None
        
        while attempt < max_retries:
            try:
                # Use thread-local storage for connections
                if not hasattr(self._local, 'conn') or self._local.conn is None:
                    self._local.conn = sqlite3.connect(
                        str(self.db_path),
                        timeout=self.timeout,
                        check_same_thread=False
                    )
                    self._local.conn.row_factory = sqlite3.Row
                    self._local.conn.execute("PRAGMA journal_mode=WAL")
                    self._local.conn.execute("PRAGMA busy_timeout=5000")
                
                conn = self._local.conn
                
                # Begin transaction
                conn.execute("BEGIN IMMEDIATE")
                
                try:
                    yield conn
                    conn.commit()
                    return
                except sqlite3.IntegrityError as e:
                    conn.rollback()
                    logger.error(f"Database integrity error: {str(e)}")
                    raise
                except Exception as e:
                    conn.rollback()
                    raise e
                    
            except sqlite3.OperationalError as e:
                last_exception = e
                if "database is locked" in str(e):
                    attempt += 1
                    if attempt < max_retries:
                        wait_time = 0.1 * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Database locked, retrying in {wait_time:.2f}s (attempt {attempt}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Database locked after {max_retries} attempts")
                        raise
                else:
                    raise
            except Exception as e:
                logger.error(f"Database connection error: {str(e)}")
                # Reset connection on error
                if hasattr(self._local, 'conn'):
                    try:
                        self._local.conn.close()
                    except:
                        pass
                    self._local.conn = None
                raise
        
        if last_exception:
            raise last_exception
    
    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Positions table - tracks current and historical positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    position_type TEXT NOT NULL,  -- 'stock', 'put', 'call'
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_date TIMESTAMP NOT NULL,
                    exit_price REAL,
                    exit_date TIMESTAMP,
                    status TEXT NOT NULL,  -- 'open', 'closed', 'assigned', 'expired'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Premiums table - tracks all premiums collected
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS premiums (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    option_type TEXT NOT NULL,  -- 'P' for put, 'C' for call
                    strike_price REAL NOT NULL,
                    premium_collected REAL NOT NULL,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    expiration_date DATE NOT NULL,
                    trade_date TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,  -- 'collected', 'assigned', 'expired'
                    position_id INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (position_id) REFERENCES positions(id)
                )
            """)
            
            # Cost basis table - tracks adjusted cost basis per symbol
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cost_basis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    shares_owned INTEGER NOT NULL,
                    total_cost REAL NOT NULL,
                    total_premiums_collected REAL NOT NULL DEFAULT 0,
                    avg_cost_per_share REAL NOT NULL,
                    adjusted_cost_per_share REAL NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Trade history table - comprehensive trade log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    trade_type TEXT NOT NULL,  -- 'sell_put', 'sell_call', 'buy_stock', 'sell_stock', 'buy_to_close', 'roll'
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    strike_price REAL,
                    expiration_date DATE,
                    premium REAL,
                    trade_date TIMESTAMP NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_premiums_symbol ON premiums(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_symbol ON trade_history(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_date ON trade_history(trade_date)")
    
    def add_premium(self, symbol, option_type, strike_price, premium, contracts=1, 
                   expiration_date=None, trade_date=None, status='collected', notes=None):
        """Record premium collected from selling an option with thread safety."""
        if trade_date is None:
            trade_date = datetime.now()
        
        with self._lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO premiums 
                        (symbol, option_type, strike_price, premium_collected, contracts, 
                         expiration_date, trade_date, status, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (symbol, option_type, strike_price, premium, contracts,
                          expiration_date, trade_date, status, notes))
                    
                    row_id = cursor.lastrowid
                    
                # Update cost basis in separate transaction
                self.update_cost_basis(symbol)
                
                logger.debug(f"Added premium record for {symbol}: ${premium:.2f}")
                return row_id
                
            except Exception as e:
                logger.error(f"Failed to add premium for {symbol}: {str(e)}")
                raise
    
    def add_position(self, symbol, position_type, quantity, entry_price, entry_date=None):
        """Add a new position with thread safety."""
        if entry_date is None:
            entry_date = datetime.now()
        
        with self._lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Check for existing open position first
                    cursor.execute("""
                        SELECT id FROM positions 
                        WHERE symbol = ? AND position_type = ? AND status = 'open'
                    """, (symbol, position_type))
                    
                    existing = cursor.fetchone()
                    if existing:
                        logger.warning(f"Open position already exists for {symbol} {position_type}")
                        return existing['id']
                    
                    cursor.execute("""
                        INSERT INTO positions 
                        (symbol, position_type, quantity, entry_price, entry_date, status)
                        VALUES (?, ?, ?, ?, ?, 'open')
                    """, (symbol, position_type, quantity, entry_price, entry_date))
                    
                    logger.debug(f"Added position for {symbol}: {position_type} qty={quantity}")
                    return cursor.lastrowid
                    
            except Exception as e:
                logger.error(f"Failed to add position for {symbol}: {str(e)}")
                raise
    
    def close_position(self, position_id, exit_price, exit_date=None, status='closed'):
        """Close an existing position"""
        if exit_date is None:
            exit_date = datetime.now()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE positions 
                SET exit_price = ?, exit_date = ?, status = ?
                WHERE id = ?
            """, (exit_price, exit_date, status, position_id))
    
    def update_cost_basis(self, symbol):
        """Update the cost basis for a symbol based on positions and premiums with thread safety."""
        with self._lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get current stock positions
                    cursor.execute("""
                        SELECT SUM(quantity) as total_shares, 
                               SUM(quantity * entry_price) as total_cost
                        FROM positions 
                        WHERE symbol = ? AND position_type = 'stock' AND status = 'open'
                    """, (symbol,))
                    
                    stock_data = cursor.fetchone()
                    shares = stock_data['total_shares'] or 0
                    total_cost = stock_data['total_cost'] or 0
                    
                    # Get total premiums collected (calls only, as they reduce cost basis when holding)
                    cursor.execute("""
                        SELECT SUM(premium_collected * contracts * 100) as total_premiums
                        FROM premiums 
                        WHERE symbol = ? AND option_type = 'C' AND status IN ('collected', 'expired')
                    """, (symbol,))
                    
                    premium_data = cursor.fetchone()
                    total_premiums = premium_data['total_premiums'] or 0
                    
                    if shares > 0:
                        avg_cost = total_cost / shares
                        # total_premiums is already in dollars (from query: premium_collected * contracts * 100)
                        premium_per_share = total_premiums / shares
                        adjusted_cost = avg_cost - premium_per_share
                        
                        # Insert or update cost basis
                        cursor.execute("""
                            INSERT OR REPLACE INTO cost_basis 
                            (symbol, shares_owned, total_cost, total_premiums_collected, 
                             avg_cost_per_share, adjusted_cost_per_share, last_updated)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (symbol, shares, total_cost, total_premiums, 
                              avg_cost, max(0, adjusted_cost), datetime.now()))
                        
                        logger.debug(f"Updated cost basis for {symbol}: adjusted=${adjusted_cost:.2f}")
                    
            except Exception as e:
                logger.error(f"Failed to update cost basis for {symbol}: {str(e)}")
                raise
    
    def get_adjusted_cost_basis(self, symbol) -> Optional[Dict[str, Any]]:
        """Get the adjusted cost basis for a symbol with error handling."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT adjusted_cost_per_share, avg_cost_per_share, 
                           total_premiums_collected, shares_owned
                    FROM cost_basis 
                    WHERE symbol = ?
                """, (symbol,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'adjusted_cost': result['adjusted_cost_per_share'],
                        'original_cost': result['avg_cost_per_share'],
                        'total_premiums': result['total_premiums_collected'],
                        'shares': result['shares_owned']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get cost basis for {symbol}: {str(e)}")
            return None
    
    def get_recent_trades(self, limit=10):
        """Get recent trades from the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, symbol, trade_type, strike_price, premium
                    FROM trades
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to get recent trades: {str(e)}")
            return []
    
    def get_position_history(self, symbol=None, position_type=None, status=None):
        """Get position history with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM positions WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if position_type:
                query += " AND position_type = ?"
                params.append(position_type)
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY entry_date DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_premium_history(self, symbol=None, option_type=None, days_back=None):
        """Get premium history with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM premiums WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if option_type:
                query += " AND option_type = ?"
                params.append(option_type)
            if days_back:
                query += " AND trade_date >= datetime('now', '-' || ? || ' days')"
                params.append(days_back)
            
            query += " ORDER BY trade_date DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def add_trade(self, symbol, trade_type, quantity, price, strike_price=None,
                  expiration_date=None, premium=None, trade_date=None, notes=None):
        """Add a trade to the history"""
        if trade_date is None:
            trade_date = datetime.now()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_history 
                (symbol, trade_type, quantity, price, strike_price, 
                 expiration_date, premium, trade_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, trade_type, quantity, price, strike_price,
                  expiration_date, premium, trade_date, notes))
            
            return cursor.lastrowid
    
    def get_summary_stats(self, symbol=None) -> Optional[Dict[str, Any]]:
        """Get summary statistics for the wheel strategy with error handling."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if symbol:
                    # Symbol-specific stats
                    cursor.execute("""
                        SELECT 
                            COUNT(DISTINCT symbol) as symbols_traded,
                            SUM(CASE WHEN option_type = 'P' THEN premium_collected * contracts * 100 ELSE 0 END) as total_put_premiums,
                            SUM(CASE WHEN option_type = 'C' THEN premium_collected * contracts * 100 ELSE 0 END) as total_call_premiums,
                            COUNT(CASE WHEN option_type = 'P' THEN 1 ELSE NULL END) as put_trades,
                            COUNT(CASE WHEN option_type = 'C' THEN 1 ELSE NULL END) as call_trades
                        FROM premiums
                        WHERE symbol = ?
                    """, (symbol,))
                else:
                    # Overall stats
                    cursor.execute("""
                        SELECT 
                            COUNT(DISTINCT symbol) as symbols_traded,
                            SUM(CASE WHEN option_type = 'P' THEN premium_collected * contracts * 100 ELSE 0 END) as total_put_premiums,
                            SUM(CASE WHEN option_type = 'C' THEN premium_collected * contracts * 100 ELSE 0 END) as total_call_premiums,
                            COUNT(CASE WHEN option_type = 'P' THEN 1 ELSE NULL END) as put_trades,
                            COUNT(CASE WHEN option_type = 'C' THEN 1 ELSE NULL END) as call_trades
                        FROM premiums
                    """)
                
                result = cursor.fetchone()
                return dict(result) if result else None
                
        except Exception as e:
            logger.error(f"Failed to get summary stats: {str(e)}")
            return None
    
    def get_cumulative_pnl_history(self, days_back=90) -> List[Dict[str, Any]]:
        """Get cumulative P&L history for charting."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get daily premium income
                cursor.execute("""
                    SELECT 
                        DATE(trade_date) as date,
                        SUM(premium_collected * contracts * 100) as daily_premium
                    FROM premiums
                    WHERE trade_date >= date('now', '-' || ? || ' days')
                    GROUP BY DATE(trade_date)
                    ORDER BY date
                """, (days_back,))
                
                results = []
                cumulative_total = 0
                
                # Get initial total before the period
                cursor.execute("""
                    SELECT SUM(premium_collected * contracts * 100) as prior_total
                    FROM premiums
                    WHERE trade_date < date('now', '-' || ? || ' days')
                """, (days_back,))
                
                prior_result = cursor.fetchone()
                if prior_result and prior_result['prior_total']:
                    cumulative_total = prior_result['prior_total']
                
                # Build cumulative data
                for row in cursor.fetchall():
                    cumulative_total += row['daily_premium'] or 0
                    results.append({
                        'date': row['date'],
                        'daily_premium': row['daily_premium'] or 0,
                        'cumulative_pnl': cumulative_total
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get P&L history: {str(e)}")
            return []
    
    def get_realized_pnl(self) -> Dict[str, float]:
        """Get realized P&L from closed positions."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get total premiums collected
                cursor.execute("""
                    SELECT 
                        SUM(premium_collected * contracts * 100) as total_premiums
                    FROM premiums
                    WHERE status IN ('collected', 'expired')
                """)
                premiums_result = cursor.fetchone()
                total_premiums = premiums_result['total_premiums'] or 0 if premiums_result else 0
                
                # Get closed stock positions P&L
                cursor.execute("""
                    SELECT 
                        SUM((exit_price - entry_price) * quantity) as stock_pnl
                    FROM positions
                    WHERE position_type = 'stock' AND status = 'closed'
                """)
                stock_result = cursor.fetchone()
                stock_pnl = stock_result['stock_pnl'] or 0 if stock_result else 0
                
                # Get assignment costs (when puts are assigned)
                cursor.execute("""
                    SELECT 
                        SUM((entry_price - strike_price) * quantity * 100) as assignment_cost
                    FROM positions p
                    JOIN premiums pr ON p.symbol = pr.symbol
                    WHERE p.position_type = 'stock' 
                    AND p.status IN ('open', 'closed')
                    AND pr.option_type = 'P' 
                    AND pr.status = 'assigned'
                """)
                assignment_result = cursor.fetchone()
                assignment_cost = assignment_result['assignment_cost'] or 0 if assignment_result else 0
                
                return {
                    'total_premiums': total_premiums,
                    'stock_pnl': stock_pnl,
                    'assignment_cost': assignment_cost,
                    'total_realized': total_premiums + stock_pnl - assignment_cost
                }
                
        except Exception as e:
            logger.error(f"Failed to get realized P&L: {str(e)}")
            return {'total_premiums': 0, 'stock_pnl': 0, 'assignment_cost': 0, 'total_realized': 0}
    
    def get_performance_by_symbol(self) -> List[Dict[str, Any]]:
        """Get performance breakdown by symbol."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 
                        symbol,
                        SUM(CASE WHEN option_type = 'P' THEN premium_collected * contracts * 100 ELSE 0 END) as put_premiums,
                        SUM(CASE WHEN option_type = 'C' THEN premium_collected * contracts * 100 ELSE 0 END) as call_premiums,
                        COUNT(CASE WHEN option_type = 'P' THEN 1 ELSE NULL END) as put_count,
                        COUNT(CASE WHEN option_type = 'C' THEN 1 ELSE NULL END) as call_count,
                        MIN(trade_date) as first_trade,
                        MAX(trade_date) as last_trade
                    FROM premiums
                    GROUP BY symbol
                    ORDER BY (put_premiums + call_premiums) DESC
                """)
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'symbol': row['symbol'],
                        'total_premiums': row['put_premiums'] + row['call_premiums'],
                        'put_premiums': row['put_premiums'],
                        'call_premiums': row['call_premiums'],
                        'total_trades': row['put_count'] + row['call_count'],
                        'first_trade': row['first_trade'],
                        'last_trade': row['last_trade']
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get performance by symbol: {str(e)}")
            return []
    
    def close(self):
        """Close database connections and cleanup."""
        if hasattr(self._local, 'conn') and self._local.conn:
            try:
                self._local.conn.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database: {str(e)}")
            finally:
                self._local.conn = None