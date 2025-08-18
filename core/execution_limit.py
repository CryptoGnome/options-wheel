"""
Execution module using limit orders instead of market orders.
Works with OrderManager to place and manage limit orders.
"""

import logging
import datetime
from typing import List, Optional
from .strategy import filter_underlying, filter_options, score_options, select_options
from .database import WheelDatabase
from .order_manager import OrderManager
from models.contract import Contract
from config.credentials import strategy_config
import numpy as np

logger = logging.getLogger(f"strategy.{__name__}")


def sell_puts_limit(client, order_manager: OrderManager, allowed_symbols, buying_power, 
                   position_counts=None, db=None, strat_logger=None) -> List[str]:
    """
    Sell puts using limit orders.
    
    Returns:
        List of order IDs for tracking
    """
    logger.info("Searching for put options...")
    
    # Get and filter put options
    puts = filter_underlying(client, allowed_symbols)
    put_options = filter_options(client, puts)
    scores = score_options(put_options)
    selected_puts = select_options(put_options, scores)
    
    if not selected_puts:
        logger.info("No suitable put options found")
        return []
    
    logger.info("Scoring put options...")
    order_ids = []
    
    for p in selected_puts:
        # Check if we have enough buying power
        required_capital = 100 * p.strike
        if required_capital > buying_power:
            logger.info(f"Insufficient buying power for {p.symbol} (need ${required_capital:.2f}, have ${buying_power:.2f})")
            break
            
        logger.info(f"Selling put via limit order: {p.symbol}")
        
        # Submit limit sell order
        order_id = order_manager.submit_limit_sell(
            symbol=p.symbol,
            quantity=1,
            order_type='put',
            underlying=p.underlying,
            strike=p.strike
        )
        
        if order_id:
            order_ids.append(order_id)
            buying_power -= required_capital  # Reserve capital
            
            # Track in database (pending)
            if db:
                # Calculate expiration date from DTE
                expiration_date = datetime.date.today() + datetime.timedelta(days=int(p.dte))
                
                # Note: We'll update with actual fill price when order fills
                db.add_premium(
                    symbol=p.underlying,
                    option_type='P',
                    strike_price=p.strike,
                    premium=p.bid_price,  # Using bid as estimate
                    contracts=1,
                    expiration_date=expiration_date,
                    notes=f"PENDING - Delta: {p.delta:.3f}, DTE: {p.dte}"
                )
            
            if strat_logger:
                strat_logger.log_sold_puts([p.to_dict()])
                
            # Check position counts to see if we should continue
            if position_counts:
                symbol_positions = position_counts.get(p.underlying, {})
                put_count = symbol_positions.get('puts', 0) + 1  # Include pending order
                max_layers = strategy_config.get_max_wheel_layers()
                
                if put_count >= max_layers:
                    logger.info(f"Reached max wheel layers for {p.underlying}")
                    # Remove from allowed symbols for next iteration
                    if p.underlying in allowed_symbols:
                        allowed_symbols.remove(p.underlying)
    
    return order_ids


def sell_calls_limit(client, order_manager: OrderManager, symbol, entry_price, shares, 
                    db=None, strat_logger=None) -> Optional[str]:
    """
    Sell covered calls using limit orders.
    
    Returns:
        Order ID if successful, None otherwise
    """
    # Get call options
    calls = filter_underlying(client, [symbol])
    call_options = filter_options(client, calls, contract_type='C')
    
    if not call_options:
        logger.warning(f"No call options found for {symbol}")
        return None
    
    # Score and select best call
    scores = score_options(call_options)
    
    # Filter for strikes above entry price (or adjusted cost basis)
    if db:
        # Get adjusted cost basis
        position = db.get_position_history(symbol, 'stock', 'open')
        if position:
            adjusted_basis = position[0]['adjusted_cost_basis'] or entry_price
        else:
            adjusted_basis = entry_price
    else:
        adjusted_basis = entry_price
    
    # Filter calls above adjusted basis
    valid_indices = [i for i, c in enumerate(call_options) if c.strike >= adjusted_basis]
    
    if not valid_indices:
        logger.warning(f"No calls above cost basis ${adjusted_basis:.2f} for {symbol}")
        return None
    
    # Select best valid call
    valid_scores = scores[valid_indices]
    best_idx = valid_indices[np.argmax(valid_scores)]
    contract = call_options[best_idx]
    
    logger.info(f"Selling call via limit order: {contract.symbol} (strike: ${contract.strike:.2f})")
    
    # Submit limit sell order
    order_id = order_manager.submit_limit_sell(
        symbol=contract.symbol,
        quantity=1,
        order_type='call',
        underlying=symbol,
        strike=contract.strike
    )
    
    if order_id:
        # Track in database (pending)
        if db:
            # Calculate expiration date from DTE
            expiration_date = datetime.date.today() + datetime.timedelta(days=int(contract.dte))
            
            # Note: We'll update with actual fill price when order fills
            db.add_premium(
                symbol=symbol,
                option_type='C',
                strike_price=contract.strike,
                premium=contract.bid_price,  # Using bid as estimate
                contracts=1,
                expiration_date=expiration_date,
                notes=f"PENDING - Delta: {contract.delta:.3f}, DTE: {contract.dte}"
            )
            
            # Get updated stats
            stats = db.get_summary_stats(symbol)
            if stats:
                logger.info(f"Total premiums for {symbol} - Puts: ${stats['total_put_premiums']:.2f}, Calls: ${stats['total_call_premiums']:.2f}")
        
        if strat_logger:
            strat_logger.log_sold_calls([contract.to_dict()])
    
    return order_id


def update_filled_orders(order_manager: OrderManager, db: Optional[WheelDatabase] = None) -> dict:
    """
    Check for filled orders and update database with actual fill prices.
    
    Returns:
        Dictionary of order statuses
    """
    results = order_manager.update_pending_orders()
    
    if db:
        # Update database for filled orders
        for order_id, status in results.items():
            if status == 'filled':
                # Get the filled order details
                try:
                    order = order_manager.client.trade_client.get_order_by_id(order_id)
                    if order.status == OrderStatus.FILLED:
                        # Get pending order details
                        pending = order_manager.pending_orders.get(order_id)
                        if pending:
                            # Update database with actual fill price
                            fill_price = float(order.filled_avg_price)
                            
                            # Update the pending record with actual values
                            if pending.order_type in ['put', 'call']:
                                option_type = 'P' if pending.order_type == 'put' else 'C'
                                
                                # Find and update the pending record
                                # This is simplified - you might want to track order IDs in the database
                                logger.info(f"Order {order_id} filled at ${fill_price:.2f} for {pending.symbol}")
                                
                                # Add trade record with actual fill price
                                if pending.order_type == 'put':
                                    db.add_trade(
                                        symbol=pending.underlying,
                                        trade_type='sell_put',
                                        quantity=1,
                                        price=fill_price,
                                        strike_price=pending.strike,
                                        expiration_date=pending.expiration,
                                        premium=fill_price
                                    )
                                else:
                                    db.add_trade(
                                        symbol=pending.underlying,
                                        trade_type='sell_call',
                                        quantity=1,
                                        price=fill_price,
                                        strike_price=pending.strike,
                                        expiration_date=pending.expiration,
                                        premium=fill_price
                                    )
                                    
                except Exception as e:
                    logger.error(f"Error updating filled order {order_id}: {str(e)}")
    
    return results