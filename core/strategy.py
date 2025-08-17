from config.params import DELTA_MIN, DELTA_MAX, YIELD_MIN, YIELD_MAX, OPEN_INTEREST_MIN, SCORE_MIN

def filter_underlying(client, symbols, buying_power_limit):
    """
    Filter underlying symbols based on buying power.  Can add custom logic such as volatility or ranging / support metrics.
    """
    resp = client.get_stock_latest_trade(symbols)

    filtered_symbols = [symbol for symbol in resp if 100*resp[symbol].price <= buying_power_limit]

    return filtered_symbols

def filter_options(options, min_strike = 0):
    """
    Filter put options based on delta and open interest.
    """
    filtered_contracts = [contract for contract in options 
                          if contract.delta 
                          and abs(contract.delta) > DELTA_MIN 
                          and abs(contract.delta) < DELTA_MAX
                          and (contract.bid_price / contract.strike) * (365 / (contract.dte + 1)) > YIELD_MIN
                          and (contract.bid_price / contract.strike) * (365 / (contract.dte + 1)) < YIELD_MAX
                          and contract.oi 
                          and contract.oi > OPEN_INTEREST_MIN
                          and contract.strike >= min_strike]
    
    return filtered_contracts

def score_options(options):
    """
    Score options based on delta, days to expiration, and bid price.  
    The score is the annualized rate of return on selling the contract, discounted by the probability of assignment.
    """
    scores = [(1 - abs(p.delta)) * (250 / (p.dte + 5)) * (p.bid_price / p.strike) for p in options]
    return scores

def select_options(options, scores, n=None, max_per_symbol=1, position_counts=None):
    """
    Select the top n options, allowing multiple positions per underlying symbol.
    
    Args:
        options: List of option contracts
        scores: List of scores for each option
        n: Maximum total number of options to select
        max_per_symbol: Maximum positions allowed per symbol
        position_counts: Dict of current position counts by symbol
    """
    # Filter out low scores
    filtered = [(option, score) for option, score in zip(options, scores) if score > SCORE_MIN]

    # Group options by underlying and sort by score
    options_by_underlying = {}
    for option, score in filtered:
        underlying = option.underlying
        if underlying not in options_by_underlying:
            options_by_underlying[underlying] = []
        options_by_underlying[underlying].append((option, score))
    
    # Sort options within each underlying by score
    for underlying in options_by_underlying:
        options_by_underlying[underlying].sort(key=lambda x: x[1], reverse=True)
    
    # Select options respecting max_per_symbol limit
    selected_options = []
    if position_counts is None:
        position_counts = {}
    
    # Sort underlyings by their best option's score
    sorted_underlyings = sorted(
        options_by_underlying.keys(),
        key=lambda u: options_by_underlying[u][0][1],
        reverse=True
    )
    
    for underlying in sorted_underlyings:
        current_positions = position_counts.get(underlying, {}).get('puts', 0)
        positions_to_add = min(
            max_per_symbol - current_positions,
            len(options_by_underlying[underlying])
        )
        
        for i in range(positions_to_add):
            if n and len(selected_options) >= n:
                break
            selected_options.append(options_by_underlying[underlying][i][0])
        
        if n and len(selected_options) >= n:
            break
    
    return selected_options
