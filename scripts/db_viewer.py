#!/usr/bin/env python3
"""
Database viewer utility for the wheel strategy.
View positions, premiums, and cost basis information.
"""
import argparse
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.database import WheelDatabase
from datetime import datetime
from tabulate import tabulate

def view_cost_basis(db, symbol=None):
    """View cost basis information"""
    print("\n=== COST BASIS ===")
    
    if symbol:
        data = db.get_adjusted_cost_basis(symbol)
        if data:
            print(f"\nSymbol: {symbol}")
            print(f"Shares: {data['shares']}")
            print(f"Original Cost: ${data['original_cost']:.2f}")
            print(f"Total Premiums: ${data['total_premiums']:.2f}")
            print(f"Adjusted Cost: ${data['adjusted_cost']:.2f}")
            print(f"Reduction: ${data['original_cost'] - data['adjusted_cost']:.2f} ({((data['original_cost'] - data['adjusted_cost'])/data['original_cost']*100):.1f}%)")
        else:
            print(f"No cost basis data for {symbol}")
    else:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cost_basis ORDER BY symbol")
            rows = cursor.fetchall()
            
            if rows:
                headers = ["Symbol", "Shares", "Avg Cost", "Premiums", "Adjusted Cost", "Reduction %"]
                table_data = []
                for row in rows:
                    reduction_pct = ((row['avg_cost_per_share'] - row['adjusted_cost_per_share']) / row['avg_cost_per_share'] * 100)
                    table_data.append([
                        row['symbol'],
                        row['shares_owned'],
                        f"${row['avg_cost_per_share']:.2f}",
                        f"${row['total_premiums_collected']:.2f}",
                        f"${row['adjusted_cost_per_share']:.2f}",
                        f"{reduction_pct:.1f}%"
                    ])
                print(tabulate(table_data, headers=headers, tablefmt="grid"))
            else:
                print("No cost basis data found")

def view_positions(db, symbol=None, status='open'):
    """View positions"""
    print(f"\n=== POSITIONS ({status.upper()}) ===")
    
    positions = db.get_position_history(symbol=symbol, status=status)
    
    if positions:
        headers = ["ID", "Symbol", "Type", "Qty", "Entry Price", "Entry Date", "Status"]
        table_data = []
        for pos in positions:
            table_data.append([
                pos['id'],
                pos['symbol'],
                pos['position_type'],
                pos['quantity'],
                f"${pos['entry_price']:.2f}",
                pos['entry_date'][:10] if pos['entry_date'] else '',
                pos['status']
            ])
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    else:
        print(f"No {status} positions found")

def view_premiums(db, symbol=None, days_back=30):
    """View premium history"""
    print(f"\n=== PREMIUM HISTORY (Last {days_back} days) ===")
    
    premiums = db.get_premium_history(symbol=symbol, days_back=days_back)
    
    if premiums:
        headers = ["Date", "Symbol", "Type", "Strike", "Premium", "Contracts", "Status"]
        table_data = []
        total_puts = 0
        total_calls = 0
        
        for prem in premiums:
            table_data.append([
                prem['trade_date'][:10] if prem['trade_date'] else '',
                prem['symbol'],
                prem['option_type'],
                f"${prem['strike_price']:.2f}",
                f"${prem['premium_collected']:.2f}",
                prem['contracts'],
                prem['status']
            ])
            
            if prem['option_type'] == 'P':
                total_puts += prem['premium_collected'] * prem['contracts']
            else:
                total_calls += prem['premium_collected'] * prem['contracts']
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal Put Premiums: ${total_puts:.2f}")
        print(f"Total Call Premiums: ${total_calls:.2f}")
        print(f"Total All Premiums: ${total_puts + total_calls:.2f}")
    else:
        print("No premiums found")

def view_summary(db):
    """View overall summary statistics"""
    print("\n=== STRATEGY SUMMARY ===")
    
    stats = db.get_summary_stats()
    
    if stats:
        print(f"\nSymbols Traded: {stats['symbols_traded']}")
        print(f"Put Trades: {stats['put_trades']}")
        print(f"Call Trades: {stats['call_trades']}")
        print(f"Total Put Premiums: ${stats['total_put_premiums']:.2f}")
        print(f"Total Call Premiums: ${stats['total_call_premiums']:.2f}")
        print(f"Total All Premiums: ${stats['total_put_premiums'] + stats['total_call_premiums']:.2f}")
    else:
        print("No data available")

def main():
    parser = argparse.ArgumentParser(description='View wheel strategy database')
    parser.add_argument('--symbol', '-s', help='Filter by symbol')
    parser.add_argument('--positions', '-p', action='store_true', help='View positions')
    parser.add_argument('--premiums', '-r', action='store_true', help='View premiums')
    parser.add_argument('--cost-basis', '-c', action='store_true', help='View cost basis')
    parser.add_argument('--summary', '-u', action='store_true', help='View summary stats')
    parser.add_argument('--all', '-a', action='store_true', help='View all data')
    parser.add_argument('--days', '-d', type=int, default=30, help='Days back for premium history')
    parser.add_argument('--status', choices=['open', 'closed', 'all'], default='open', 
                       help='Position status filter')
    
    args = parser.parse_args()
    
    # Initialize database
    db = WheelDatabase()
    
    # If no specific view requested, show summary
    if not any([args.positions, args.premiums, args.cost_basis, args.summary, args.all]):
        args.summary = True
    
    if args.all or args.summary:
        view_summary(db)
    
    if args.all or args.cost_basis:
        view_cost_basis(db, args.symbol)
    
    if args.all or args.positions:
        if args.status == 'all':
            view_positions(db, args.symbol, 'open')
            view_positions(db, args.symbol, 'closed')
        else:
            view_positions(db, args.symbol, args.status)
    
    if args.all or args.premiums:
        view_premiums(db, args.symbol, args.days)

if __name__ == "__main__":
    main()