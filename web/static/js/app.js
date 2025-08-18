// WheelForge Dashboard JavaScript

// Initialize Socket.IO connection
const socket = io();

// Global state
let strategyRunning = false;
let pnlChart = null;
let currentChartType = 'cumulative';

// DOM Elements
const elements = {
    marketStatus: document.getElementById('market-status'),
    tradingMode: document.getElementById('trading-mode'),
    strategyToggle: document.getElementById('strategy-toggle'),
    portfolioValue: document.getElementById('portfolio-value'),
    dailyPL: document.getElementById('daily-pl'),
    cashBalance: document.getElementById('cash-balance'),
    buyingPower: document.getElementById('buying-power'),
    optionsTbody: document.getElementById('options-tbody'),
    stocksTbody: document.getElementById('stocks-tbody'),
    ordersTbody: document.getElementById('orders-tbody'),
    strategyGrid: document.getElementById('strategy-grid'),
    totalPremiums: document.getElementById('total-premiums'),
    totalTrades: document.getElementById('total-trades'),
    avgPremium: document.getElementById('avg-premium'),
    activeSymbols: document.getElementById('active-symbols'),
    totalRealizedPnl: document.getElementById('total-realized-pnl'),
    winRate: document.getElementById('win-rate'),
    symbolPerformanceTbody: document.getElementById('symbol-performance-tbody'),
    notifications: document.getElementById('notifications')
};

// Format currency
function formatCurrency(value, showSign = false) {
    const formatted = new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(Math.abs(value));
    
    if (showSign && value > 0) {
        return `+${formatted}`;
    } else if (value < 0) {
        return `-${formatted}`;
    }
    return formatted;
}

// Format percentage
function formatPercentage(value) {
    const sign = value > 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    
    elements.notifications.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Update account display
function updateAccount(data) {
    if (!data) return;
    
    elements.portfolioValue.textContent = formatCurrency(data.portfolio_value);
    
    elements.dailyPL.textContent = formatCurrency(data.daily_pl, true);
    elements.dailyPL.className = `value ${data.daily_pl >= 0 ? 'positive' : 'negative'}`;
    
    elements.cashBalance.textContent = formatCurrency(data.cash_balance);
    elements.buyingPower.textContent = formatCurrency(data.buying_power);
    
    // Update market status
    const statusDot = elements.marketStatus.querySelector('.status-dot');
    const statusText = elements.marketStatus.querySelector('.status-text');
    
    if (data.market_open) {
        elements.marketStatus.classList.add('open');
        elements.marketStatus.classList.remove('closed');
        statusText.textContent = 'Market Open';
    } else {
        elements.marketStatus.classList.add('closed');
        elements.marketStatus.classList.remove('open');
        statusText.textContent = 'Market Closed';
    }
    
    // Update trading mode
    elements.tradingMode.textContent = data.mode;
    elements.tradingMode.style.background = data.mode === 'PAPER' ? '#ffa502' : '#00ff88';
}

// Update positions display
function updatePositions(data) {
    if (!data) return;
    
    // Update options table
    const options = data.positions.filter(p => p.type === 'option');
    if (options.length > 0) {
        elements.optionsTbody.innerHTML = options.map(p => {
            const plClass = p.unrealized_pl >= 0 ? 'positive' : 'negative';
            const plPercent = p.pl_percentage ? ` (${p.pl_percentage.toFixed(1)}%)` : '';
            
            // Format DTE with color coding
            let dteClass = '';
            let dteText = p.dte !== null ? `${p.dte}d` : 'N/A';
            if (p.dte !== null) {
                if (p.dte <= 1) {
                    dteClass = 'dte-urgent';  // Red for expiring soon
                } else if (p.dte <= 7) {
                    dteClass = 'dte-warning'; // Yellow for expiring this week
                } else {
                    dteClass = 'dte-normal';  // Normal color
                }
            }
            
            return `
                <tr>
                    <td>${p.underlying}</td>
                    <td>${p.option_type}</td>
                    <td>$${p.strike.toFixed(0)}</td>
                    <td>${p.expiration || 'N/A'}</td>
                    <td class="${dteClass}">${dteText}</td>
                    <td>${p.quantity}</td>
                    <td>$${p.avg_price.toFixed(2)}</td>
                    <td>$${p.current_price.toFixed(2)}</td>
                    <td class="${plClass}">
                        ${formatCurrency(p.unrealized_pl, true)}${plPercent}
                    </td>
                </tr>
            `;
        }).join('');
    } else {
        elements.optionsTbody.innerHTML = '<tr><td colspan="9" class="empty">No option positions</td></tr>';
    }
    
    // Update stocks table
    const stocks = data.positions.filter(p => p.type === 'stock');
    if (stocks.length > 0) {
        elements.stocksTbody.innerHTML = stocks.map(p => `
            <tr>
                <td>${p.symbol}</td>
                <td>${p.quantity}</td>
                <td>$${p.avg_price.toFixed(2)}</td>
                <td>$${p.current_price.toFixed(2)}</td>
                <td>${formatCurrency(p.market_value)}</td>
                <td class="${p.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(p.unrealized_pl, true)}
                </td>
                <td>${p.state.replace('_', ' ')}</td>
            </tr>
        `).join('');
    } else {
        elements.stocksTbody.innerHTML = '<tr><td colspan="7" class="empty">No stock positions</td></tr>';
    }
}

// Update pending orders
function updateOrders(orders) {
    if (!orders || orders.length === 0) {
        elements.ordersTbody.innerHTML = '<tr><td colspan="7" class="empty">No pending orders</td></tr>';
        return;
    }
    
    elements.ordersTbody.innerHTML = orders.map(order => {
        const progress = (order.age_seconds / order.max_age_seconds) * 100;
        return `
            <tr>
                <td>${order.underlying}</td>
                <td>${order.type}</td>
                <td>${order.strike ? '$' + order.strike.toFixed(0) : '-'}</td>
                <td>${order.quantity}</td>
                <td>$${order.limit_price.toFixed(2)}</td>
                <td>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                    ${order.age_seconds}s
                </td>
                <td>
                    <button class="btn-small" onclick="cancelOrder('${order.id}')">Cancel</button>
                </td>
            </tr>
        `;
    }).join('');
}

// Update strategy matrix
function updateStrategy(data) {
    if (!data || !data.symbols) return;
    
    strategyRunning = data.running;
    elements.strategyToggle.textContent = strategyRunning ? 'Stop Strategy' : 'Start Strategy';
    elements.strategyToggle.classList.toggle('active', strategyRunning);
    
    elements.strategyGrid.innerHTML = data.symbols.map(s => {
        let statusClass = 'idle';
        let statusText = 'IDLE';
        
        if (s.current_layers >= s.max_layers) {
            statusClass = 'full';
            statusText = 'FULL';
        } else if (s.puts > 0 || s.calls > 0 || s.shares > 0) {
            statusClass = 'active';
            statusText = 'ACTIVE';
        }
        
        return `
            <div class="strategy-item">
                <div class="symbol">${s.symbol}</div>
                <div class="layers">${s.current_layers}/${s.max_layers} layers</div>
                <div>P: ${s.puts} | C: ${s.calls} | S: ${s.shares * 100}</div>
                <div class="status ${statusClass}">${statusText}</div>
            </div>
        `;
    }).join('');
}

// Update performance metrics
function updatePerformance(data) {
    if (!data) return;
    
    // Update main metrics
    elements.totalPremiums.textContent = formatCurrency(data.total_premiums || 0);
    elements.totalTrades.textContent = data.total_trades || 0;
    elements.avgPremium.textContent = formatCurrency(data.avg_premium || 0);
    elements.activeSymbols.textContent = data.symbols_traded || 0;
    
    // Update total realized P&L
    const totalPnl = data.total_realized_pnl || 0;
    elements.totalRealizedPnl.textContent = formatCurrency(totalPnl, true);
    elements.totalRealizedPnl.className = `value large ${totalPnl >= 0 ? 'positive' : 'negative'}`;
    
    // Update win rate
    elements.winRate.textContent = `${(data.win_rate || 0).toFixed(1)}%`;
    
    // Update symbol performance table
    updateSymbolPerformance(data.symbol_performance);
    
    // Update P&L chart based on current view
    updatePnLChart(data);
}

// Update symbol performance table
function updateSymbolPerformance(symbolData) {
    if (!symbolData || symbolData.length === 0) {
        elements.symbolPerformanceTbody.innerHTML = '<tr><td colspan="6" class="empty">No trading data available</td></tr>';
        return;
    }
    
    elements.symbolPerformanceTbody.innerHTML = symbolData.map(s => {
        const avgPerTrade = s.total_trades > 0 ? s.total_premiums / s.total_trades : 0;
        return `
            <tr>
                <td><strong>${s.symbol}</strong></td>
                <td class="${s.total_premiums >= 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(s.total_premiums, true)}
                </td>
                <td>${formatCurrency(s.put_premiums)}</td>
                <td>${formatCurrency(s.call_premiums)}</td>
                <td>${s.total_trades}</td>
                <td>${formatCurrency(avgPerTrade)}</td>
            </tr>
        `;
    }).join('');
}

// Update P&L chart
function updatePnLChart(data) {
    const ctx = document.getElementById('pnl-chart');
    if (!ctx) return;
    
    let chartData = {};
    
    if (currentChartType === 'cumulative') {
        // Cumulative P&L chart
        if (!data.pnl_history || data.pnl_history.length === 0) return;
        
        const dates = data.pnl_history.map(d => d.date);
        const values = data.pnl_history.map(d => d.cumulative_pnl);
        
        chartData = {
            labels: dates,
            datasets: [{
                label: 'Cumulative P&L',
                data: values,
                borderColor: '#00d4ff',
                backgroundColor: 'rgba(0, 212, 255, 0.1)',
                fill: true,
                tension: 0.1
            }]
        };
    } else if (currentChartType === 'daily') {
        // Daily income chart
        if (!data.pnl_history || data.pnl_history.length === 0) return;
        
        const dates = data.pnl_history.map(d => d.date);
        const values = data.pnl_history.map(d => d.daily_premium);
        
        chartData = {
            labels: dates,
            datasets: [{
                label: 'Daily Premium Income',
                data: values,
                backgroundColor: 'rgba(0, 255, 136, 0.6)',
                borderColor: '#00ff88',
                borderWidth: 1
            }]
        };
    } else if (currentChartType === 'symbol') {
        // By symbol chart
        if (!data.symbol_performance || data.symbol_performance.length === 0) return;
        
        const symbols = data.symbol_performance.map(s => s.symbol);
        const values = data.symbol_performance.map(s => s.total_premiums);
        
        chartData = {
            labels: symbols,
            datasets: [{
                label: 'Premium by Symbol',
                data: values,
                backgroundColor: [
                    'rgba(0, 212, 255, 0.6)',
                    'rgba(0, 255, 136, 0.6)',
                    'rgba(255, 165, 2, 0.6)',
                    'rgba(255, 71, 87, 0.6)',
                    'rgba(156, 136, 255, 0.6)'
                ],
                borderColor: [
                    '#00d4ff',
                    '#00ff88',
                    '#ffa502',
                    '#ff4757',
                    '#9c88ff'
                ],
                borderWidth: 1
            }]
        };
    }
    
    if (!pnlChart) {
        pnlChart = new Chart(ctx, {
            type: currentChartType === 'daily' || currentChartType === 'symbol' ? 'bar' : 'line',
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatCurrency(context.parsed.y);
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + (value >= 1000 ? (value/1000).toFixed(0) + 'k' : value.toFixed(0));
                            },
                            color: '#8892a0'
                        },
                        grid: {
                            color: 'rgba(42, 49, 65, 0.3)'
                        }
                    },
                    x: {
                        ticks: {
                            color: '#8892a0',
                            maxRotation: 45,
                            minRotation: 0
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    } else {
        // Update existing chart
        pnlChart.config.type = currentChartType === 'daily' || currentChartType === 'symbol' ? 'bar' : 'line';
        pnlChart.data = chartData;
        pnlChart.update();
    }
}

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        
        // Update buttons
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Update content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.add('hidden');
        });
        document.getElementById(`${tab}-tab`).classList.remove('hidden');
    });
});

// Strategy toggle
elements.strategyToggle.addEventListener('click', async () => {
    const endpoint = strategyRunning ? '/api/strategy/stop' : '/api/strategy/start';
    
    try {
        const response = await fetch(endpoint, { method: 'POST' });
        const data = await response.json();
        
        if (data.status === 'started') {
            showNotification('Strategy started successfully', 'success');
        } else if (data.status === 'stopped') {
            showNotification('Strategy stopped', 'warning');
        }
    } catch (error) {
        showNotification('Failed to toggle strategy', 'error');
    }
});

// Cancel order function
window.cancelOrder = async (orderId) => {
    try {
        const response = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
        if (response.ok) {
            showNotification('Order cancelled', 'success');
        }
    } catch (error) {
        showNotification('Failed to cancel order', 'error');
    }
};

// Socket.IO event handlers
socket.on('connect', () => {
    console.log('Connected to server');
    showNotification('Connected to trading server', 'success');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    showNotification('Disconnected from server', 'error');
});

socket.on('connected', (data) => {
    updateAccount(data.account);
    updatePositions(data.positions);
    updateOrders(data.orders);
    updateStrategy(data.status);
    updatePerformance(data.performance);
});

socket.on('update', (data) => {
    updateAccount(data.account);
    updatePositions(data.positions);
    updateOrders(data.orders);
    updateStrategy(data.status);
    updatePerformance(data.performance);
});

socket.on('order_placed', (data) => {
    showNotification(`New ${data.type} order placed for ${data.symbol || 'multiple symbols'}`, 'info');
});

socket.on('orders_filled', (data) => {
    showNotification(`${data.order_ids.length} order(s) filled`, 'success');
});

socket.on('roll_executed', (data) => {
    showNotification(`${data.count} position(s) rolled successfully`, 'info');
});

socket.on('strategy_started', () => {
    strategyRunning = true;
    elements.strategyToggle.textContent = 'Stop Strategy';
    elements.strategyToggle.classList.add('active');
});

socket.on('strategy_stopped', () => {
    strategyRunning = false;
    elements.strategyToggle.textContent = 'Start Strategy';
    elements.strategyToggle.classList.remove('active');
});

// Initial data fetch
async function loadInitialData() {
    try {
        const [account, positions, orders, performance, status] = await Promise.all([
            fetch('/api/account').then(r => r.json()),
            fetch('/api/positions').then(r => r.json()),
            fetch('/api/orders').then(r => r.json()),
            fetch('/api/performance').then(r => r.json()),
            fetch('/api/status').then(r => r.json())
        ]);
        
        updateAccount(account);
        updatePositions(positions);
        updateOrders(orders);
        updateStrategy(status);
        updatePerformance(performance);
    } catch (error) {
        console.error('Failed to load initial data:', error);
        showNotification('Failed to load data', 'error');
    }
}

// Chart tab switching
document.addEventListener('DOMContentLoaded', () => {
    // Initialize chart tabs
    document.querySelectorAll('.chart-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const chartType = btn.dataset.chart;
            
            // Update buttons
            document.querySelectorAll('.chart-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Update chart type and redraw
            currentChartType = chartType;
            
            // Request fresh data to update chart
            socket.emit('request_update');
        });
    });
    
    // Load initial data
    loadInitialData();
});

// Refresh data every 10 seconds
setInterval(() => {
    socket.emit('request_update');
}, 10000);