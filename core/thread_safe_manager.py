"""
Thread-safe state management for the wheel strategy.
"""
import threading
from typing import Dict, Any, Optional
from contextlib import contextmanager
import logging
from .state_manager import update_state as _update_state, calculate_risk as _calculate_risk
from .state_manager import count_positions_by_symbol as _count_positions_by_symbol

logger = logging.getLogger(f"strategy.{__name__}")

class ThreadSafeStateManager:
    """
    Thread-safe wrapper for state management operations.
    Prevents race conditions when updating positions and states.
    """
    
    def __init__(self):
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._state: Dict[str, Any] = {}
        self._position_counts: Dict[str, Dict[str, int]] = {}
        self._current_risk: float = 0.0
        
    @contextmanager
    def _acquire_lock(self, operation_name: str):
        """Context manager for acquiring lock with logging."""
        logger.debug(f"Acquiring lock for {operation_name}")
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()
            logger.debug(f"Released lock for {operation_name}")
    
    def update_state(self, positions, premium_tracker=None) -> Dict[str, Any]:
        """
        Thread-safe state update.
        
        Args:
            positions: List of current positions
            premium_tracker: Optional premium tracker for cost basis
            
        Returns:
            Updated state dictionary
        """
        with self._acquire_lock("update_state"):
            try:
                self._state = _update_state(positions, premium_tracker)
                return self._state.copy()  # Return a copy to prevent external modification
            except Exception as e:
                logger.error(f"Error updating state: {str(e)}")
                raise
    
    def calculate_risk(self, positions) -> float:
        """
        Thread-safe risk calculation.
        
        Args:
            positions: List of current positions
            
        Returns:
            Total risk amount
        """
        with self._acquire_lock("calculate_risk"):
            try:
                self._current_risk = _calculate_risk(positions)
                return self._current_risk
            except Exception as e:
                logger.error(f"Error calculating risk: {str(e)}")
                raise
    
    def count_positions_by_symbol(self, positions) -> Dict[str, Dict[str, int]]:
        """
        Thread-safe position counting.
        
        Args:
            positions: List of current positions
            
        Returns:
            Dictionary of position counts by symbol
        """
        with self._acquire_lock("count_positions"):
            try:
                self._position_counts = _count_positions_by_symbol(positions)
                return self._position_counts.copy()  # Return a copy
            except Exception as e:
                logger.error(f"Error counting positions: {str(e)}")
                raise
    
    def get_state(self, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get current state for a symbol or all symbols.
        
        Args:
            symbol: Optional symbol to get state for
            
        Returns:
            State dictionary or None if not found
        """
        with self._acquire_lock("get_state"):
            if symbol:
                return self._state.get(symbol, {}).copy()
            return self._state.copy()
    
    def get_position_count(self, symbol: str) -> Dict[str, int]:
        """
        Get position counts for a specific symbol.
        
        Args:
            symbol: Symbol to get counts for
            
        Returns:
            Dictionary with puts, calls, and shares counts
        """
        with self._acquire_lock("get_position_count"):
            return self._position_counts.get(symbol, {'puts': 0, 'calls': 0, 'shares': 0}).copy()
    
    def get_current_risk(self) -> float:
        """
        Get the current calculated risk.
        
        Returns:
            Current risk amount
        """
        with self._acquire_lock("get_current_risk"):
            return self._current_risk
    
    def is_position_allowed(self, symbol: str, max_layers: int) -> bool:
        """
        Check if a new position is allowed for a symbol.
        
        Args:
            symbol: Symbol to check
            max_layers: Maximum allowed wheel layers
            
        Returns:
            True if position is allowed, False otherwise
        """
        with self._acquire_lock("is_position_allowed"):
            counts = self._position_counts.get(symbol, {'puts': 0, 'calls': 0, 'shares': 0})
            put_count = counts.get('puts', 0)
            share_lots = counts.get('shares', 0)
            current_layers = max(put_count, share_lots)
            return current_layers < max_layers
    
    def reset(self):
        """Reset all state data."""
        with self._acquire_lock("reset"):
            self._state = {}
            self._position_counts = {}
            self._current_risk = 0.0
            logger.info("State manager reset")

# Global singleton instance
_state_manager_instance: Optional[ThreadSafeStateManager] = None
_instance_lock = threading.Lock()

def get_state_manager() -> ThreadSafeStateManager:
    """
    Get or create the singleton state manager instance.
    
    Returns:
        ThreadSafeStateManager instance
    """
    global _state_manager_instance
    
    if _state_manager_instance is None:
        with _instance_lock:
            if _state_manager_instance is None:
                _state_manager_instance = ThreadSafeStateManager()
                logger.info("Created new ThreadSafeStateManager instance")
    
    return _state_manager_instance