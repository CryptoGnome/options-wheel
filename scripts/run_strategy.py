from pathlib import Path
from core.broker_client import BrokerClient
from core.execution import sell_puts, sell_calls
from core.state_manager import update_state, calculate_risk, count_positions_by_symbol
from core.database import WheelDatabase
from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER, BALANCE_ALLOCATION, MAX_POSITIONS_PER_SYMBOL
from config.params import MAX_RISK
from logging.strategy_logger import StrategyLogger
from logging.logger_setup import setup_logger
from core.cli_args import parse_args

def main():
    args = parse_args()
    
    # Initialize two separate loggers and database
    strat_logger = StrategyLogger(enabled=args.strat_log)  # custom JSON logger used to persist strategy-specific state (e.g. trades, symbols, PnL).
    logger = setup_logger(level=args.log_level, to_file=args.log_to_file) # standard Python logger used for general runtime messages, debugging, and error reporting.
    db = WheelDatabase()  # SQLite database for tracking positions and premiums

    strat_logger.set_fresh_start(args.fresh_start)

    SYMBOLS_FILE = Path(__file__).parent.parent / "config" / "symbol_list.txt"
    with open(SYMBOLS_FILE, 'r') as file:
        SYMBOLS = [line.strip() for line in file.readlines()]

    client = BrokerClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper=IS_PAPER)

    # Get actual account balance
    actual_balance = client.get_non_margin_buying_power()
    allocated_balance = actual_balance * BALANCE_ALLOCATION
    logger.info(f"Account balance: ${actual_balance:.2f}, Allocated for trading: ${allocated_balance:.2f} ({BALANCE_ALLOCATION*100:.0f}%)")
    
    if args.fresh_start:
        logger.info("Running in fresh start mode — liquidating all positions.")
        client.liquidate_all_positions()
        allowed_symbols = SYMBOLS
        buying_power = min(allocated_balance, MAX_RISK)  # Use lesser of allocated balance or MAX_RISK
    else:
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
            current_put_count = position_counts.get(symbol, {}).get('puts', 0)
            
            # Allow selling more puts if under the max position limit
            # This enables averaging down when assigned
            if current_put_count < MAX_POSITIONS_PER_SYMBOL:
                allowed_symbols.append(symbol)
                if symbol in position_counts:
                    logger.info(f"{symbol}: {current_put_count}/{MAX_POSITIONS_PER_SYMBOL} put positions used")
        
        # Calculate available buying power
        buying_power = min(allocated_balance - current_risk, MAX_RISK - current_risk)
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
