"""
Elite professional trading terminal display.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from alpaca.trading.enums import AssetClass
from tabulate import tabulate
import os

logger = logging.getLogger(f"strategy.{__name__}")


def get_timestamp():
    """Get current timestamp in market time"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ny_time = datetime.now(ZoneInfo("America/New_York"))
    return ny_time.strftime("%H:%M:%S ET")


def format_number(value: float, decimals: int = 2, show_sign: bool = False) -> str:
    """Format number with thousands separator"""
    if show_sign and value > 0:
        return f"+{value:,.{decimals}f}"
    return f"{value:,.{decimals}f}"


def format_currency(value: float, show_sign: bool = False) -> str:
    """Format currency consistently"""
    if show_sign:
        if value > 0:
            return f"+${abs(value):,.2f}"
        elif value < 0:
            return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def format_percentage(value: float, show_sign: bool = True) -> str:
    """Format percentage with consistent styling"""
    if show_sign and value > 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def parse_option_symbol(symbol: str) -> tuple:
    """Parse option symbol to extract components"""
    if len(symbol) < 15:
        return symbol, None, None
    
    for i, char in enumerate(symbol):
        if char.isdigit():
            underlying = symbol[:i]
            rest = symbol[i:]
            if len(rest) >= 15:
                option_type = rest[6]
                strike_str = rest[7:]
                strike = float(strike_str) / 1000
                return underlying, option_type, strike
    return symbol, None, None


def print_elite_header():
    """Print elite header with timestamp"""
    timestamp = get_timestamp()
    logger.info("")
    logger.info("┌" + "─" * 78 + "┐")
    logger.info(f"│ WHEELFORGE PROFESSIONAL │ {timestamp:>50} │")
    logger.info("└" + "─" * 78 + "┘")


def display_market_overview(account, balance: float, allocated: float, 
                           buying_power: float, portfolio_value: float,
                           allocation_pct: float):
    """Display market overview dashboard"""
    
    # Calculate metrics
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
    
    # Calculate utilization
    utilization = ((portfolio_value - balance) / portfolio_value * 100) if portfolio_value > 0 else 0
    
    logger.info("")
    logger.info("PORTFOLIO OVERVIEW")
    logger.info("─" * 78)
    
    # First row - key metrics
    logger.info(f"Net Value: {format_currency(portfolio_value):>15}  │  "
                f"Daily P&L: {format_currency(daily_pl, show_sign=True):>12} ({format_percentage(daily_pl_pct):>8})  │  "
                f"Utilization: {utilization:>5.1f}%")
    
    # Second row - capital allocation
    logger.info(f"Cash:      {format_currency(balance):>15}  │  "
                f"Allocated: {format_currency(allocated):>12} ({allocation_pct:.0f}%)         │  "
                f"Available:  {format_currency(buying_power):>10}")


def display_positions_elite(positions: List[Any], states: Dict[str, Any], 
                           position_counts: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Display positions in elite format"""
    
    if not positions:
        logger.info("")
        logger.info("POSITIONS")
        logger.info("─" * 78)
        logger.info("No active positions")
        return {'total_pl': 0, 'total_value': 0, 'option_count': 0, 'stock_count': 0}
    
    # Separate and sort positions
    option_positions = []
    stock_positions = []
    
    for p in positions:
        if p.asset_class == AssetClass.US_EQUITY:
            stock_positions.append(p)
        elif p.asset_class == AssetClass.US_OPTION:
            option_positions.append(p)
    
    # Sort options by underlying and strike
    option_positions.sort(key=lambda x: (parse_option_symbol(x.symbol)[0], parse_option_symbol(x.symbol)[2] or 0))
    
    total_pl = 0
    total_value = 0
    
    logger.info("")
    logger.info("ACTIVE POSITIONS")
    logger.info("─" * 78)
    
    if option_positions:
        # Group by underlying
        current_underlying = None
        
        for p in option_positions:
            qty = int(p.qty)
            symbol = p.symbol
            underlying, option_type, strike = parse_option_symbol(symbol)
            
            # Print underlying header if changed
            if underlying != current_underlying:
                if current_underlying is not None:
                    logger.info("")  # Space between symbols
                logger.info(f"  {underlying}")
                logger.info("  " + "─" * 74)
                current_underlying = underlying
            
            avg_price = abs(float(p.avg_entry_price))
            current_price = abs(float(p.current_price)) if p.current_price else avg_price
            market_value = abs(float(p.market_value))
            # For SHORT options: profit when price goes down
            unrealized_pl = (avg_price - current_price) * abs(qty) * 100
            pl_pct = (unrealized_pl / (avg_price * abs(qty) * 100) * 100) if avg_price > 0 and qty != 0 else 0
            
            # Format based on option type
            opt_type = "PUT" if option_type == 'P' else "CALL"
            
            # Calculate days to expiration
            # Extract date from symbol (format: AAPL241231P00150000)
            date_str = symbol[len(underlying):len(underlying)+6]
            try:
                exp_date = datetime.strptime(date_str, "%y%m%d")
                dte = (exp_date.date() - datetime.now().date()).days
                dte_str = f"{dte}d"
            except:
                dte_str = "N/A"
            
            # Format the line
            logger.info(f"    {opt_type:>4} ${strike:>6.0f}  │  "
                       f"Qty: {abs(qty):>2}  │  "
                       f"Entry: ${avg_price:>5.2f}  │  "
                       f"Mark: ${current_price:>5.2f}  │  "
                       f"Value: {format_currency(market_value):>9}  │  "
                       f"P&L: {format_currency(unrealized_pl, show_sign=True):>9} ({format_percentage(pl_pct):>7})  │  "
                       f"DTE: {dte_str:>3}")
            
            total_pl += unrealized_pl
            total_value += market_value
    
    if stock_positions:
        logger.info("")
        logger.info("  SHARES")
        logger.info("  " + "─" * 74)
        
        for p in stock_positions:
            qty = int(p.qty)
            avg_price = float(p.avg_entry_price)
            current_price = float(p.current_price) if p.current_price else avg_price
            market_value = float(p.market_value)
            unrealized_pl = float(p.unrealized_pl) if p.unrealized_pl else 0
            pl_pct = (unrealized_pl / (avg_price * qty) * 100) if avg_price > 0 and qty > 0 else 0
            
            state = states.get(p.symbol, {})
            status = state.get('type', 'holding').replace('_', ' ').upper()
            
            logger.info(f"  {p.symbol:>6}  │  "
                       f"Qty: {qty:>4}  │  "
                       f"Avg: ${avg_price:>7.2f}  │  "
                       f"Mark: ${current_price:>7.2f}  │  "
                       f"Value: {format_currency(market_value):>10}  │  "
                       f"P&L: {format_currency(unrealized_pl, show_sign=True):>10} ({format_percentage(pl_pct):>7})  │  "
                       f"{status:>12}")
            
            total_pl += unrealized_pl
            total_value += market_value
    
    # Summary footer
    logger.info("  " + "─" * 74)
    logger.info(f"  TOTAL: {format_currency(total_value):>12}  │  "
                f"P&L: {format_currency(total_pl, show_sign=True):>12} ({format_percentage(total_pl/total_value*100 if total_value > 0 else 0):>7})")
    
    return {
        'total_pl': total_pl,
        'total_value': total_value,
        'option_count': len(option_positions),
        'stock_count': len(stock_positions)
    }


def display_strategy_matrix(position_counts: Dict[str, Dict[str, int]], 
                           states: Dict[str, Any], max_layers: int, 
                           allowed_symbols: List[str]):
    """Display strategy status matrix"""
    logger.info("")
    logger.info("STRATEGY MATRIX")
    logger.info("─" * 78)
    
    # Header
    logger.info(f"  {'Symbol':<8} │ {'State':<12} │ {'Layers':<8} │ {'Puts':>5} │ {'Calls':>6} │ {'Shares':>7} │ {'Action':<20}")
    logger.info("  " + "─" * 74)
    
    # Get all symbols from config
    from config.credentials import strategy_config
    all_symbols = strategy_config.get_enabled_symbols()
    
    for symbol in sorted(all_symbols):
        counts = position_counts.get(symbol, {'puts': 0, 'calls': 0, 'shares': 0})
        state = states.get(symbol, {})
        
        puts = counts.get('puts', 0)
        calls = counts.get('calls', 0)
        shares = counts.get('shares', 0)
        
        # Determine state
        if puts > 0 or calls > 0 or shares > 0:
            wheel_state = state.get('type', 'idle').replace('_', ' ').upper()[:12]
        else:
            wheel_state = "IDLE"
        
        # Calculate layer usage
        current_layers = max(puts, shares)
        layer_str = f"{current_layers}/{max_layers}"
        
        # Determine action/status
        if current_layers >= max_layers:
            action = "AT CAPACITY"
        elif symbol in allowed_symbols:
            action = "SEEKING ENTRY"
        elif current_layers > 0:
            action = "MANAGING"
        else:
            action = "READY"
        
        # Format row
        puts_str = str(puts) if puts > 0 else "-"
        calls_str = str(calls) if calls > 0 else "-"
        shares_str = f"{shares*100}" if shares > 0 else "-"
        
        logger.info(f"  {symbol:<8} │ {wheel_state:<12} │ {layer_str:>8} │ {puts_str:>5} │ {calls_str:>6} │ {shares_str:>7} │ {action:<20}")


def display_performance_dashboard(db):
    """Display performance metrics dashboard"""
    if not db:
        return
    
    try:
        summary = db.get_summary_stats()
        if not summary:
            return
        
        logger.info("")
        logger.info("PERFORMANCE ANALYTICS")
        logger.info("─" * 78)
        
        total_premiums = summary['total_put_premiums'] + summary['total_call_premiums']
        total_trades = summary['put_trades'] + summary['call_trades']
        avg_premium = total_premiums / total_trades if total_trades > 0 else 0
        
        # Calculate additional metrics
        put_win_rate = (summary['total_put_premiums'] / (summary['put_trades'] * 100)) * 100 if summary['put_trades'] > 0 else 0
        
        # Two column layout
        logger.info(f"  Gross Premiums: {format_currency(total_premiums):>12}     │     "
                   f"Total Trades:    {total_trades:>6}")
        logger.info(f"  Put Premiums:   {format_currency(summary['total_put_premiums']):>12}     │     "
                   f"Put Trades:      {summary['put_trades']:>6}")
        logger.info(f"  Call Premiums:  {format_currency(summary['total_call_premiums']):>12}     │     "
                   f"Call Trades:     {summary['call_trades']:>6}")
        logger.info(f"  Avg Premium:    {format_currency(avg_premium):>12}     │     "
                   f"Active Symbols:  {summary['symbols_traded']:>6}")
        
    except Exception:
        pass


def display_pending_orders_elite(order_manager):
    """Display pending orders in elite format"""
    pending_orders = order_manager.get_pending_orders()
    
    if not pending_orders:
        return
    
    logger.info("")
    logger.info("PENDING ORDERS")
    logger.info("─" * 78)
    
    for order in pending_orders:
        age_seconds = (datetime.now() - order.created_at).total_seconds()
        time_left = 60 - age_seconds  # Assuming 60 second max
        
        # Progress bar for order age
        progress = int((age_seconds / 60) * 10)
        progress_bar = "█" * progress + "░" * (10 - progress)
        
        logger.info(f"  {order.underlying:<6} {order.order_type.upper():<4} "
                   f"${order.strike:>6.0f} @ ${order.limit_price:>5.2f}  │  "
                   f"Attempt {order.attempts}/3  │  "
                   f"[{progress_bar}] {int(time_left)}s")


def display_cycle_summary(actions_taken: List[str], allowed_symbols: List[str], 
                         buying_power: float, cycle_number: int = 0):
    """Display cycle execution summary"""
    logger.info("")
    logger.info("EXECUTION SUMMARY")
    logger.info("─" * 78)
    
    if actions_taken:
        logger.info("  Actions Executed:")
        for action in actions_taken:
            logger.info(f"    ► {action}")
    else:
        logger.info("  Status: No new positions opened")
        if not allowed_symbols:
            logger.info("    • All symbols at maximum capacity")
        elif buying_power <= 0:
            logger.info("    • Insufficient buying power")
        else:
            logger.info("    • No opportunities meeting criteria")


def display_footer(next_cycle_seconds: int):
    """Display footer with next action"""
    logger.info("")
    logger.info("─" * 78)
    
    # Create a simple progress indicator
    bars = int((60 - next_cycle_seconds) / 60 * 20)
    progress = "▓" * bars + "░" * (20 - bars)
    
    logger.info(f"Next Cycle: {next_cycle_seconds}s [{progress}]  │  System: ACTIVE  │  Ctrl+C to Exit")
    logger.info("")