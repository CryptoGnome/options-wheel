"""
SQLite database for tracking positions, premiums, and trade history.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import json

class WheelDatabase:
    """Database for tracking options wheel strategy data"""
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "wheel_strategy.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
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
                    trade_type TEXT NOT NULL,  -- 'sell_put', 'sell_call', 'buy_stock', 'sell_stock'
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
        """Record premium collected from selling an option"""
        if trade_date is None:
            trade_date = datetime.now()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO premiums 
                (symbol, option_type, strike_price, premium_collected, contracts, 
                 expiration_date, trade_date, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, option_type, strike_price, premium, contracts,
                  expiration_date, trade_date, status, notes))
            
            # Update cost basis
            self.update_cost_basis(symbol)
            
            return cursor.lastrowid
    
    def add_position(self, symbol, position_type, quantity, entry_price, entry_date=None):
        """Add a new position"""
        if entry_date is None:
            entry_date = datetime.now()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions 
                (symbol, position_type, quantity, entry_price, entry_date, status)
                VALUES (?, ?, ?, ?, ?, 'open')
            """, (symbol, position_type, quantity, entry_price, entry_date))
            
            return cursor.lastrowid
    
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
        """Update the cost basis for a symbol based on positions and premiums"""
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
                SELECT SUM(premium_collected * contracts) as total_premiums
                FROM premiums 
                WHERE symbol = ? AND option_type = 'C' AND status IN ('collected', 'expired')
            """, (symbol,))
            
            premium_data = cursor.fetchone()
            total_premiums = premium_data['total_premiums'] or 0
            
            if shares > 0:
                avg_cost = total_cost / shares
                # Each option contract is for 100 shares
                premium_per_share = (total_premiums * 100) / shares
                adjusted_cost = avg_cost - premium_per_share
                
                # Insert or update cost basis
                cursor.execute("""
                    INSERT OR REPLACE INTO cost_basis 
                    (symbol, shares_owned, total_cost, total_premiums_collected, 
                     avg_cost_per_share, adjusted_cost_per_share, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, shares, total_cost, total_premiums, 
                      avg_cost, max(0, adjusted_cost), datetime.now()))
    
    def get_adjusted_cost_basis(self, symbol):
        """Get the adjusted cost basis for a symbol"""
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
    
    def get_summary_stats(self, symbol=None):
        """Get summary statistics for the wheel strategy"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if symbol:
                # Symbol-specific stats
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT symbol) as symbols_traded,
                        SUM(CASE WHEN option_type = 'P' THEN premium_collected * contracts ELSE 0 END) as total_put_premiums,
                        SUM(CASE WHEN option_type = 'C' THEN premium_collected * contracts ELSE 0 END) as total_call_premiums,
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
                        SUM(CASE WHEN option_type = 'P' THEN premium_collected * contracts ELSE 0 END) as total_put_premiums,
                        SUM(CASE WHEN option_type = 'C' THEN premium_collected * contracts ELSE 0 END) as total_call_premiums,
                        COUNT(CASE WHEN option_type = 'P' THEN 1 ELSE NULL END) as put_trades,
                        COUNT(CASE WHEN option_type = 'C' THEN 1 ELSE NULL END) as call_trades
                    FROM premiums
                """)
            
            result = cursor.fetchone()
            return dict(result) if result else None