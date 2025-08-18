#!/usr/bin/env python3
"""
Flask web application for Options Wheel Strategy dashboard.
Provides real-time monitoring and control via localhost.
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import threading
import time
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import os
from pathlib import Path

# Import strategy components
from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER, strategy_config
from core.broker_client import BrokerClient
from core.database import WheelDatabase
from core.thread_safe_manager import ThreadSafeStateManager
from core.order_manager import OrderManager
from core.execution_limit import sell_puts_limit, sell_calls_limit, update_filled_orders
from core.rolling import process_rolls

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            static_folder='web/static',
            template_folder='web/templates')
app.config['SECRET_KEY'] = 'wheel-strategy-secret-key'
CORS(app)

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global components
client = None
db = None
state_manager = None
order_manager = None
strategy_thread = None
strategy_running = False
last_update = {}

def initialize_components():
    """Initialize all trading components"""
    global client, db, state_manager, order_manager
    
    client = BrokerClient(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        paper=IS_PAPER
    )
    db = WheelDatabase()
    state_manager = ThreadSafeStateManager()
    order_manager = OrderManager(client, update_interval=20, max_order_age=1)
    
    logger.info("Trading components initialized")

def is_market_open():
    """Check if US market is currently open"""
    now = datetime.now(ZoneInfo("America/New_York"))
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if now.weekday() >= 5:  # Weekend
        return False
    
    return market_open <= now <= market_close

def get_account_data():
    """Get current account data"""
    try:
        account = client.get_account()
        actual_balance = client.get_non_margin_buying_power()
        balance_allocation = strategy_config.get_balance_allocation()
        allocated_balance = actual_balance * balance_allocation
        options_buying_power = client.get_options_buying_power()
        
        # Calculate daily P&L
        daily_pl = 0
        daily_pl_pct = 0
        if hasattr(account, 'equity') and hasattr(account, 'last_equity'):
            try:
                last_equity = float(account.last_equity)
                current_equity = float(account.equity)
                daily_pl = current_equity - last_equity
                daily_pl_pct = (daily_pl / last_equity * 100) if last_equity > 0 else 0
            except:
                pass
        
        return {
            'portfolio_value': float(account.portfolio_value),
            'cash_balance': actual_balance,
            'allocated_balance': allocated_balance,
            'allocation_percentage': balance_allocation * 100,
            'buying_power': min(options_buying_power, allocated_balance),
            'daily_pl': daily_pl,
            'daily_pl_percentage': daily_pl_pct,
            'market_open': is_market_open(),
            'mode': 'PAPER' if IS_PAPER else 'LIVE'
        }
    except Exception as e:
        logger.error(f"Error getting account data: {e}")
        return None

def get_positions_data():
    """Get current positions data"""
    try:
        positions = client.get_positions()
        states = state_manager.update_state(positions)
        position_counts = state_manager.count_positions_by_symbol(positions)
        
        formatted_positions = []
        
        for p in positions:
            from alpaca.trading.enums import AssetClass
            
            if p.asset_class == AssetClass.US_OPTION:
                # Parse option symbol
                from core.utils import parse_option_symbol
                underlying, option_type, strike = parse_option_symbol(p.symbol)
                
                qty = abs(int(p.qty))
                avg_price = abs(float(p.avg_entry_price))
                current_price = abs(float(p.current_price)) if p.current_price else avg_price
                
                # For SHORT options: P&L = (Entry - Current) * 100 * Qty
                # We sold at avg_price and can buy back at current_price
                unrealized_pl = (avg_price - current_price) * 100 * qty
                pl_percentage = (unrealized_pl / (avg_price * 100 * qty) * 100) if avg_price > 0 else 0
                
                # Extract expiration date from symbol (format: AAPL241231P00150000)
                exp_date_str = None
                dte = None
                try:
                    # Extract date portion after underlying symbol
                    date_part = p.symbol[len(underlying):len(underlying)+6]  # YYMMDD format
                    if len(date_part) == 6 and date_part.isdigit():
                        year = 2000 + int(date_part[:2])
                        month = int(date_part[2:4])
                        day = int(date_part[4:6])
                        exp_date = datetime(year, month, day).date()
                        exp_date_str = exp_date.strftime('%m/%d/%y')
                        dte = (exp_date - datetime.now().date()).days
                except:
                    pass
                
                formatted_positions.append({
                    'symbol': p.symbol,
                    'underlying': underlying,
                    'type': 'option',
                    'option_type': 'PUT' if option_type == 'P' else 'CALL',
                    'strike': strike,
                    'quantity': qty,
                    'avg_price': avg_price,
                    'current_price': current_price,
                    'market_value': abs(float(p.market_value)),
                    'unrealized_pl': unrealized_pl,
                    'pl_percentage': pl_percentage,
                    'expiration': exp_date_str,
                    'dte': dte
                })
            elif p.asset_class == AssetClass.US_EQUITY:
                state = states.get(p.symbol, {})
                formatted_positions.append({
                    'symbol': p.symbol,
                    'type': 'stock',
                    'quantity': int(p.qty),
                    'avg_price': float(p.avg_entry_price),
                    'current_price': float(p.current_price) if p.current_price else 0,
                    'market_value': float(p.market_value),
                    'unrealized_pl': float(p.unrealized_pl) if p.unrealized_pl else 0,
                    'state': state.get('type', 'holding'),
                    'pl_percentage': 0  # Calculate if needed
                })
        
        return {
            'positions': formatted_positions,
            'states': states,
            'counts': position_counts
        }
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return {'positions': [], 'states': {}, 'counts': {}}

def get_pending_orders_data():
    """Get pending orders data"""
    try:
        pending = order_manager.get_pending_orders()
        
        formatted_orders = []
        for order in pending:
            age_seconds = (datetime.now() - order.created_at).total_seconds()
            formatted_orders.append({
                'id': order.order_id,
                'underlying': order.underlying,
                'type': order.order_type.upper(),
                'strike': order.strike if hasattr(order, 'strike') else 0,
                'quantity': order.quantity,
                'limit_price': order.limit_price,
                'attempts': order.attempts,
                'age_seconds': int(age_seconds),
                'max_age_seconds': 60
            })
        
        return formatted_orders
    except Exception as e:
        logger.error(f"Error getting pending orders: {e}")
        return []

def get_performance_data():
    """Get performance metrics"""
    try:
        summary = db.get_summary_stats()
        if not summary:
            summary = {'total_put_premiums': 0, 'total_call_premiums': 0, 
                      'put_trades': 0, 'call_trades': 0, 'symbols_traded': 0}
        
        total_premiums = summary['total_put_premiums'] + summary['total_call_premiums']
        total_trades = summary['put_trades'] + summary['call_trades']
        avg_premium = total_premiums / total_trades if total_trades > 0 else 0
        
        # Get realized P&L
        realized_pnl = db.get_realized_pnl()
        
        # Get cumulative P&L history for chart
        pnl_history = db.get_cumulative_pnl_history(days_back=90)
        
        # Get performance by symbol with enhanced metrics
        symbol_performance = []
        try:
            raw_performance = db.get_performance_by_symbol()
            for symbol_data in raw_performance:
                symbol = symbol_data.get('symbol', 'Unknown')
                put_premiums = symbol_data.get('put_premiums', 0)
                call_premiums = symbol_data.get('call_premiums', 0)
                put_trades = symbol_data.get('put_trades', 0)
                call_trades = symbol_data.get('call_trades', 0)
                total_pnl = put_premiums + call_premiums
                total_trades_sym = put_trades + call_trades
                
                symbol_performance.append({
                    'symbol': symbol,
                    'total_pnl': total_pnl,
                    'put_premiums': put_premiums,
                    'call_premiums': call_premiums,
                    'put_trades': put_trades,
                    'call_trades': call_trades,
                    'win_rate': 0,  # Calculate based on expired vs assigned
                    'roi': 0  # Calculate based on capital used
                })
        except:
            pass
        
        # Get recent premium history
        recent_premiums = db.get_premium_history(days_back=30)
        
        # Calculate daily premiums for chart
        daily_data = {}
        for premium in recent_premiums:
            date = premium['trade_date'][:10]  # Extract date part
            if date not in daily_data:
                daily_data[date] = 0
            daily_data[date] += premium['premium_collected'] * premium['contracts'] * 100
        
        # Calculate win rate (premiums kept vs assigned)
        win_rate = 0
        if total_trades > 0:
            # Assuming expired/collected options are wins
            expired_trades = len([p for p in recent_premiums if p.get('status') in ['expired', 'collected']])
            win_rate = (expired_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'total_premiums': total_premiums,
            'put_premiums': summary['total_put_premiums'],
            'call_premiums': summary['total_call_premiums'],
            'total_trades': total_trades,
            'put_trades': summary['put_trades'],
            'call_trades': summary['call_trades'],
            'avg_premium': avg_premium,
            'symbols_traded': summary['symbols_traded'],
            'daily_premiums': daily_data,
            'pnl_history': pnl_history if pnl_history else [],
            'realized_pnl': realized_pnl if realized_pnl else {'total_realized': 0},
            'symbol_performance': symbol_performance,
            'win_rate': win_rate,
            'total_realized_pnl': realized_pnl.get('total_realized', 0) if realized_pnl else 0
        }
    except Exception as e:
        logger.error(f"Error getting performance data: {e}")
        return {
            'total_premiums': 0,
            'total_trades': 0,
            'avg_premium': 0,
            'symbols_traded': 0,
            'daily_premiums': {},
            'pnl_history': [],
            'realized_pnl': {'total_realized': 0},
            'symbol_performance': [],
            'win_rate': 0,
            'total_realized_pnl': 0
        }

def get_strategy_status():
    """Get current strategy status and configuration"""
    try:
        symbols = strategy_config.get_enabled_symbols()
        max_layers = strategy_config.get_max_wheel_layers()
        
        symbol_status = []
        for symbol in symbols:
            pos_count = state_manager.get_position_count(symbol)
            is_allowed = state_manager.is_position_allowed(symbol, max_layers)
            
            symbol_status.append({
                'symbol': symbol,
                'enabled': True,
                'contracts': strategy_config.get_contracts_for_symbol(symbol),
                'puts': pos_count.get('puts', 0),
                'calls': pos_count.get('calls', 0),
                'shares': pos_count.get('shares', 0),
                'current_layers': max(pos_count.get('puts', 0), pos_count.get('shares', 0)),
                'max_layers': max_layers,
                'can_add_position': is_allowed
            })
        
        return {
            'running': strategy_running,
            'market_open': is_market_open(),
            'symbols': symbol_status,
            'config': {
                'allocation_percentage': strategy_config.get_balance_allocation() * 100,
                'max_wheel_layers': max_layers,
                'delta_min': strategy_config.get_option_filters()['delta_min'],
                'delta_max': strategy_config.get_option_filters()['delta_max'],
                'dte_min': strategy_config.get_option_filters()['expiration_min_days'],
                'dte_max': strategy_config.get_option_filters()['expiration_max_days']
            }
        }
    except Exception as e:
        logger.error(f"Error getting strategy status: {e}")
        return {}

def emit_log(level, message, highlight=False):
    """Emit log message to connected clients"""
    try:
        socketio.emit('log_message', {
            'level': level,
            'message': message,
            'highlight': highlight,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error emitting log: {e}")

def run_strategy_cycle():
    """Run one cycle of the strategy"""
    global last_update
    
    try:
        # Get enabled symbols
        SYMBOLS = strategy_config.get_enabled_symbols()
        if not SYMBOLS:
            emit_log('warning', 'No enabled symbols configured')
            return
        
        # Get account info
        emit_log('info', f'Checking account status for {len(SYMBOLS)} symbols')
        account_data = get_account_data()
        if not account_data:
            emit_log('error', 'Failed to get account data')
            return
        
        emit_log('info', f'Account balance: ${account_data["cash_balance"]:,.2f}, Buying power: ${account_data["buying_power"]:,.2f}')
        
        # Get positions
        positions = client.get_positions()
        emit_log('info', f'Found {len(positions)} active positions')
        
        # Process rolls
        rolls_executed = process_rolls(client, positions, strategy_config, db)
        if rolls_executed > 0:
            emit_log('success', f'Successfully rolled {rolls_executed} position(s)', True)
            positions = client.get_positions()
            socketio.emit('roll_executed', {'count': rolls_executed})
        
        # Update state
        states = state_manager.update_state(positions)
        position_counts = state_manager.count_positions_by_symbol(positions)
        
        # Sell calls on long shares
        for symbol, state in states.items():
            if state["type"] == "long_shares":
                pending_calls = [o for o in order_manager.get_pending_orders() 
                               if o.underlying == symbol and o.order_type == 'call']
                
                if not pending_calls:
                    emit_log('info', f'{symbol}: Found {state["qty"]} shares, preparing covered call')
                    
                    # Track in database if needed
                    existing = db.get_position_history(symbol, 'stock', 'open')
                    if not existing:
                        db.add_position(symbol, 'stock', state["qty"], state["price"])
                    
                    # Sell covered call
                    order_id = sell_calls_limit(client, order_manager, symbol, 
                                               state["price"], state["qty"], db, None)
                    if order_id:
                        emit_log('success', f'{symbol}: Covered CALL order placed', True)
                        socketio.emit('order_placed', {
                            'type': 'call',
                            'symbol': symbol,
                            'order_id': order_id
                        })
        
        # Determine allowed symbols for puts
        allowed_symbols = []
        max_layers = strategy_config.get_max_wheel_layers()
        
        for symbol in SYMBOLS:
            if state_manager.is_position_allowed(symbol, max_layers):
                pending_puts = [o for o in order_manager.get_pending_orders() 
                              if o.underlying == symbol and o.order_type == 'put']
                
                if not pending_puts:
                    allowed_symbols.append(symbol)
        
        # Sell puts if possible
        buying_power = account_data['buying_power']
        if buying_power > 0 and allowed_symbols:
            emit_log('info', f'Searching for PUT opportunities on: {", ".join(allowed_symbols)}')
            order_ids = sell_puts_limit(client, order_manager, allowed_symbols, 
                                       buying_power, position_counts, db, None)
            if order_ids:
                emit_log('success', f'Placed {len(order_ids)} PUT order(s)', True)
                for order_id in order_ids:
                    socketio.emit('order_placed', {
                        'type': 'put',
                        'order_ids': order_ids
                    })
        elif not allowed_symbols:
            emit_log('info', 'No symbols available for new PUT positions (max layers reached)')
        
        # Update pending orders
        results = update_filled_orders(order_manager, db)
        
        # Emit updates
        filled = [oid for oid, status in results.items() if status == 'filled']
        if filled:
            socketio.emit('orders_filled', {'order_ids': filled})
        
        # Store last update
        last_update = {
            'timestamp': datetime.now().isoformat(),
            'positions': len(positions),
            'pending_orders': len(order_manager.get_pending_orders()),
            'buying_power': buying_power
        }
        
    except Exception as e:
        logger.error(f"Error in strategy cycle: {e}")

def strategy_worker():
    """Background worker thread for strategy"""
    global strategy_running
    
    while strategy_running:
        if is_market_open():
            run_strategy_cycle()
            
            # Emit regular updates
            socketio.emit('update', {
                'account': get_account_data(),
                'positions': get_positions_data(),
                'orders': get_pending_orders_data(),
                'performance': get_performance_data(),
                'status': get_strategy_status()
            })
        
        time.sleep(20)  # Run every 20 seconds

# API Routes
@app.route('/')
def index():
    """Serve main dashboard"""
    return render_template('index.html')

@app.route('/api/account')
def api_account():
    """Get account data"""
    return jsonify(get_account_data())

@app.route('/api/positions')
def api_positions():
    """Get positions data"""
    return jsonify(get_positions_data())

@app.route('/api/orders')
def api_orders():
    """Get pending orders"""
    return jsonify(get_pending_orders_data())

@app.route('/api/performance')
def api_performance():
    """Get performance metrics"""
    return jsonify(get_performance_data())

@app.route('/api/status')
def api_status():
    """Get strategy status"""
    return jsonify(get_strategy_status())

@app.route('/api/strategy/start', methods=['POST'])
def start_strategy():
    """Start the strategy"""
    global strategy_running, strategy_thread
    
    if not strategy_running:
        strategy_running = True
        strategy_thread = threading.Thread(target=strategy_worker)
        strategy_thread.daemon = True
        strategy_thread.start()
        
        socketio.emit('strategy_started')
        return jsonify({'status': 'started'})
    
    return jsonify({'status': 'already_running'})

@app.route('/api/strategy/stop', methods=['POST'])
def stop_strategy():
    """Stop the strategy"""
    global strategy_running
    
    if strategy_running:
        strategy_running = False
        
        # Cancel pending orders
        if order_manager.has_pending_orders():
            cancelled = order_manager.cancel_all_pending()
            socketio.emit('orders_cancelled', {'count': cancelled})
        
        socketio.emit('strategy_stopped')
        return jsonify({'status': 'stopped'})
    
    return jsonify({'status': 'not_running'})

@app.route('/api/setup/status')
def setup_status():
    """Check if initial setup is needed"""
    env_path = Path(__file__).parent / '.env'
    config_path = Path(__file__).parent / 'config' / 'strategy_config.json'
    
    # Check if .env exists and has required keys
    needs_setup = not env_path.exists()
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            content = f.read()
            if 'ALPACA_API_KEY' not in content or 'ALPACA_SECRET_KEY' not in content:
                needs_setup = True
    
    return jsonify({
        'needsSetup': needs_setup,
        'hasEnv': env_path.exists(),
        'hasConfig': config_path.exists()
    })

@app.route('/api/setup/complete', methods=['POST'])
def complete_setup():
    """Complete the initial setup process"""
    try:
        data = request.json
        
        # Create .env file
        env_path = Path(__file__).parent / '.env'
        env_content = f"""# Alpaca API Credentials
ALPACA_API_KEY={data['credentials']['api_key']}
ALPACA_SECRET_KEY={data['credentials']['secret_key']}
IS_PAPER={'true' if data['credentials']['is_paper'] else 'false'}
"""
        
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        # Create/update strategy_config.json
        config_path = Path(__file__).parent / 'config' / 'strategy_config.json'
        
        # Ensure symbols have proper structure
        symbols = {}
        for symbol, settings in data['strategy'].get('symbols', {}).items():
            symbols[symbol] = {
                'enabled': settings.get('enabled', True),
                'contracts': settings.get('contracts', 1),
                'rolling': {
                    'enabled': False,
                    'strategy': 'both'
                }
            }
        
        strategy_config_data = {
            'balance_settings': data['strategy']['balance_settings'],
            'option_filters': data['strategy']['option_filters'],
            'rolling_settings': data['strategy'].get('rolling_settings', {
                'enabled': False,
                'days_before_expiry': 1,
                'min_premium_to_roll': 0.05,
                'roll_delta_target': 0.25
            }),
            'symbols': symbols,
            'default_contracts': 1
        }
        
        with open(config_path, 'w') as f:
            json.dump(strategy_config_data, f, indent=2)
        
        # Reload configurations
        global ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER, strategy_config
        
        # Re-import credentials
        from config.credentials import ALPACA_API_KEY as NEW_KEY, ALPACA_SECRET_KEY as NEW_SECRET, IS_PAPER as NEW_PAPER
        ALPACA_API_KEY = NEW_KEY
        ALPACA_SECRET_KEY = NEW_SECRET
        IS_PAPER = NEW_PAPER
        
        # Reload strategy config
        strategy_config.reload()
        
        # Reinitialize components with new credentials
        initialize_components()
        
        return jsonify({'status': 'success', 'message': 'Setup completed successfully'})
        
    except Exception as e:
        logger.error(f"Setup error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Get or update configuration"""
    if request.method == 'GET':
        # Return the config dictionary directly
        return jsonify(strategy_config.config)
    
    # POST - update config
    try:
        data = request.json
        # Update config file
        config_path = Path(__file__).parent / 'config' / 'strategy_config.json'
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Reload config
        strategy_config.reload()
        
        socketio.emit('config_updated', data)
        return jsonify({'status': 'updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("Client connected")
    emit('connected', {
        'account': get_account_data(),
        'positions': get_positions_data(),
        'orders': get_pending_orders_data(),
        'performance': get_performance_data(),
        'status': get_strategy_status()
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Client disconnected")

@socketio.on('request_update')
def handle_update_request():
    """Handle manual update request"""
    emit('update', {
        'account': get_account_data(),
        'positions': get_positions_data(),
        'orders': get_pending_orders_data(),
        'performance': get_performance_data(),
        'status': get_strategy_status()
    })

if __name__ == '__main__':
    # Initialize components
    initialize_components()
    
    # Create web directories if they don't exist
    web_dir = Path(__file__).parent / 'web'
    templates_dir = web_dir / 'templates'
    static_dir = web_dir / 'static'
    
    templates_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / 'css').mkdir(parents=True, exist_ok=True)
    (static_dir / 'js').mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting WheelForge Web Dashboard")
    logger.info("Open http://localhost:5000 in your browser")
    
    # Run Flask app with SocketIO
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)