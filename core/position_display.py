"""
Position display utilities for showing current positions and P&L.
"""

import logging
from typing import List, Dict, Any
from alpaca.trading.enums import AssetClass
from tabulate import tabulate

logger = logging.getLogger(f"strategy.{__name__}")


def parse_option_symbol(symbol: str) -> tuple:
    """Parse option symbol to extract underlying, type, and strike"""
    # Format: AAPL240119C00150000
    if len(symbol) < 15:
        return symbol, None, None
    
    # Find where the numbers start (date)
    for i, char in enumerate(symbol):
        if char.isdigit():
            underlying = symbol[:i]
            rest = symbol[i:]
            
            # Date is 6 digits, then C/P, then strike
            if len(rest) >= 15:
                date = rest[:6]
                option_type = rest[6]
                strike_str = rest[7:]
                strike = float(strike_str) / 1000
                return underlying, option_type, strike
    
    return symbol, None, None


def display_positions(positions: List[Any], states: Dict[str, Any], 
                     position_counts: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """
    Display current positions in a formatted table with P&L.
    
    Returns:
        Dictionary with summary statistics
    """
    if not positions:
        logger.info("📊 No open positions")
        return {
            'total_pl': 0,
            'total_value': 0,
            'option_count': 0,
            'stock_count': 0
        }
    
    # Separate positions by type
    stock_positions = []
    option_positions = []
    
    for p in positions:
        if p.asset_class == AssetClass.US_EQUITY:
            stock_positions.append(p)
        elif p.asset_class == AssetClass.US_OPTION:
            option_positions.append(p)
    
    total_pl = 0
    total_value = 0
    
    # Display stock positions
    if stock_positions:
        logger.info("\n📈 STOCK POSITIONS:")
        stock_data = []
        for p in stock_positions:
            qty = int(p.qty)
            avg_price = float(p.avg_entry_price)
            current_price = float(p.current_price) if p.current_price else avg_price
            market_value = float(p.market_value)
            unrealized_pl = float(p.unrealized_pl) if p.unrealized_pl else 0
            pl_pct = (unrealized_pl / (qty * avg_price) * 100) if qty > 0 else 0
            
            # Get wheel state
            state = states.get(p.symbol, {})
            wheel_state = state.get('type', 'unknown')
            
            stock_data.append([
                p.symbol,
                f"{qty:,}",
                f"${avg_price:.2f}",
                f"${current_price:.2f}",
                f"${market_value:,.2f}",
                f"${unrealized_pl:+,.2f}",
                f"{pl_pct:+.1f}%",
                wheel_state
            ])
            
            total_pl += unrealized_pl
            total_value += market_value
        
        headers = ["Symbol", "Qty", "Avg Cost", "Current", "Value", "P&L", "P&L%", "State"]
        logger.info("\n" + tabulate(stock_data, headers=headers, tablefmt="grid"))
    
    # Display option positions
    if option_positions:
        logger.info("\n📊 OPTION POSITIONS:")
        option_data = []
        for p in option_positions:
            qty = int(p.qty)
            symbol = p.symbol
            underlying, option_type, strike = parse_option_symbol(symbol)
            
            # For short options, we show them as negative qty
            avg_price = abs(float(p.avg_entry_price))
            current_price = abs(float(p.current_price)) if p.current_price else avg_price
            market_value = abs(float(p.market_value))
            
            # For short options, unrealized P&L is reversed
            unrealized_pl = -float(p.unrealized_pl) if p.unrealized_pl else 0
            
            position_type = "Short Put" if option_type == 'P' else "Short Call"
            
            option_data.append([
                underlying,
                position_type,
                f"${strike:.2f}" if strike else "N/A",
                f"{qty:,}",
                f"${avg_price:.2f}",
                f"${current_price:.2f}",
                f"${market_value:,.2f}",
                f"${unrealized_pl:+,.2f}"
            ])
            
            total_pl += unrealized_pl
            total_value += market_value
        
        headers = ["Underlying", "Type", "Strike", "Qty", "Avg Price", "Current", "Value", "P&L"]
        logger.info("\n" + tabulate(option_data, headers=headers, tablefmt="grid"))
    
    # Display position counts by symbol
    if position_counts:
        logger.info("\n🎯 POSITION COUNTS BY SYMBOL:")
        count_data = []
        for symbol, counts in position_counts.items():
            puts = counts.get('puts', 0)
            calls = counts.get('calls', 0)
            shares = counts.get('shares', 0)
            
            # Get state
            state = states.get(symbol, {})
            wheel_state = state.get('type', 'no position')
            
            if puts > 0 or calls > 0 or shares > 0:
                count_data.append([
                    symbol,
                    f"{puts}" if puts > 0 else "-",
                    f"{calls}" if calls > 0 else "-",
                    f"{shares * 100:,}" if shares > 0 else "-",
                    wheel_state
                ])
        
        if count_data:
            headers = ["Symbol", "Puts", "Calls", "Shares", "Wheel State"]
            logger.info("\n" + tabulate(count_data, headers=headers, tablefmt="grid"))
    
    # Display summary
    logger.info("\n💰 POSITION SUMMARY:")
    logger.info(f"  Total Market Value: ${total_value:,.2f}")
    logger.info(f"  Total Unrealized P&L: ${total_pl:+,.2f}")
    if total_value > 0:
        logger.info(f"  Total P&L %: {(total_pl / total_value * 100):+.1f}%")
    logger.info(f"  Stock Positions: {len(stock_positions)}")
    logger.info(f"  Option Positions: {len(option_positions)}")
    
    return {
        'total_pl': total_pl,
        'total_value': total_value,
        'option_count': len(option_positions),
        'stock_count': len(stock_positions)
    }


def display_pending_orders(order_manager) -> None:
    """Display pending limit orders"""
    pending_orders = order_manager.get_pending_orders()
    
    if not pending_orders:
        return
    
    logger.info("\n⏳ PENDING LIMIT ORDERS:")
    order_data = []
    
    for order in pending_orders:
        age_seconds = (datetime.now() - order.created_at).total_seconds()
        age_str = f"{int(age_seconds)}s"
        
        order_data.append([
            order.underlying,
            order.order_type.upper(),
            f"${order.strike:.2f}" if order.strike else "N/A",
            order.quantity,
            f"${order.limit_price:.2f}",
            f"${order.target_price:.2f}",
            order.attempts,
            age_str
        ])
    
    headers = ["Symbol", "Type", "Strike", "Qty", "Limit", "Target", "Attempts", "Age"]
    logger.info("\n" + tabulate(order_data, headers=headers, tablefmt="grid"))


def display_database_stats(db) -> None:
    """Display database statistics"""
    if not db:
        return
    
    try:
        # Get overall summary
        summary = db.get_summary_stats()
        if summary:
            logger.info("\n📊 DATABASE STATISTICS:")
            logger.info(f"  Symbols Traded: {summary['symbols_traded']}")
            logger.info(f"  Total Put Premiums: ${summary['total_put_premiums']:.2f}")
            logger.info(f"  Total Call Premiums: ${summary['total_call_premiums']:.2f}")
            logger.info(f"  Total Premiums: ${summary['total_put_premiums'] + summary['total_call_premiums']:.2f}")
            logger.info(f"  Put Trades: {summary['put_trades']}")
            logger.info(f"  Call Trades: {summary['call_trades']}")
            
            # Get recent trades
            recent_trades = db.get_recent_trades(limit=5)
            if recent_trades:
                logger.info("\n📝 RECENT TRADES:")
                trade_data = []
                for trade in recent_trades:
                    trade_data.append([
                        trade['timestamp'][:16],  # Trim seconds
                        trade['symbol'],
                        trade['trade_type'],
                        f"${trade.get('strike_price', 0):.2f}" if trade.get('strike_price') else "N/A",
                        f"${trade['premium']:.2f}" if trade.get('premium') else "N/A"
                    ])
                
                headers = ["Time", "Symbol", "Type", "Strike", "Premium"]
                logger.info("\n" + tabulate(trade_data, headers=headers, tablefmt="grid"))
    except Exception as e:
        logger.error(f"Error displaying database stats: {str(e)}")


from datetime import datetime