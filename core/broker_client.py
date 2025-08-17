from config.params import EXPIRATION_MIN, EXPIRATION_MAX
from .user_agent_mixin import UserAgentMixin 
from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient, StockLatestTradeRequest
from alpaca.data.requests import OptionSnapshotRequest
from alpaca.trading.requests import GetOptionContractsRequest, MarketOrderRequest
from alpaca.trading.enums import ContractType, AssetStatus, AssetClass
from datetime import timedelta
from zoneinfo import ZoneInfo
import datetime

class TradingClientSigned(UserAgentMixin, TradingClient):
    pass

class StockHistoricalDataClientSigned(UserAgentMixin, StockHistoricalDataClient):
    pass

class OptionHistoricalDataClientSigned(UserAgentMixin, OptionHistoricalDataClient):
    pass


class BrokerClient:
    def __init__(self, api_key, secret_key, paper=True):
        self.trade_client = TradingClientSigned(api_key=api_key, secret_key=secret_key, paper=paper)
        self.stock_client = StockHistoricalDataClientSigned(api_key=api_key, secret_key=secret_key)
        self.option_client = OptionHistoricalDataClientSigned(api_key=api_key, secret_key=secret_key)

    def get_positions(self):
        return self.trade_client.get_all_positions()
    
    def get_account(self):
        """Get account information including balances"""
        return self.trade_client.get_account()
    
    def get_non_margin_buying_power(self):
        """Get the non-marginable buying power (cash available for trading)"""
        account = self.get_account()
        # Use non_marginable_buying_power for cash-secured strategies
        return float(account.non_marginable_buying_power)

    def market_sell(self, symbol, qty=1):
        req = MarketOrderRequest(
            symbol=symbol, qty=qty, side='sell', type='market', time_in_force='day'
        )
        self.trade_client.submit_order(req)

    def get_option_snapshot(self, symbol):
        if isinstance(symbol, str):
            req = OptionSnapshotRequest(symbol_or_symbols=symbol)
            return self.option_client.get_option_snapshot(req)

        elif isinstance(symbol, list):
            all_results = {}
            for i in range(0, len(symbol), 100):
                batch = symbol[i:i+100]
                req = OptionSnapshotRequest(symbol_or_symbols=batch)
                result = self.option_client.get_option_snapshot(req)
                all_results.update(result)
            
            return all_results


        else:
            raise ValueError("Input must be a string or list of strings representing symbols.")

    def get_stock_latest_trade(self, symbol):
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        return self.stock_client.get_stock_latest_trade(req)

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
    
    def liquidate_all_positions(self):
        positions = self.get_positions()
        to_liquidate = []
        for p in positions:
            if p.asset_class == AssetClass.US_OPTION:
                self.trade_client.close_position(p.symbol)
            else:
                to_liquidate.append(p)
        for p in to_liquidate:
            self.trade_client.close_position(p.symbol)


