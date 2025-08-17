import logging
from .strategy import filter_underlying, filter_options, score_options, select_options
from .database import WheelDatabase
from models.contract import Contract
from config.credentials import strategy_config
import numpy as np

logger = logging.getLogger(f"strategy.{__name__}")

def sell_puts(client, allowed_symbols, buying_power, position_counts=None, db=None, strat_logger=None):
    """
    Scan allowed symbols and sell short puts up to the buying power limit.
    """
    if not allowed_symbols or buying_power <= 0:
        return

    logger.info("Searching for put options...")
    filtered_symbols = filter_underlying(client, allowed_symbols, buying_power)
    strat_logger.set_filtered_symbols(filtered_symbols)
    if len(filtered_symbols) == 0:
        logger.info("No symbols found with sufficient buying power.")
        return
    option_contracts = client.get_options_contracts(filtered_symbols, 'put')
    snapshots = client.get_option_snapshot([c.symbol for c in option_contracts])
    put_options = filter_options([Contract.from_contract_snapshot(contract, snapshots.get(contract.symbol, None)) for contract in option_contracts if snapshots.get(contract.symbol, None)])
    if strat_logger:
        strat_logger.log_put_options([p.to_dict() for p in put_options])
    
    if put_options:
        logger.info("Scoring put options...")
        scores = score_options(put_options)
        put_options = select_options(put_options, scores, max_per_symbol=strategy_config.get_max_wheel_layers(), position_counts=position_counts)
        for p in put_options:
            buying_power -= 100 * p.strike 
            if buying_power < 0:
                break
            logger.info(f"Selling put: {p.symbol}")
            client.market_sell(p.symbol)
            
            # Track in database
            if db:
                db.add_premium(
                    symbol=p.underlying,
                    option_type='P',
                    strike_price=p.strike,
                    premium=p.bid_price,
                    contracts=1,
                    expiration_date=p.expiration,
                    notes=f"Delta: {p.delta:.3f}, DTE: {p.dte}"
                )
                
                db.add_trade(
                    symbol=p.underlying,
                    trade_type='sell_put',
                    quantity=1,
                    price=p.bid_price,
                    strike_price=p.strike,
                    expiration_date=p.expiration,
                    premium=p.bid_price
                )
            
            if strat_logger:
                strat_logger.log_sold_puts([p.to_dict()])
    else:
        logger.info("No put options found with sufficient delta and open interest.")

def sell_calls(client, symbol, purchase_price, stock_qty, db=None, strat_logger=None):
    """
    Select and sell covered calls.
    
    Args:
        client: Broker client
        symbol: Stock symbol
        purchase_price: Original average entry price
        stock_qty: Number of shares owned
        adjusted_price: Premium-adjusted cost basis (if None, uses purchase_price)
        premium_tracker: PremiumTracker instance for recording premiums
        strat_logger: Strategy logger
    """
    if stock_qty < 100:
        msg = f"Not enough shares of {symbol} to cover short calls!  Only {stock_qty} shares are held and at least 100 are needed!"
        logger.error(msg)
        raise ValueError(msg)

    # Get adjusted cost basis from database if available
    strike_filter_price = purchase_price
    if db:
        cost_data = db.get_adjusted_cost_basis(symbol)
        if cost_data:
            strike_filter_price = cost_data['adjusted_cost']
            logger.info(f"Using adjusted cost basis from database: ${strike_filter_price:.2f}")
            logger.info(f"Original: ${cost_data['original_cost']:.2f}, Premiums collected: ${cost_data['total_premiums']:.2f}")
    
    logger.info(f"Searching for call options on {symbol}...")
    
    # Filter calls using the adjusted cost basis for better exit opportunities
    call_options = filter_options(
        [Contract.from_contract(option, client) for option in client.get_options_contracts([symbol], 'call')], 
        strike_filter_price
    )
    if strat_logger:
        strat_logger.log_call_options([c.to_dict() for c in call_options])

    if call_options:
        scores = score_options(call_options)
        contract = call_options[np.argmax(scores)]
        logger.info(f"Selling call option: {contract.symbol} (strike: ${contract.strike:.2f})")
        client.market_sell(contract.symbol)
        
        # Track in database
        if db:
            db.add_premium(
                symbol=symbol,
                option_type='C',
                strike_price=contract.strike,
                premium=contract.bid_price,
                contracts=1,
                expiration_date=contract.expiration,
                notes=f"Delta: {contract.delta:.3f}, DTE: {contract.dte}"
            )
            
            db.add_trade(
                symbol=symbol,
                trade_type='sell_call',
                quantity=1,
                price=contract.bid_price,
                strike_price=contract.strike,
                expiration_date=contract.expiration,
                premium=contract.bid_price
            )
            
            # Get updated stats
            stats = db.get_summary_stats(symbol)
            if stats:
                logger.info(f"Total premiums for {symbol} - Puts: ${stats['total_put_premiums']:.2f}, Calls: ${stats['total_call_premiums']:.2f}")
        
        if strat_logger:
            strat_logger.log_sold_calls(contract.to_dict())
    else:
        logger.info(f"No viable call options found for {symbol}")