#!/usr/bin/env python3
"""
Continuous market hours runner for wheel strategy using limit orders.
Monitors positions, places limit orders, and manages repricing during market hours.
"""

import argparse
import logging
import time
import signal
import sys
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER, strategy_config
from core.broker_client import BrokerClient
from core.execution_limit import sell_puts_limit, sell_calls_limit, update_filled_orders
from core.order_manager import OrderManager
from core.rolling import process_rolls
from core.database import WheelDatabase
from core.thread_safe_manager import ThreadSafeStateManager
from core.elite_display import (
    print_elite_header, display_market_overview, display_positions_elite,
    display_strategy_matrix, display_pending_orders_elite, 
    display_performance_dashboard, display_cycle_summary, display_footer
)
from strategy_logging.strategy_logger import StrategyLogger


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(message)s]',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
should_exit = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global should_exit
    logger.info("\nReceived shutdown signal, finishing current operations...")
    should_exit = True


def is_market_open():
    """Check if US market is currently open"""
    now = datetime.now(ZoneInfo("America/New_York"))
    
    # Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
    market_open = dt_time(9, 30)
    market_close = dt_time(16, 0)
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Check if within market hours
    current_time = now.time()
    return market_open <= current_time <= market_close


def wait_for_market_open():
    """Wait until market opens"""
    while not is_market_open() and not should_exit:
        now = datetime.now(ZoneInfo("America/New_York"))
        logger.info(f"Market closed. Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}. Waiting...")
        time.sleep(60)  # Check every minute


def run_strategy_cycle(client, order_manager, state_manager, db, strat_logger):
    """Run one cycle of the strategy"""
    
    # Get enabled symbols
    SYMBOLS = strategy_config.get_enabled_symbols()
    if not SYMBOLS:
        logger.warning("No symbols enabled in configuration")
        return
    
    # Get account info
    account = client.get_account()
    actual_balance = client.get_non_margin_buying_power()
    balance_allocation = strategy_config.get_balance_allocation()
    allocated_balance = actual_balance * balance_allocation
    options_buying_power = client.get_options_buying_power()
    portfolio_value = float(account.portfolio_value)
    
    # Display market overview
    display_market_overview(account, actual_balance, allocated_balance,
                           options_buying_power, portfolio_value, balance_allocation)
    
    # Get current positions
    positions = client.get_positions()
    if strat_logger:
        strat_logger.add_current_positions(positions)
    
    # Process any rolls first
    rolls_executed = process_rolls(client, positions, strategy_config, db, strat_logger)
    if rolls_executed > 0:
        logger.info(f"Executed {rolls_executed} roll(s)")
        positions = client.get_positions()
        if strat_logger:
            strat_logger.add_current_positions(positions)
    
    # Update state
    current_risk = state_manager.calculate_risk(positions)
    position_counts = state_manager.count_positions_by_symbol(positions)
    states = state_manager.update_state(positions)
    if strat_logger:
        strat_logger.add_state_dict(states)
    
    # Track actions taken
    actions_taken = []
    
    # Determine which symbols can have more positions (needed for display)
    allowed_symbols = []
    max_layers = strategy_config.get_max_wheel_layers()
    
    # Display positions
    position_summary = display_positions_elite(positions, states, position_counts)
    
    # Display strategy matrix
    display_strategy_matrix(position_counts, states, max_layers, allowed_symbols)
    
    # Display performance dashboard
    display_performance_dashboard(db)
    
    # Display pending orders
    display_pending_orders_elite(order_manager)
    
    # Sell calls on any long shares
    for symbol, state in states.items():
        if state["type"] == "long_shares":
            # Check if we already have a pending call order
            pending_calls = [o for o in order_manager.get_pending_orders() 
                           if o.underlying == symbol and o.order_type == 'call']
            
            if not pending_calls:
                # Add position to database if not tracked
                if db:
                    existing = db.get_position_history(symbol, 'stock', 'open')
                    if not existing:
                        db.add_position(symbol, 'stock', state["qty"], state["price"])
                
                # Sell covered call
                order_id = sell_calls_limit(client, order_manager, symbol, 
                                           state["price"], state["qty"], db, strat_logger)
                if order_id:
                    actions_taken.append(f"Placed call order for {symbol}")
    
    # Now populate allowed_symbols with actual logic
    for symbol in SYMBOLS:
        if state_manager.is_position_allowed(symbol, max_layers):
            # Check if we already have pending put orders for this symbol
            pending_puts = [o for o in order_manager.get_pending_orders() 
                          if o.underlying == symbol and o.order_type == 'put']
            
            if not pending_puts:
                allowed_symbols.append(symbol)
                symbol_positions = state_manager.get_position_count(symbol)
                put_count = symbol_positions.get('puts', 0)
                share_lots = symbol_positions.get('shares', 0)
                current_layers = max(put_count, share_lots)
                if current_layers > 0:
                    logger.info(f"{symbol}: {current_layers}/{max_layers} wheel layers active")
    
    # Calculate available buying power
    buying_power = min(options_buying_power, allocated_balance)
    buying_power = max(0, buying_power)
    
    if strat_logger:
        strat_logger.set_buying_power(buying_power)
        strat_logger.set_allowed_symbols(allowed_symbols)
    
    # Sell puts if we have buying power and allowed symbols
    if buying_power > 0 and allowed_symbols:
        order_ids = sell_puts_limit(client, order_manager, allowed_symbols, 
                                   buying_power, position_counts, db, strat_logger)
        if order_ids:
            actions_taken.append(f"Placed {len(order_ids)} put order(s)")
    
    # Display cycle summary
    display_cycle_summary(actions_taken, allowed_symbols, buying_power)
    
    if strat_logger:
        strat_logger.save()


def main():
    parser = argparse.ArgumentParser(description='Run wheel strategy with limit orders during market hours')
    parser.add_argument('--update-interval', type=int, default=20,
                       help='Seconds between order repricing (default: 20)')
    parser.add_argument('--cycle-interval', type=int, default=60,
                       help='Seconds between strategy cycles (default: 60)')
    parser.add_argument('--max-order-age', type=int, default=1,
                       help='Maximum minutes to keep an order before cancelling (default: 1)')
    parser.add_argument('--strat-log', action='store_true',
                       help='Enable strategy logging to JSON')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    parser.add_argument('--log-to-file', action='store_true',
                       help='Log to file instead of console')
    parser.add_argument('--once', action='store_true',
                       help='Run once then exit (for testing)')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = getattr(logging, args.log_level)
    
    if args.log_to_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f'logs/strategy_limit_{timestamp}.log'
        logging.basicConfig(
            level=log_level,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        logger.info(f"Logging to file: {log_file}")
    else:
        logging.basicConfig(
            level=log_level,
            format='[%(message)s]',
            handlers=[logging.StreamHandler()]
        )
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize components
    print_elite_header()
    logger.info("System initialization in progress...")
    
    client = BrokerClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper=IS_PAPER)
    order_manager = OrderManager(client, args.update_interval, args.max_order_age)
    state_manager = ThreadSafeStateManager()
    db = WheelDatabase()
    strat_logger = StrategyLogger() if args.strat_log else None
    
    logger.info("")
    logger.info("Configuration:")
    logger.info(f"  Symbols: {', '.join(strategy_config.get_enabled_symbols())}")
    logger.info(f"  Update: {args.update_interval}s | Cycle: {args.cycle_interval}s | Max Age: {args.max_order_age}m")
    logger.info(f"  Mode: {'PAPER' if IS_PAPER else 'LIVE'} Trading")
    
    last_cycle_time = 0
    last_update_time = 0
    
    # Check market status
    if not is_market_open():
        logger.info("")
        logger.info("Market Status: CLOSED")
        if args.once:
            logger.info("Exiting (--once flag set and market is closed)")
            return
        else:
            logger.info("Waiting for market open...")
    else:
        logger.info("")
        logger.info("Market Status: OPEN")
    
    try:
        while not should_exit:
            # Wait for market to open
            if not is_market_open():
                if args.once:
                    logger.warning("Market is closed and --once flag is set, exiting")
                    break
                wait_for_market_open()
                if should_exit:
                    break
            
            current_time = time.time()
            
            # Run strategy cycle
            if current_time - last_cycle_time >= args.cycle_interval:
                print_elite_header()
                
                try:
                    run_strategy_cycle(client, order_manager, state_manager, db, strat_logger)
                except Exception as e:
                    logger.error(f"Error in strategy cycle: {str(e)}", exc_info=True)
                
                last_cycle_time = current_time
                
                if args.once:
                    logger.info("\n--once flag set, exiting after one cycle")
                    break
                else:
                    time_until_next = args.cycle_interval
                    display_footer(time_until_next)
            
            # Update pending orders
            if current_time - last_update_time >= args.update_interval:
                if order_manager.has_pending_orders():
                    logger.info("Updating pending orders...")
                    
                    try:
                        results = update_filled_orders(order_manager, db)
                        
                        # Log results
                        filled = [oid for oid, status in results.items() if status == 'filled']
                        repriced = [oid for oid, status in results.items() if status == 'repriced']
                        expired = [oid for oid, status in results.items() if status == 'expired']
                        
                        if filled:
                            logger.info(f"  {len(filled)} order(s) filled")
                        if repriced:
                            logger.info(f"  {len(repriced)} order(s) repriced")
                        if expired:
                            logger.info(f"  {len(expired)} order(s) expired")
                            
                    except Exception as e:
                        logger.error(f"Error updating orders: {str(e)}", exc_info=True)
                else:
                    # Show periodic status even if no orders (but less frequently)
                    time_until_next = args.cycle_interval - (current_time - last_cycle_time)
                    if time_until_next > 0 and int(time_until_next) % 20 == 0:
                        logger.info(f"Next cycle in {int(time_until_next)} seconds...")
                
                last_update_time = current_time
            
            # Sleep briefly to avoid busy waiting
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\nShutdown requested...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
    finally:
        # Clean up
        logger.info("Cleaning up...")
        
        # Cancel all pending orders
        if order_manager.has_pending_orders():
            logger.info("Cancelling pending orders...")
            cancelled = order_manager.cancel_all_pending()
            logger.info(f"Cancelled {cancelled} order(s)")
        
        # Close database
        if db:
            db.close()
            logger.info("Database connection closed")
        
        # Print final summary
        if db:
            print_elite_header()
            logger.info("")
            logger.info("SESSION COMPLETE")
            logger.info("─" * 78)
            display_performance_dashboard(db)
        
        logger.info("")
        logger.info("─" * 78)
        logger.info("System shutdown complete.")


if __name__ == "__main__":
    main()