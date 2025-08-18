"""
Order management system for limit orders with automatic repricing.
Tracks pending orders and updates prices periodically to get fills.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from alpaca.trading import OrderStatus, OrderSide, OrderType
from alpaca.trading.requests import LimitOrderRequest, ReplaceOrderRequest

logger = logging.getLogger(f"strategy.{__name__}")


@dataclass
class PendingOrder:
    """Tracks a pending limit order"""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    limit_price: float
    target_price: float  # The price we're targeting (bid for sells, ask for buys)
    created_at: datetime
    last_updated: datetime
    order_type: str  # 'put', 'call', 'stock'
    underlying: str
    strike: Optional[float] = None
    expiration: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 10  # Maximum repricing attempts before giving up
    
    def should_update(self, update_interval: int = 60) -> bool:
        """Check if order should be repriced based on time interval"""
        return (datetime.now() - self.last_updated).total_seconds() >= update_interval
    
    def is_expired(self, max_age_minutes: int = 30) -> bool:
        """Check if order has been pending too long"""
        return (datetime.now() - self.created_at).total_seconds() >= max_age_minutes * 60


class OrderManager:
    """Manages limit orders with automatic repricing"""
    
    def __init__(self, client, update_interval: int = 60, max_order_age: int = 30):
        """
        Initialize order manager.
        
        Args:
            client: BrokerClient instance
            update_interval: Seconds between price updates (default 60)
            max_order_age: Maximum minutes to keep trying an order (default 30)
        """
        self.client = client
        self.update_interval = update_interval
        self.max_order_age = max_order_age
        self.pending_orders: Dict[str, PendingOrder] = {}
        
    def submit_limit_sell(self, symbol: str, quantity: int = 1, 
                          price_adjustment: float = 0.0,
                          order_type: str = 'option',
                          underlying: str = None,
                          strike: float = None) -> Optional[str]:
        """
        Submit a limit sell order at or near the bid price.
        
        Args:
            symbol: Option or stock symbol to sell
            quantity: Number of contracts/shares
            price_adjustment: Price adjustment from bid (positive = more aggressive)
            order_type: 'put', 'call', or 'stock'
            underlying: Underlying symbol for options
            strike: Strike price for options
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Get current quote
            snapshot = self.client.get_option_snapshot(symbol)
            if not snapshot or symbol not in snapshot:
                logger.error(f"Could not get snapshot for {symbol}")
                return None
                
            quote = snapshot[symbol].latest_quote
            if not quote:
                logger.error(f"No quote available for {symbol}")
                return None
            
            # For sells, start at the ask (we want to get filled)
            # but be willing to come down toward the bid
            bid_price = float(quote.bid_price)
            ask_price = float(quote.ask_price)
            
            # Start at mid-point for better fill
            limit_price = round((bid_price + ask_price) / 2, 2)
            limit_price = max(limit_price + price_adjustment, bid_price)  # Don't go below bid
            
            # Submit limit order
            req = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                time_in_force='day',
                limit_price=limit_price
            )
            
            order = self.client.trade_client.submit_order(req)
            
            # Track the order
            pending = PendingOrder(
                order_id=order.id,
                symbol=symbol,
                side='sell',
                quantity=quantity,
                limit_price=limit_price,
                target_price=bid_price,  # We're targeting the bid for sells
                created_at=datetime.now(),
                last_updated=datetime.now(),
                order_type=order_type,
                underlying=underlying or symbol,
                strike=strike
            )
            
            self.pending_orders[order.id] = pending
            logger.info(f"Limit sell order placed: {symbol} qty={quantity} @ ${limit_price:.2f} (bid: ${bid_price:.2f}, ask: ${ask_price:.2f})")
            
            return order.id
            
        except Exception as e:
            logger.error(f"Failed to submit limit sell order for {symbol}: {str(e)}")
            return None
    
    def submit_limit_buy(self, symbol: str, quantity: int = 1,
                        price_adjustment: float = 0.0,
                        order_type: str = 'option') -> Optional[str]:
        """
        Submit a limit buy order at or near the ask price.
        
        Args:
            symbol: Option or stock symbol to buy
            quantity: Number of contracts/shares
            price_adjustment: Price adjustment from ask (negative = more aggressive)
            order_type: 'option' or 'stock'
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Get current quote
            snapshot = self.client.get_option_snapshot(symbol)
            if not snapshot or symbol not in snapshot:
                logger.error(f"Could not get snapshot for {symbol}")
                return None
                
            quote = snapshot[symbol].latest_quote
            if not quote:
                logger.error(f"No quote available for {symbol}")
                return None
            
            # For buys, start at the bid (we want to get filled)
            # but be willing to go up toward the ask
            bid_price = float(quote.bid_price)
            ask_price = float(quote.ask_price)
            
            # Start at mid-point for better fill
            limit_price = round((bid_price + ask_price) / 2, 2)
            limit_price = min(limit_price + price_adjustment, ask_price)  # Don't go above ask
            
            # Submit limit order
            req = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                time_in_force='day',
                limit_price=limit_price
            )
            
            order = self.client.trade_client.submit_order(req)
            
            # Track the order
            pending = PendingOrder(
                order_id=order.id,
                symbol=symbol,
                side='buy',
                quantity=quantity,
                limit_price=limit_price,
                target_price=ask_price,  # We're targeting the ask for buys
                created_at=datetime.now(),
                last_updated=datetime.now(),
                order_type=order_type,
                underlying=symbol
            )
            
            self.pending_orders[order.id] = pending
            logger.info(f"Limit buy order placed: {symbol} qty={quantity} @ ${limit_price:.2f} (bid: ${bid_price:.2f}, ask: ${ask_price:.2f})")
            
            return order.id
            
        except Exception as e:
            logger.error(f"Failed to submit limit buy order for {symbol}: {str(e)}")
            return None
    
    def update_pending_orders(self) -> Dict[str, str]:
        """
        Check and update all pending orders.
        Reprices orders that haven't filled and are due for update.
        
        Returns:
            Dictionary of order_id: status
        """
        results = {}
        
        for order_id, pending in list(self.pending_orders.items()):
            try:
                # Get current order status
                order = self.client.trade_client.get_order_by_id(order_id)
                
                # Check if filled or cancelled
                if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.EXPIRED]:
                    if order.status == OrderStatus.FILLED:
                        logger.info(f"Order {order_id} filled: {pending.symbol} @ ${order.filled_avg_price:.2f}")
                        results[order_id] = 'filled'
                    else:
                        logger.info(f"Order {order_id} {order.status}: {pending.symbol}")
                        results[order_id] = str(order.status)
                    
                    # Remove from tracking
                    del self.pending_orders[order_id]
                    continue
                
                # Check if order should be cancelled (too old)
                if pending.is_expired(self.max_order_age):
                    logger.warning(f"Order {order_id} expired after {self.max_order_age} minutes, cancelling")
                    self.client.trade_client.cancel_order_by_id(order_id)
                    del self.pending_orders[order_id]
                    results[order_id] = 'expired'
                    continue
                
                # Check if we should update the price
                if pending.should_update(self.update_interval):
                    self._reprice_order(order_id, pending)
                    results[order_id] = 'repriced'
                else:
                    results[order_id] = 'pending'
                    
            except Exception as e:
                logger.error(f"Error updating order {order_id}: {str(e)}")
                results[order_id] = 'error'
        
        return results
    
    def _reprice_order(self, order_id: str, pending: PendingOrder) -> bool:
        """
        Reprice an existing order to try to get filled.
        
        Args:
            order_id: Order to reprice
            pending: PendingOrder tracking info
            
        Returns:
            True if successfully repriced, False otherwise
        """
        try:
            # Get current quote
            snapshot = self.client.get_option_snapshot(pending.symbol)
            if not snapshot or pending.symbol not in snapshot:
                logger.error(f"Could not get snapshot for {pending.symbol}")
                return False
            
            quote = snapshot[pending.symbol].latest_quote
            if not quote:
                logger.error(f"No quote available for {pending.symbol}")
                return False
            
            bid_price = float(quote.bid_price)
            ask_price = float(quote.ask_price)
            
            # Calculate new price based on how many attempts we've made
            # Get more aggressive with each attempt
            if pending.side == 'sell':
                # For sells, move toward the bid
                spread = ask_price - bid_price
                adjustment = min(pending.attempts * 0.01, spread * 0.5)  # Move up to half spread
                new_price = max(bid_price, ask_price - adjustment)
                new_price = round(new_price, 2)
            else:
                # For buys, move toward the ask
                spread = ask_price - bid_price
                adjustment = min(pending.attempts * 0.01, spread * 0.5)
                new_price = min(ask_price, bid_price + adjustment)
                new_price = round(new_price, 2)
            
            # Don't reprice if the price hasn't changed
            if new_price == pending.limit_price:
                logger.debug(f"Price unchanged for {pending.symbol}, skipping update")
                return False
            
            # Replace the order with new price
            req = ReplaceOrderRequest(
                qty=pending.quantity,
                limit_price=new_price
            )
            
            updated_order = self.client.trade_client.replace_order_by_id(order_id, req)
            
            # Update tracking
            pending.limit_price = new_price
            pending.last_updated = datetime.now()
            pending.attempts += 1
            
            logger.info(f"Repriced order {order_id}: {pending.symbol} @ ${new_price:.2f} (attempt {pending.attempts}, bid: ${bid_price:.2f}, ask: ${ask_price:.2f})")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to reprice order {order_id}: {str(e)}")
            return False
    
    def cancel_all_pending(self) -> int:
        """
        Cancel all pending orders.
        
        Returns:
            Number of orders cancelled
        """
        cancelled = 0
        for order_id in list(self.pending_orders.keys()):
            try:
                self.client.trade_client.cancel_order_by_id(order_id)
                del self.pending_orders[order_id]
                cancelled += 1
                logger.info(f"Cancelled order {order_id}")
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {str(e)}")
        
        return cancelled
    
    def get_pending_orders(self) -> List[PendingOrder]:
        """Get list of all pending orders"""
        return list(self.pending_orders.values())
    
    def has_pending_orders(self) -> bool:
        """Check if there are any pending orders"""
        return len(self.pending_orders) > 0