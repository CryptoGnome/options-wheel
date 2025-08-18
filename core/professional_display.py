"""
Professional display utilities for a clean, trading terminal appearance.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from alpaca.trading.enums import AssetClass
from tabulate import tabulate
import os

logger = logging.getLogger(f"strategy.{__name__}")

# ANSI color codes for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    @staticmethod
    def disable():
        Colors.HEADER = ''
        Colors.BLUE = ''
        Colors.CYAN = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.RED = ''
        Colors.ENDC = ''
        Colors.BOLD = ''
        Colors.UNDERLINE = ''

# Disable colors on Windows if not supported
if os.name == 'nt':
    Colors.disable()


def format_currency(value: float, show_sign: bool = False) -> str:
    """Format currency with proper sign and color"""
    if show_sign:
        if value > 0:
            return f"{Colors.GREEN}+${abs(value):,.2f}{Colors.ENDC}"
        elif value < 0:
            return f"{Colors.RED}-${abs(value):,.2f}{Colors.ENDC}"
        else:
            return f"${value:,.2f}"
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Format percentage with color"""
    if value > 0:
        return f"{Colors.GREEN}+{value:.1f}%{Colors.ENDC}"
    elif value < 0:
        return f"{Colors.RED}{value:.1f}%{Colors.ENDC}"
    else:
        return f"{value:.1f}%"


def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    """Print a professional header"""
    width = 80
    logger.info("")
    logger.info("=" * width)
    logger.info(f"{title.center(width)}")
    logger.info("=" * width)


def print_section(title: str):
    """Print a section header"""
    logger.info("")
    logger.info(f"[{title}]")
    logger.info("-" * 40)


def parse_option_symbol(symbol: str) -> tuple:
    """Parse option symbol to extract underlying, type, and strike"""
    if len(symbol) < 15:
        return symbol, None, None
    
    for i, char in enumerate(symbol):
        if char.isdigit():
            underlying = symbol[:i]
            rest = symbol[i:]
            
            if len(rest) >= 15:
                date = rest[:6]
                option_type = rest[6]
                strike_str = rest[7:]
                strike = float(strike_str) / 1000
                return underlying, option_type, strike
    
    return symbol, None, None


def display_account_summary(account, actual_balance: float, allocated_balance: float, 
                           options_buying_power: float, portfolio_value: float,
                           balance_allocation: float):
    """Display account summary in a clean format"""
    print_section("ACCOUNT STATUS")
    
    # Calculate daily P&L if available
    daily_pl = 0
    if hasattr(account, 'equity') and hasattr(account, 'last_equity'):
        try:
            daily_pl = float(account.equity) - float(account.last_equity)
        except:
            daily_pl = 0
    
    data = [
        ["Portfolio Value", format_currency(portfolio_value)],
        ["Daily P&L", format_currency(daily_pl, show_sign=True)],
        ["Cash Balance", format_currency(actual_balance)],
        ["Allocated Funds", f"{format_currency(allocated_balance)} ({int(balance_allocation*100)}%)"],
        ["Options Buying Power", format_currency(options_buying_power)]
    ]
    
    logger.info(tabulate(data, tablefmt="plain"))


def display_positions_professional(positions: List[Any], states: Dict[str, Any], 
                                  position_counts: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Display positions in a professional format"""
    
    if not positions:
        print_section("POSITIONS")
        logger.info("No open positions")
        return {'total_pl': 0, 'total_value': 0, 'option_count': 0, 'stock_count': 0}
    
    # Separate positions
    stock_positions = []
    option_positions = []
    
    for p in positions:
        if p.asset_class == AssetClass.US_EQUITY:
            stock_positions.append(p)
        elif p.asset_class == AssetClass.US_OPTION:
            option_positions.append(p)
    
    total_pl = 0
    total_value = 0
    
    # Display options first (more relevant for wheel strategy)
    if option_positions:
        print_section("OPTION POSITIONS")
        option_data = []
        
        for p in option_positions:
            qty = int(p.qty)
            symbol = p.symbol
            underlying, option_type, strike = parse_option_symbol(symbol)
            
            avg_price = abs(float(p.avg_entry_price))
            current_price = abs(float(p.current_price)) if p.current_price else avg_price
            market_value = abs(float(p.market_value))
            # For SHORT options: profit when price goes down
            unrealized_pl = (avg_price - current_price) * abs(qty) * 100
            
            position_type = "PUT" if option_type == 'P' else "CALL"
            
            option_data.append([
                underlying,
                position_type,
                f"${strike:.0f}",
                f"{abs(qty)}",
                f"${avg_price:.2f}",
                f"${current_price:.2f}",
                format_currency(market_value),
                format_currency(unrealized_pl, show_sign=True)
            ])
            
            total_pl += unrealized_pl
            total_value += market_value
        
        headers = ["Symbol", "Type", "Strike", "Qty", "Avg", "Curr", "Value", "P&L"]
        logger.info(tabulate(option_data, headers=headers, tablefmt="simple"))
    
    # Display stocks if any
    if stock_positions:
        print_section("STOCK POSITIONS")
        stock_data = []
        
        for p in stock_positions:
            qty = int(p.qty)
            avg_price = float(p.avg_entry_price)
            current_price = float(p.current_price) if p.current_price else avg_price
            market_value = float(p.market_value)
            unrealized_pl = float(p.unrealized_pl) if p.unrealized_pl else 0
            
            state = states.get(p.symbol, {})
            wheel_state = state.get('type', 'holding').replace('_', ' ').title()
            
            stock_data.append([
                p.symbol,
                f"{qty:,}",
                f"${avg_price:.2f}",
                f"${current_price:.2f}",
                format_currency(market_value),
                format_currency(unrealized_pl, show_sign=True),
                wheel_state
            ])
            
            total_pl += unrealized_pl
            total_value += market_value
        
        headers = ["Symbol", "Shares", "Avg", "Curr", "Value", "P&L", "Status"]
        logger.info(tabulate(stock_data, headers=headers, tablefmt="simple"))
    
    # Summary line
    logger.info("")
    logger.info(f"Total Value: {format_currency(total_value)}  |  "
                f"Unrealized P&L: {format_currency(total_pl, show_sign=True)}  |  "
                f"Return: {format_percentage(total_pl/total_value*100 if total_value > 0 else 0)}")
    
    return {
        'total_pl': total_pl,
        'total_value': total_value,
        'option_count': len(option_positions),
        'stock_count': len(stock_positions)
    }


def display_wheel_status(position_counts: Dict[str, Dict[str, int]], 
                        states: Dict[str, Any], max_layers: int):
    """Display wheel strategy status"""
    print_section("WHEEL STATUS")
    
    data = []
    for symbol in sorted(position_counts.keys()):
        counts = position_counts[symbol]
        puts = counts.get('puts', 0)
        calls = counts.get('calls', 0)
        shares = counts.get('shares', 0)
        
        if puts > 0 or calls > 0 or shares > 0:
            state = states.get(symbol, {})
            wheel_state = state.get('type', 'idle').replace('_', ' ').title()
            
            # Calculate utilization
            current_layers = max(puts, shares)
            utilization = f"{current_layers}/{max_layers}"
            
            # Status indicator
            if current_layers >= max_layers:
                status = f"{Colors.YELLOW}FULL{Colors.ENDC}"
            elif current_layers > 0:
                status = f"{Colors.GREEN}ACTIVE{Colors.ENDC}"
            else:
                status = "READY"
            
            data.append([
                symbol,
                utilization,
                f"{puts}" if puts > 0 else "-",
                f"{calls}" if calls > 0 else "-",
                f"{shares*100:,}" if shares > 0 else "-",
                wheel_state,
                status
            ])
    
    if data:
        headers = ["Symbol", "Layers", "Puts", "Calls", "Shares", "State", "Status"]
        logger.info(tabulate(data, headers=headers, tablefmt="simple"))
    else:
        logger.info("No active positions")


def display_pending_orders_professional(order_manager) -> None:
    """Display pending orders in a clean format"""
    pending_orders = order_manager.get_pending_orders()
    
    if not pending_orders:
        return
    
    print_section("PENDING ORDERS")
    order_data = []
    
    for order in pending_orders:
        age_seconds = (datetime.now() - order.created_at).total_seconds()
        
        # Color code based on age
        if age_seconds > 45:
            age_str = f"{Colors.YELLOW}{int(age_seconds)}s{Colors.ENDC}"
        else:
            age_str = f"{int(age_seconds)}s"
        
        order_data.append([
            order.underlying,
            order.order_type.upper(),
            f"${order.strike:.0f}" if order.strike else "N/A",
            order.quantity,
            f"${order.limit_price:.2f}",
            f"Attempt {order.attempts}",
            age_str
        ])
    
    headers = ["Symbol", "Type", "Strike", "Qty", "Limit", "Status", "Age"]
    logger.info(tabulate(order_data, headers=headers, tablefmt="simple"))


def display_performance_summary(db) -> None:
    """Display performance summary"""
    if not db:
        return
    
    try:
        summary = db.get_summary_stats()
        if not summary:
            return
        
        print_section("PERFORMANCE METRICS")
        
        total_premiums = summary['total_put_premiums'] + summary['total_call_premiums']
        total_trades = summary['put_trades'] + summary['call_trades']
        avg_premium = total_premiums / total_trades if total_trades > 0 else 0
        
        data = [
            ["Total Premiums Collected", format_currency(total_premiums)],
            ["Put Premiums", format_currency(summary['total_put_premiums'])],
            ["Call Premiums", format_currency(summary['total_call_premiums'])],
            ["Total Trades", f"{total_trades}"],
            ["Average Premium/Trade", format_currency(avg_premium)],
            ["Symbols Traded", f"{summary['symbols_traded']}"]
        ]
        
        logger.info(tabulate(data, tablefmt="plain"))
        
    except Exception as e:
        # Silently skip if there's an error
        pass


def display_cycle_actions(actions_taken: List[str], allowed_symbols: List[str], 
                         buying_power: float):
    """Display what happened in this cycle"""
    print_section("CYCLE ACTIVITY")
    
    if actions_taken:
        for action in actions_taken:
            logger.info(f"  + {action}")
    else:
        if not allowed_symbols:
            logger.info("  - All positions at maximum capacity")
        elif buying_power <= 0:
            logger.info("  - Insufficient buying power for new positions")
        else:
            logger.info("  - No attractive opportunities found")


def display_next_cycle_info(next_cycle_seconds: int):
    """Display when next cycle will run"""
    logger.info("")
    logger.info("-" * 80)
    logger.info(f"Next cycle in {next_cycle_seconds} seconds | Press Ctrl+C to exit")
    logger.info("")