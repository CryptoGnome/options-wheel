from config.config_loader import StrategyConfig

# Load configuration
_config = StrategyConfig()
_filters = _config.get_option_filters()

EXPIRATION_MIN = _filters['expiration_min_days']
EXPIRATION_MAX = _filters['expiration_max_days']
from .user_agent_mixin import UserAgentMixin 
from .retry_decorator import retry_on_failure, CircuitBreaker, RetryException
from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient, StockLatestTradeRequest
from alpaca.data.requests import OptionSnapshotRequest
from alpaca.trading.requests import GetOptionContractsRequest, MarketOrderRequest
from alpaca.trading.enums import ContractType, AssetStatus, AssetClass
from datetime import timedelta
from zoneinfo import ZoneInfo
import datetime
import logging
import requests
from typing import Optional, List, Dict, Any

logger = logging.getLogger(f"strategy.{__name__}")

# Define retryable exceptions
NETWORK_EXCEPTIONS = (requests.exceptions.RequestException, ConnectionError, TimeoutError)
API_EXCEPTIONS = (Exception,)  # Alpaca API exceptions

class TradingClientSigned(UserAgentMixin, TradingClient):
    pass

class StockHistoricalDataClientSigned(UserAgentMixin, StockHistoricalDataClient):
    pass

class OptionHistoricalDataClientSigned(UserAgentMixin, OptionHistoricalDataClient):
    pass


class BrokerClient:
    def __init__(self, api_key, secret_key, paper=True):
        self.trade_client = TradingClientSigned(api_key=api_key, secret_key=secret_key, paper=paper)
        self.trading_client = self.trade_client  # Alias for backward compatibility
        self.stock_client = StockHistoricalDataClientSigned(api_key=api_key, secret_key=secret_key)
        self.option_client = OptionHistoricalDataClientSigned(api_key=api_key, secret_key=secret_key)
        
        # Initialize circuit breakers for different API endpoints
        self.circuit_breakers = {
            'trading': CircuitBreaker(failure_threshold=3, recovery_timeout=60),
            'market_data': CircuitBreaker(failure_threshold=5, recovery_timeout=30),
            'options': CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        }

    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS)
    def get_positions(self):
        """Get all positions with retry logic."""
        try:
            positions = self.circuit_breakers['trading'].call(
                self.trade_client.get_all_positions
            )
            # Validate response
            if positions is None:
                raise ValueError("Received None from get_all_positions")
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {str(e)}")
            raise
    
    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS)
    def get_account(self):
        """Get account information including balances with retry logic."""
        try:
            account = self.circuit_breakers['trading'].call(
                self.trade_client.get_account
            )
            # Validate response
            if account is None:
                raise ValueError("Received None from get_account")
            if not hasattr(account, 'non_marginable_buying_power'):
                raise ValueError("Invalid account response: missing non_marginable_buying_power")
            return account
        except Exception as e:
            logger.error(f"Failed to get account: {str(e)}")
            raise
    
    def get_non_margin_buying_power(self) -> float:
        """Get the non-marginable buying power (cash available for trading) with validation."""
        account = self.get_account()
        # Use non_marginable_buying_power for cash-secured strategies
        buying_power = float(account.non_marginable_buying_power)
        if buying_power < 0:
            raise ValueError(f"Invalid buying power: {buying_power}")
        return buying_power
    
    def get_options_buying_power(self) -> float:
        """Get the buying power available for options trading."""
        account = self.get_account()
        # Use options_buying_power which accounts for existing positions
        buying_power = float(account.options_buying_power)
        if buying_power < 0:
            raise ValueError(f"Invalid options buying power: {buying_power}")
        return buying_power

    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS, base_delay=2.0)
    def market_sell(self, symbol: str, qty: int = 1) -> Optional[Any]:
        """Submit market sell order with retry logic and validation."""
        if not symbol or qty <= 0:
            raise ValueError(f"Invalid order parameters: symbol={symbol}, qty={qty}")
        
        req = MarketOrderRequest(
            symbol=symbol, qty=qty, side='sell', type='market', time_in_force='day'
        )
        
        try:
            order = self.circuit_breakers['trading'].call(
                self.trade_client.submit_order, req
            )
            logger.info(f"Market sell order placed: {symbol} qty={qty}")
            return order
        except Exception as e:
            logger.error(f"Failed to place market sell order for {symbol}: {str(e)}")
            raise
    
    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS, base_delay=2.0)
    def market_buy(self, symbol: str, qty: int = 1) -> Optional[Any]:
        """Submit market buy order with retry logic and validation."""
        if not symbol or qty <= 0:
            raise ValueError(f"Invalid order parameters: symbol={symbol}, qty={qty}")
        
        req = MarketOrderRequest(
            symbol=symbol, qty=qty, side='buy', type='market', time_in_force='day'
        )
        
        try:
            order = self.circuit_breakers['trading'].call(
                self.trade_client.submit_order, req
            )
            logger.info(f"Market buy order placed: {symbol} qty={qty}")
            return order
        except Exception as e:
            logger.error(f"Failed to place market buy order for {symbol}: {str(e)}")
            raise

    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS)
    def get_option_snapshot(self, symbol) -> Dict[str, Any]:
        """Get option snapshot with retry logic and validation."""
        if isinstance(symbol, str):
            req = OptionSnapshotRequest(symbol_or_symbols=symbol)
            result = self.circuit_breakers['options'].call(
                self.option_client.get_option_snapshot, req
            )
            if result is None:
                logger.warning(f"No snapshot data for symbol: {symbol}")
                return {}
            return result

        elif isinstance(symbol, list):
            if not symbol:
                return {}
            
            all_results = {}
            for i in range(0, len(symbol), 100):
                batch = symbol[i:i+100]
                req = OptionSnapshotRequest(symbol_or_symbols=batch)
                try:
                    result = self.circuit_breakers['options'].call(
                        self.option_client.get_option_snapshot, req
                    )
                    if result:
                        all_results.update(result)
                except Exception as e:
                    logger.warning(f"Failed to get snapshot for batch {i//100 + 1}: {str(e)}")
                    # Continue with other batches even if one fails
            
            return all_results

        else:
            raise ValueError("Input must be a string or list of strings representing symbols.")

    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS)
    def get_stock_latest_trade(self, symbol) -> Dict[str, Any]:
        """Get latest stock trade with retry logic and validation."""
        if not symbol:
            raise ValueError("Symbol(s) required for latest trade request")
        
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        try:
            result = self.circuit_breakers['market_data'].call(
                self.stock_client.get_stock_latest_trade, req
            )
            if result is None:
                logger.warning(f"No trade data for symbol(s): {symbol}")
                return {}
            return result
        except Exception as e:
            logger.error(f"Failed to get latest trade for {symbol}: {str(e)}")
            raise

    def get_latest_quote(self, symbol):
        """Get latest quote for a stock - alias for get_stock_latest_trade"""
        return self.get_stock_latest_trade(symbol)
    
    def get_option_contracts(self, underlying_symbols, contract_type=None):
        """Alias for get_options_contracts for backward compatibility"""
        return self.get_options_contracts(underlying_symbols, contract_type)
    
    def get_stock_bars(self, symbol, timeframe='1Day', start=None, end=None):
        """Get historical stock bars"""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        
        timeframe_map = {
            '1Day': TimeFrame.Day,
            '1Hour': TimeFrame.Hour,
            '5Min': TimeFrame(5, 'Min')
        }
        
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_map.get(timeframe, TimeFrame.Day),
            start=start,
            end=end
        )
        
        try:
            result = self.circuit_breakers['market_data'].call(
                self.stock_client.get_stock_bars, req
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get stock bars for {symbol}: {str(e)}")
            raise
    
    def get_options_contracts(self, underlying_symbols, contract_type=None):
        timezone = ZoneInfo("America/New_York")
        today = datetime.datetime.now(timezone).date()
        # Set the expiration date range for the options
        min_expiration = today + timedelta(days=EXPIRATION_MIN)
        max_expiration = today + timedelta(days=EXPIRATION_MAX)

        contract_type = {'put': ContractType.PUT, 'call': ContractType.CALL}.get(contract_type, None)

        # Set up the initial request
        req = GetOptionContractsRequest(
            underlying_symbols=underlying_symbols,
            status=AssetStatus.ACTIVE,
            expiration_date_gte=min_expiration,
            expiration_date_lte=max_expiration,
            type=contract_type,
            limit=1000,  
        )

        all_contracts = []
        page_token = None

        while True:
            if page_token:
                req.page_token = page_token

            response = self.trade_client.get_option_contracts(req)
            all_contracts.extend(response.option_contracts)

            page_token = getattr(response, "next_page_token", None)
            if not page_token:
                break

        return all_contracts
    
    @retry_on_failure(max_attempts=3, exceptions=API_EXCEPTIONS)
    def liquidate_all_positions(self):
        """Liquidate all positions with error handling."""
        try:
            positions = self.get_positions()
            if not positions:
                logger.info("No positions to liquidate")
                return
            
            options_closed = 0
            stocks_closed = 0
            errors = []
            
            # Close options first
            for p in positions:
                if p.asset_class == AssetClass.US_OPTION:
                    try:
                        self.trade_client.close_position(p.symbol)
                        options_closed += 1
                    except Exception as e:
                        logger.error(f"Failed to close option position {p.symbol}: {str(e)}")
                        errors.append((p.symbol, str(e)))
            
            # Then close stock positions
            for p in positions:
                if p.asset_class != AssetClass.US_OPTION:
                    try:
                        self.trade_client.close_position(p.symbol)
                        stocks_closed += 1
                    except Exception as e:
                        logger.error(f"Failed to close stock position {p.symbol}: {str(e)}")
                        errors.append((p.symbol, str(e)))
            
            logger.info(f"Liquidation complete: {options_closed} options, {stocks_closed} stocks closed")
            
            if errors:
                logger.warning(f"Failed to close {len(errors)} positions: {errors}")
                
        except Exception as e:
            logger.error(f"Critical error during liquidation: {str(e)}")
            raise


