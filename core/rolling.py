"""
Option rolling functionality for the wheel strategy.
Handles rolling of short puts before expiration.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from alpaca.trading.enums import AssetClass
from .utils import parse_option_symbol
from .strategy import filter_options, score_options
from models.contract import Contract

logger = logging.getLogger(f"strategy.{__name__}")

def identify_rollable_positions(positions, strategy_config):
    """
    Identify short put positions that are candidates for rolling.
    
    Args:
        positions: List of current positions
        strategy_config: Strategy configuration object
        
    Returns:
        List of tuples (position, underlying, strike, expiration) for rollable positions
    """
    rollable = []
    rolling_settings = strategy_config.get_rolling_settings()
    days_before_expiry = rolling_settings.get("days_before_expiry", 1)
    
    timezone = ZoneInfo("America/New_York")
    today = datetime.now(timezone).date()
    
    for position in positions:
        # Only consider short option positions
        if position.asset_class != AssetClass.US_OPTION:
            continue
        if int(position.qty) >= 0:  # Skip long positions
            continue
            
        # Parse option details
        underlying, option_type, strike = parse_option_symbol(position.symbol)
        
        # Only roll puts (not calls)
        if option_type != 'P':
            continue
            
        # Check if rolling is enabled for this symbol
        if not strategy_config.is_rolling_enabled_for_symbol(underlying):
            continue
        
        # Get expiration date from position symbol
        # Format: AAPL241220P00150000 -> expiration is 2024-12-20
        symbol_parts = position.symbol.replace(underlying, '')
        exp_str = symbol_parts[:6]  # YYMMDD format
        
        try:
            exp_year = 2000 + int(exp_str[:2])
            exp_month = int(exp_str[2:4])
            exp_day = int(exp_str[4:6])
            expiration = datetime(exp_year, exp_month, exp_day).date()
        except (ValueError, IndexError):
            logger.warning(f"Could not parse expiration from symbol {position.symbol}")
            continue
        
        # Check if close to expiration
        days_to_expiry = (expiration - today).days
        if days_to_expiry <= days_before_expiry:
            rollable.append({
                'position': position,
                'underlying': underlying,
                'strike': strike,
                'expiration': expiration,
                'days_to_expiry': days_to_expiry,
                'quantity': abs(int(position.qty))
            })
            logger.info(f"Identified rollable position: {position.symbol} expires in {days_to_expiry} days")
    
    return rollable

def find_roll_targets(client, rollable_position, strategy_config):
    """
    Find suitable options to roll into.
    
    Args:
        client: Broker client
        rollable_position: Dict with position details
        strategy_config: Strategy configuration object
        
    Returns:
        List of potential roll target contracts sorted by score
    """
    underlying = rollable_position['underlying']
    current_strike = rollable_position['strike']
    rolling_strategy = strategy_config.get_rolling_strategy_for_symbol(underlying)
    rolling_settings = strategy_config.get_rolling_settings()
    
    # Get available put options
    option_contracts = client.get_options_contracts([underlying], 'put')
    snapshots = client.get_option_snapshot([c.symbol for c in option_contracts])
    
    # Convert to Contract objects with market data
    put_options = [
        Contract.from_contract_snapshot(contract, snapshots.get(contract.symbol, None)) 
        for contract in option_contracts 
        if snapshots.get(contract.symbol, None)
    ]
    
    # Filter based on rolling strategy
    filtered_options = []
    for option in put_options:
        # Skip if not enough premium
        if option.bid_price < rolling_settings.get("min_premium_to_roll", 0.05):
            continue
            
        # Apply strategy-specific filters
        if rolling_strategy == "forward":
            # Roll forward: same or higher strike, later expiration
            if option.strike >= current_strike and option.dte > rollable_position['days_to_expiry']:
                filtered_options.append(option)
        elif rolling_strategy == "down":
            # Roll down: lower strike, any later expiration
            if option.strike < current_strike and option.dte > rollable_position['days_to_expiry']:
                filtered_options.append(option)
        elif rolling_strategy == "both":
            # Roll forward or down: any strike, later expiration
            if option.dte > rollable_position['days_to_expiry']:
                filtered_options.append(option)
    
    # Apply standard option filters
    filtered_options = filter_options(filtered_options)
    
    if filtered_options:
        # Score and sort options
        scores = score_options(filtered_options)
        sorted_options = sorted(zip(filtered_options, scores), key=lambda x: x[1], reverse=True)
        return [opt for opt, score in sorted_options]
    
    return []

def execute_roll(client, rollable_position, target_contract, db=None, strat_logger=None):
    """
    Execute a roll transaction: buy to close current position, sell to open new position.
    
    Args:
        client: Broker client
        rollable_position: Dict with current position details
        target_contract: Contract object to roll into
        db: Database object for tracking
        strat_logger: Strategy logger
        
    Returns:
        True if roll was successful, False otherwise
    """
    try:
        current_symbol = rollable_position['position'].symbol
        quantity = rollable_position['quantity']
        
        logger.info(f"Rolling {current_symbol} to {target_contract.symbol}")
        
        # Step 1: Buy to close the current position
        logger.info(f"Buying to close {quantity} contracts of {current_symbol}")
        client.market_buy(current_symbol, quantity)
        
        # Step 2: Sell to open the new position
        logger.info(f"Selling to open {quantity} contracts of {target_contract.symbol}")
        client.market_sell(target_contract.symbol, quantity)
        
        # Track in database if available
        if db:
            # Record the closing of the old position
            db.add_trade(
                symbol=rollable_position['underlying'],
                trade_type='buy_to_close',
                quantity=quantity,
                price=0,  # Market order, actual price unknown at submission
                strike_price=rollable_position['strike'],
                expiration_date=rollable_position['expiration'],
                premium=0,
                notes=f"Rolling position to {target_contract.symbol}"
            )
            
            # Record the opening of the new position
            db.add_premium(
                symbol=rollable_position['underlying'],
                option_type='P',
                strike_price=target_contract.strike,
                premium=target_contract.bid_price,
                contracts=quantity,
                expiration_date=target_contract.expiration,
                notes=f"Rolled from {current_symbol}, Delta: {target_contract.delta:.3f}, DTE: {target_contract.dte}"
            )
            
            db.add_trade(
                symbol=rollable_position['underlying'],
                trade_type='sell_put',
                quantity=quantity,
                price=target_contract.bid_price,
                strike_price=target_contract.strike,
                expiration_date=target_contract.expiration,
                premium=target_contract.bid_price,
                notes=f"Rolled from {current_symbol}"
            )
        
        # Log to strategy logger if available
        if strat_logger:
            strat_logger.log_roll({
                'from_symbol': current_symbol,
                'to_symbol': target_contract.symbol,
                'underlying': rollable_position['underlying'],
                'from_strike': rollable_position['strike'],
                'to_strike': target_contract.strike,
                'from_expiration': str(rollable_position['expiration']),
                'to_expiration': str(target_contract.expiration),
                'new_premium': target_contract.bid_price,
                'quantity': quantity
            })
        
        logger.info(f"Successfully rolled {current_symbol} to {target_contract.symbol}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to roll position: {e}")
        return False

def process_rolls(client, positions, strategy_config, db=None, strat_logger=None):
    """
    Main function to process all potential rolls.
    
    Args:
        client: Broker client
        positions: List of current positions
        strategy_config: Strategy configuration object
        db: Database object for tracking
        strat_logger: Strategy logger
        
    Returns:
        Number of successful rolls executed
    """
    # Check if rolling is globally enabled
    rolling_settings = strategy_config.get_rolling_settings()
    if not rolling_settings.get("enabled", False):
        return 0
    
    # Identify positions to roll
    rollable_positions = identify_rollable_positions(positions, strategy_config)
    
    if not rollable_positions:
        logger.info("No positions identified for rolling")
        return 0
    
    successful_rolls = 0
    
    for rollable in rollable_positions:
        # Find potential roll targets
        targets = find_roll_targets(client, rollable, strategy_config)
        
        if not targets:
            logger.info(f"No suitable roll targets found for {rollable['position'].symbol}")
            continue
        
        # Use the highest scored target
        target = targets[0]
        logger.info(f"Selected roll target: {target.symbol} (strike: ${target.strike:.2f}, DTE: {target.dte})")
        
        # Execute the roll
        if execute_roll(client, rollable, target, db, strat_logger):
            successful_rolls += 1
        else:
            logger.warning(f"Failed to roll {rollable['position'].symbol}")
    
    if successful_rolls > 0:
        logger.info(f"Successfully rolled {successful_rolls} position(s)")
    
    return successful_rolls