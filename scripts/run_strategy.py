from pathlib import Path
from core.broker_client import BrokerClient
from core.execution import sell_puts, sell_calls
from core.state_manager import update_state, calculate_risk, count_positions_by_symbol
from core.database import WheelDatabase
from core.rolling import process_rolls
from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER, strategy_config
from strategy_logging.strategy_logger import StrategyLogger
from strategy_logging.logger_setup import setup_logger
from core.cli_args import parse_args

def main():
    args = parse_args()
    
    # Initialize two separate loggers and database
    strat_logger = StrategyLogger(enabled=args.strat_log)  # custom JSON logger used to persist strategy-specific state (e.g. trades, symbols, PnL).
    logger = setup_logger(level=args.log_level, to_file=args.log_to_file) # standard Python logger used for general runtime messages, debugging, and error reporting.
    db = WheelDatabase()  # SQLite database for tracking positions and premiums

    strat_logger.set_fresh_start(args.fresh_start)

    # Load symbols from JSON config instead of text file
    SYMBOLS = strategy_config.get_enabled_symbols()
    if not SYMBOLS:
        logger.error("No enabled symbols found in config/strategy_config.json")
        return
    
    logger.info(f"Trading symbols: {', '.join(SYMBOLS)}")

    client = BrokerClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper=IS_PAPER)

    # Get actual account balance
    actual_balance = client.get_non_margin_buying_power()
    balance_allocation = strategy_config.get_balance_allocation()
    allocated_balance = actual_balance * balance_allocation
    logger.info(f"Account balance: ${actual_balance:.2f}, Allocated for trading: ${allocated_balance:.2f} ({balance_allocation*100:.0f}%)")
    
    if args.fresh_start:
        logger.info("Running in fresh start mode — liquidating all positions.")
        client.liquidate_all_positions()
        allowed_symbols = SYMBOLS
        buying_power = allocated_balance  # Use allocated percentage of balance
    else:
        positions = client.get_positions()
        strat_logger.add_current_positions(positions)

        # Process any rolls first (before calculating risk and states)
        rolls_executed = process_rolls(client, positions, strategy_config, db, strat_logger)
        if rolls_executed > 0:
            logger.info(f"Executed {rolls_executed} roll(s), refreshing positions")
            # Refresh positions after rolling
            positions = client.get_positions()
            strat_logger.add_current_positions(positions)

        current_risk = calculate_risk(positions)
        position_counts = count_positions_by_symbol(positions)
        
        states = update_state(positions)
        strat_logger.add_state_dict(states)

        # Sell calls on any long shares
        for symbol, state in states.items():
            if state["type"] == "long_shares":
                # Add position to database if not already tracked
                if db:
                    existing = db.get_position_history(symbol, 'stock', 'open')
                    if not existing:
                        db.add_position(symbol, 'stock', state["qty"], state["price"])
                
                sell_calls(client, symbol, state["price"], state["qty"], db, strat_logger)

        # Determine which symbols can have more positions
        allowed_symbols = []
        for symbol in SYMBOLS:
            # Get current positions for this symbol
            symbol_positions = position_counts.get(symbol, {})
            put_count = symbol_positions.get('puts', 0)
            share_lots = symbol_positions.get('shares', 0)  # Number of 100-share lots
            
            # Calculate current wheel layers (each lot of shares + its puts counts as a layer)
            current_layers = max(put_count, share_lots)
            max_layers = strategy_config.get_max_wheel_layers()
            
            # Allow new puts if under max wheel layers
            if current_layers < max_layers:
                allowed_symbols.append(symbol)
                if symbol in position_counts:
                    logger.info(f"{symbol}: {current_layers}/{max_layers} wheel layers active")
        
        # Calculate available buying power
        buying_power = allocated_balance - current_risk
        buying_power = max(0, buying_power)  # Ensure non-negative
    
    strat_logger.set_buying_power(buying_power)
    strat_logger.set_allowed_symbols(allowed_symbols)

    logger.info(f"Current buying power is ${buying_power:.2f}")
    
    # Pass position counts and database to sell_puts for multi-position support
    if not args.fresh_start:
        sell_puts(client, allowed_symbols, buying_power, position_counts, db, strat_logger)
    else:
        sell_puts(client, allowed_symbols, buying_power, db=db, strat_logger=strat_logger)

    strat_logger.save()
    
    # Log database summary
    if db:
        summary = db.get_summary_stats()
        if summary:
            logger.info(f"\nStrategy Summary:")
            logger.info(f"Symbols traded: {summary['symbols_traded']}")
            logger.info(f"Total put premiums: ${summary['total_put_premiums']:.2f}")
            logger.info(f"Total call premiums: ${summary['total_call_premiums']:.2f}")
            logger.info(f"Put trades: {summary['put_trades']}, Call trades: {summary['call_trades']}")    

if __name__ == "__main__":
    main()
