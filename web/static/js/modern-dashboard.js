// Modern Dashboard JavaScript
// Real-time updates, WebSocket connection, and UI interactions

// Initialize Notyf for notifications
const notyf = new Notyf({
    duration: 4000,
    position: { x: 'right', y: 'top' },
    types: [
        { type: 'success', background: '#06ffa5', icon: false },
        { type: 'error', background: '#ff006e', icon: false },
        { type: 'warning', background: '#ffbe0b', icon: false },
        { type: 'info', background: '#4361ee', icon: false }
    ]
});

// Global state
let socket = null;
let strategyRunning = false;
let currentConfig = {};
let charts = {};
let updateInterval = null;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initializeWebSocket();
    initializeTheme();
    initializeNavigation();
    initializeCharts();
    initializeEventListeners();
    loadInitialData();
});

// WebSocket Connection
function initializeWebSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('Connected to server');
        updateMarketStatus(true);
        socket.emit('request_update');
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        updateMarketStatus(false);
    });
    
    socket.on('connected', (data) => {
        updateDashboard(data);
    });
    
    socket.on('update', (data) => {
        updateDashboard(data);
    });
    
    socket.on('strategy_started', () => {
        strategyRunning = true;
        updateStrategyButton();
        notyf.success('Strategy started successfully');
    });
    
    socket.on('strategy_stopped', () => {
        strategyRunning = false;
        updateStrategyButton();
        notyf.warning('Strategy stopped');
    });
    
    socket.on('order_placed', (data) => {
        notyf.info(`New ${data.type} order placed for ${data.symbol || 'multiple symbols'}`);
    });
    
    socket.on('orders_filled', (data) => {
        notyf.success(`${data.order_ids.length} order(s) filled`);
    });
    
    socket.on('roll_executed', (data) => {
        notyf.info(`${data.count} position(s) rolled`);
    });
    
    socket.on('config_updated', (data) => {
        currentConfig = data;
        notyf.success('Configuration updated successfully');
    });
}

// Theme Management
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
    
    document.getElementById('themeToggle').addEventListener('click', toggleTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    
    // Update charts theme
    Object.values(charts).forEach(chart => {
        if (chart && chart.updateOptions) {
            chart.updateOptions({
                theme: { mode: newTheme }
            });
        }
    });
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('themeIcon');
    icon.className = theme === 'dark' ? 'ri-sun-line' : 'ri-moon-line';
}

// Navigation
function initializeNavigation() {
    const navTabs = document.querySelectorAll('.nav-tab');
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const section = tab.dataset.section;
            showSection(section);
            
            // Update active tab
            navTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
        });
    });
    
    // Position tabs
    const positionTabs = document.querySelectorAll('.position-tab');
    positionTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const type = tab.dataset.type;
            showPositionTable(type);
            
            positionTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
        });
    });
}

function showSection(sectionId) {
    const sections = document.querySelectorAll('.dashboard-section');
    sections.forEach(section => {
        section.classList.remove('active');
    });
    
    const targetSection = document.getElementById(`${sectionId}-section`);
    if (targetSection) {
        targetSection.classList.add('active');
        
        // Refresh charts when analytics section is shown
        if (sectionId === 'analytics') {
            setTimeout(() => {
                Object.values(charts).forEach(chart => {
                    if (chart && chart.render) chart.render();
                });
            }, 100);
        }
    }
}

function showPositionTable(type) {
    const tables = document.querySelectorAll('.position-table-card');
    tables.forEach(table => table.classList.remove('active'));
    
    const targetTable = document.getElementById(`${type}Table`);
    if (targetTable) {
        targetTable.classList.add('active');
    }
}

// Initialize Charts
function initializeCharts() {
    const theme = document.documentElement.getAttribute('data-theme');
    const isDark = theme === 'dark';
    
    // Performance Chart
    const performanceOptions = {
        series: [{
            name: 'Portfolio Value',
            data: []
        }],
        chart: {
            type: 'area',
            height: 400,
            toolbar: { show: false },
            background: 'transparent'
        },
        theme: { mode: theme },
        colors: ['#4361ee'],
        stroke: { curve: 'smooth', width: 2 },
        fill: {
            type: 'gradient',
            gradient: {
                shadeIntensity: 1,
                opacityFrom: 0.4,
                opacityTo: 0.1,
                stops: [0, 100]
            }
        },
        xaxis: {
            type: 'datetime',
            labels: { style: { colors: isDark ? '#a0a0a0' : '#6c757d' } }
        },
        yaxis: {
            labels: {
                style: { colors: isDark ? '#a0a0a0' : '#6c757d' },
                formatter: (val) => '$' + formatNumber(val)
            }
        },
        grid: {
            borderColor: isDark ? '#2a2a2a' : '#dee2e6',
            strokeDashArray: 4
        },
        tooltip: {
            theme: theme,
            x: { format: 'MMM dd, yyyy' },
            y: { formatter: (val) => '$' + formatNumber(val) }
        }
    };
    
    if (document.getElementById('performanceChart')) {
        charts.performance = new ApexCharts(
            document.getElementById('performanceChart'),
            performanceOptions
        );
        charts.performance.render();
    }
    
    // P&L Breakdown Chart
    const pnlBreakdownOptions = {
        series: [],
        chart: {
            type: 'donut',
            height: 350,
            background: 'transparent'
        },
        theme: { mode: theme },
        colors: ['#06ffa5', '#4361ee', '#ffbe0b'],
        labels: ['Put Premiums', 'Call Premiums', 'Realized P&L'],
        legend: {
            position: 'bottom',
            labels: { colors: isDark ? '#a0a0a0' : '#6c757d' }
        },
        tooltip: {
            theme: theme,
            y: { formatter: (val) => '$' + formatNumber(val) }
        },
        dataLabels: {
            enabled: true,
            formatter: (val) => val.toFixed(1) + '%',
            style: { fontSize: '12px' }
        }
    };
    
    if (document.getElementById('pnlBreakdownChart')) {
        charts.pnlBreakdown = new ApexCharts(
            document.getElementById('pnlBreakdownChart'),
            pnlBreakdownOptions
        );
        charts.pnlBreakdown.render();
    }
    
    // Symbol Performance Chart
    const symbolPerformanceOptions = {
        series: [{
            name: 'Total P&L',
            data: []
        }],
        chart: {
            type: 'bar',
            height: 350,
            toolbar: { show: false },
            background: 'transparent'
        },
        theme: { mode: theme },
        colors: ['#4361ee'],
        plotOptions: {
            bar: {
                horizontal: true,
                borderRadius: 4,
                dataLabels: { position: 'top' }
            }
        },
        xaxis: {
            labels: {
                style: { colors: isDark ? '#a0a0a0' : '#6c757d' },
                formatter: (val) => '$' + formatNumber(val)
            }
        },
        yaxis: {
            labels: { style: { colors: isDark ? '#a0a0a0' : '#6c757d' } }
        },
        grid: {
            borderColor: isDark ? '#2a2a2a' : '#dee2e6',
            strokeDashArray: 4
        },
        tooltip: {
            theme: theme,
            y: { formatter: (val) => '$' + formatNumber(val) }
        }
    };
    
    if (document.getElementById('symbolPerformanceChart')) {
        charts.symbolPerformance = new ApexCharts(
            document.getElementById('symbolPerformanceChart'),
            symbolPerformanceOptions
        );
        charts.symbolPerformance.render();
    }
    
    // Monthly Income Chart
    const monthlyIncomeOptions = {
        series: [{
            name: 'Premium Income',
            data: []
        }],
        chart: {
            type: 'bar',
            height: 350,
            toolbar: { show: false },
            background: 'transparent'
        },
        theme: { mode: theme },
        colors: ['#06ffa5'],
        plotOptions: {
            bar: {
                borderRadius: 4,
                columnWidth: '60%'
            }
        },
        xaxis: {
            type: 'category',
            labels: { style: { colors: isDark ? '#a0a0a0' : '#6c757d' } }
        },
        yaxis: {
            labels: {
                style: { colors: isDark ? '#a0a0a0' : '#6c757d' },
                formatter: (val) => '$' + formatNumber(val)
            }
        },
        grid: {
            borderColor: isDark ? '#2a2a2a' : '#dee2e6',
            strokeDashArray: 4
        },
        tooltip: {
            theme: theme,
            y: { formatter: (val) => '$' + formatNumber(val) }
        }
    };
    
    if (document.getElementById('monthlyIncomeChart')) {
        charts.monthlyIncome = new ApexCharts(
            document.getElementById('monthlyIncomeChart'),
            monthlyIncomeOptions
        );
        charts.monthlyIncome.render();
    }
}

// Event Listeners
function initializeEventListeners() {
    // Strategy Control
    const strategyBtn = document.getElementById('strategyControl');
    if (strategyBtn) {
        strategyBtn.addEventListener('click', toggleStrategy);
    }
    
    // Refresh Wheels
    const refreshBtn = document.getElementById('refreshWheels');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            socket.emit('request_update');
            notyf.info('Refreshing data...');
        });
    }
    
    // Chart Period Selectors
    document.querySelectorAll('.chart-period').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const period = e.target.dataset.period;
            document.querySelectorAll('.chart-period').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            updateChartPeriod(period);
        });
    });
    
    // Export Positions
    const exportBtn = document.getElementById('exportPositions');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportPositions);
    }
    
    // Configuration Form
    const configForm = document.getElementById('configForm');
    if (configForm) {
        // Allocation percentage slider
        const allocationRange = document.getElementById('allocationRange');
        const allocationInput = document.getElementById('allocationPercentage');
        
        if (allocationRange && allocationInput) {
            allocationRange.addEventListener('input', (e) => {
                allocationInput.value = e.target.value;
            });
            
            allocationInput.addEventListener('input', (e) => {
                allocationRange.value = e.target.value;
            });
        }
        
        // Save Config Button
        const saveBtn = document.getElementById('saveConfig');
        if (saveBtn) {
            saveBtn.addEventListener('click', saveConfiguration);
        }
    }
    
    // Symbol Management
    const addSymbolBtn = document.getElementById('addSymbol');
    if (addSymbolBtn) {
        addSymbolBtn.addEventListener('click', () => showModal('addSymbolModal'));
    }
    
    const confirmAddBtn = document.getElementById('confirmAddSymbol');
    if (confirmAddBtn) {
        confirmAddBtn.addEventListener('click', addNewSymbol);
    }
    
    // Modal Close Buttons
    document.querySelectorAll('.modal-close, [data-modal]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const modalId = e.target.dataset.modal || e.target.closest('[data-modal]').dataset.modal;
            hideModal(modalId);
        });
    });
}

// Load Initial Data
async function loadInitialData() {
    showLoading(true);
    
    try {
        // Load account data
        try {
            const accountResponse = await fetch('/api/account');
            if (accountResponse.ok) {
                const accountData = await accountResponse.json();
                updateAccountMetrics(accountData);
            }
        } catch (e) {
            console.warn('Failed to load account data:', e);
        }
        
        // Load positions
        try {
            const positionsResponse = await fetch('/api/positions');
            if (positionsResponse.ok) {
                const positionsData = await positionsResponse.json();
                updatePositions(positionsData);
            }
        } catch (e) {
            console.warn('Failed to load positions:', e);
        }
        
        // Load performance
        try {
            const performanceResponse = await fetch('/api/performance');
            if (performanceResponse.ok) {
                const performanceData = await performanceResponse.json();
                updatePerformance(performanceData);
            }
        } catch (e) {
            console.warn('Failed to load performance data:', e);
        }
        
        // Load strategy status
        try {
            const statusResponse = await fetch('/api/status');
            if (statusResponse.ok) {
                const statusData = await statusResponse.json();
                updateStrategyStatus(statusData);
            }
        } catch (e) {
            console.warn('Failed to load strategy status:', e);
        }
        
        // Load configuration
        try {
            const configResponse = await fetch('/api/config');
            if (configResponse.ok) {
                currentConfig = await configResponse.json();
                updateConfigForm(currentConfig);
            }
        } catch (e) {
            console.warn('Failed to load configuration:', e);
        }
        
    } catch (error) {
        console.error('Critical error loading initial data:', error);
        notyf.error('Failed to load dashboard data. Please refresh the page.');
    } finally {
        showLoading(false);
    }
}

// Update Dashboard
function updateDashboard(data) {
    if (data.account) updateAccountMetrics(data.account);
    if (data.positions) updatePositions(data.positions);
    if (data.orders) updatePendingOrders(data.orders);
    if (data.performance) updatePerformance(data.performance);
    if (data.status) updateStrategyStatus(data.status);
}

// Update Account Metrics
function updateAccountMetrics(data) {
    if (!data) return;
    
    // Safe element update helper
    const safeUpdate = (id, callback) => {
        const element = document.getElementById(id);
        if (element) {
            try {
                callback(element);
            } catch (e) {
                console.warn(`Error updating element ${id}:`, e);
            }
        }
    };
    
    // Portfolio Value
    safeUpdate('portfolioValue', el => {
        el.textContent = '$' + formatNumber(data.portfolio_value || 0);
    });
    
    // Portfolio Change
    safeUpdate('portfolioChange', el => {
        if (data.daily_pl_percentage !== undefined) {
            const change = data.daily_pl_percentage;
            el.innerHTML = `<span class="${change >= 0 ? 'positive' : 'negative'}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</span>`;
        }
    });
    
    // Daily P&L
    safeUpdate('dailyPnL', el => {
        const pl = data.daily_pl || 0;
        el.innerHTML = `<span class="${pl >= 0 ? 'positive' : 'negative'}">$${formatNumber(Math.abs(pl))}</span>`;
    });
    
    // Market Status
    safeUpdate('marketStatus', el => {
        const isOpen = data.market_open;
        el.classList.toggle('open', isOpen);
        el.classList.toggle('closed', !isOpen);
        const statusText = el.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = isOpen ? 'Market Open' : 'Market Closed';
        }
    });
    
    // Trading Mode
    safeUpdate('tradingMode', el => {
        if (data.mode) {
            el.innerHTML = `<i class="ri-${data.mode === 'PAPER' ? 'test-tube' : 'shield-check'}-line"></i><span>${data.mode}</span>`;
            el.classList.toggle('live', data.mode === 'LIVE');
        }
    });
}

// Update Positions
function updatePositions(data) {
    if (!data || !data.positions) return;
    
    const options = data.positions.filter(p => p.type === 'option');
    const stocks = data.positions.filter(p => p.type === 'stock');
    
    // Update counts with null checks
    const optionsCount = document.getElementById('optionsCount');
    if (optionsCount) optionsCount.textContent = options.length;
    
    const stocksCount = document.getElementById('stocksCount');
    if (stocksCount) stocksCount.textContent = stocks.length;
    
    // Update options table
    const optionsBody = document.getElementById('optionsTableBody');
    if (optionsBody) {
        if (options.length === 0) {
            optionsBody.innerHTML = '<tr><td colspan="10" class="empty-state">No option positions</td></tr>';
        } else {
            optionsBody.innerHTML = options.map(option => `
                <tr>
                    <td><strong>${option.underlying}</strong></td>
                    <td><span class="badge ${option.option_type === 'PUT' ? 'warning' : 'info'}">${option.option_type}</span></td>
                    <td>$${option.strike}</td>
                    <td>${option.expiration || 'N/A'}</td>
                    <td>${option.dte !== null ? option.dte : 'N/A'}</td>
                    <td>${option.quantity}</td>
                    <td>$${option.avg_price.toFixed(2)}</td>
                    <td>$${option.current_price.toFixed(2)}</td>
                    <td class="${option.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                        $${formatNumber(Math.abs(option.unrealized_pl))}
                        <small>(${option.pl_percentage.toFixed(1)}%)</small>
                    </td>
                    <td>
                        <button class="btn-icon" onclick="rollPosition('${option.symbol}')">
                            <i class="ri-refresh-line"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
        }
    }
    
    // Update stocks table
    const stocksBody = document.getElementById('stocksTableBody');
    if (stocksBody) {
        if (stocks.length === 0) {
            stocksBody.innerHTML = '<tr><td colspan="9" class="empty-state">No stock positions</td></tr>';
        } else {
            stocksBody.innerHTML = stocks.map(stock => `
                <tr>
                    <td><strong>${stock.symbol}</strong></td>
                    <td>${stock.quantity}</td>
                    <td>$${stock.avg_price.toFixed(2)}</td>
                    <td>$${stock.current_price.toFixed(2)}</td>
                    <td>$${formatNumber(stock.market_value)}</td>
                    <td class="${stock.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                        $${formatNumber(Math.abs(stock.unrealized_pl))}
                    </td>
                    <td class="${stock.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                        ${((stock.unrealized_pl / (stock.avg_price * stock.quantity)) * 100).toFixed(1)}%
                    </td>
                    <td><span class="badge">${stock.state || 'holding'}</span></td>
                    <td>
                        <button class="btn-icon" onclick="sellCall('${stock.symbol}')">
                            <i class="ri-phone-line"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
        }
    }
}

// Update Pending Orders
function updatePendingOrders(orders) {
    const ordersList = document.getElementById('ordersList');
    const pendingCount = document.getElementById('pendingCount');
    
    if (pendingCount) {
        pendingCount.textContent = orders ? orders.length : 0;
    }
    
    if (ordersList) {
        if (!orders || orders.length === 0) {
            ordersList.innerHTML = `
                <div class="empty-state">
                    <i class="ri-time-line"></i>
                    <p>No pending orders</p>
                </div>
            `;
        } else {
            ordersList.innerHTML = orders.map(order => `
                <div class="order-item">
                    <div class="order-info">
                        <div class="order-symbol">${order.underlying} ${order.type}</div>
                        <div class="order-details">
                            Strike: $${order.strike} | Qty: ${order.quantity} | Limit: $${order.limit_price}
                        </div>
                    </div>
                    <div class="order-age">
                        <div class="age-progress">
                            <div class="age-bar" style="width: ${(order.age_seconds / order.max_age_seconds) * 100}%"></div>
                        </div>
                        <span>${order.age_seconds}s</span>
                    </div>
                </div>
            `).join('');
        }
    }
}

// Update Performance
function updatePerformance(data) {
    if (!data) return;
    
    // Update metrics with null checks
    const updateElement = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    };
    
    updateElement('totalPnL', '$' + formatNumber(data.total_realized_pnl || 0));
    updateElement('totalPremiums', '$' + formatNumber(data.total_premiums || 0));
    updateElement('winRate', (data.win_rate || 0).toFixed(1) + '%');
    updateElement('totalTrades', data.total_trades || 0);
    updateElement('avgPremium', '$' + formatNumber(data.avg_premium || 0));
    updateElement('putCallRatio', `${data.put_trades || 0}:${data.call_trades || 0}`);
    
    // Calculate monthly premiums
    if (data.daily_premiums) {
        const currentMonth = new Date().getMonth();
        const monthlyTotal = Object.entries(data.daily_premiums)
            .filter(([date]) => new Date(date).getMonth() === currentMonth)
            .reduce((sum, [, amount]) => sum + amount, 0);
        document.getElementById('monthlyPremiums').textContent = '$' + formatNumber(monthlyTotal);
    }
    
    // Update charts
    updatePerformanceCharts(data);
    
    // Update performance table
    updatePerformanceTable(data.symbol_performance);
}

// Update Performance Charts
function updatePerformanceCharts(data) {
    // P&L Breakdown
    if (charts.pnlBreakdown && data.put_premiums !== undefined) {
        charts.pnlBreakdown.updateSeries([
            data.put_premiums || 0,
            data.call_premiums || 0,
            Math.max(0, data.total_realized_pnl || 0)
        ]);
    }
    
    // Symbol Performance
    if (charts.symbolPerformance && data.symbol_performance) {
        const symbols = data.symbol_performance.map(s => s.symbol);
        const values = data.symbol_performance.map(s => s.total_pnl || 0);
        
        charts.symbolPerformance.updateOptions({
            xaxis: { categories: symbols }
        });
        charts.symbolPerformance.updateSeries([{
            name: 'Total P&L',
            data: values
        }]);
    }
    
    // Monthly Income
    if (charts.monthlyIncome && data.daily_premiums) {
        const monthlyData = {};
        Object.entries(data.daily_premiums).forEach(([date, amount]) => {
            const month = new Date(date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
            monthlyData[month] = (monthlyData[month] || 0) + amount;
        });
        
        const months = Object.keys(monthlyData);
        const values = Object.values(monthlyData);
        
        charts.monthlyIncome.updateOptions({
            xaxis: { categories: months }
        });
        charts.monthlyIncome.updateSeries([{
            name: 'Premium Income',
            data: values
        }]);
    }
    
    // Performance Chart (cumulative P&L)
    if (charts.performance && data.pnl_history) {
        const series = data.pnl_history.map(point => ({
            x: new Date(point.date).getTime(),
            y: point.cumulative_pnl
        }));
        
        charts.performance.updateSeries([{
            name: 'Cumulative P&L',
            data: series
        }]);
    }
}

// Update Performance Table
function updatePerformanceTable(symbolData) {
    const tbody = document.getElementById('performanceTableBody');
    if (!tbody || !symbolData) return;
    
    if (symbolData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No trading data available</td></tr>';
    } else {
        tbody.innerHTML = symbolData.map(symbol => {
            const totalTrades = (symbol.put_trades || 0) + (symbol.call_trades || 0);
            const avgPremium = totalTrades > 0 ? (symbol.total_pnl / totalTrades) : 0;
            const winRate = symbol.win_rate || 0;
            const roi = symbol.roi || 0;
            
            return `
                <tr>
                    <td><strong>${symbol.symbol}</strong></td>
                    <td class="${symbol.total_pnl >= 0 ? 'positive' : 'negative'}">
                        $${formatNumber(Math.abs(symbol.total_pnl || 0))}
                    </td>
                    <td>$${formatNumber(symbol.put_premiums || 0)}</td>
                    <td>$${formatNumber(symbol.call_premiums || 0)}</td>
                    <td>${totalTrades}</td>
                    <td>${winRate.toFixed(1)}%</td>
                    <td>$${formatNumber(avgPremium)}</td>
                    <td class="${roi >= 0 ? 'positive' : 'negative'}">${roi.toFixed(2)}%</td>
                </tr>
            `;
        }).join('');
    }
}

// Update Strategy Status
function updateStrategyStatus(data) {
    if (!data) return;
    
    strategyRunning = data.running;
    updateStrategyButton();
    
    // Update wheels grid
    updateWheelsGrid(data.symbols);
    
    // Update active symbols count
    const activeSymbols = data.symbols ? data.symbols.filter(s => s.enabled).length : 0;
    const activeSymbolsElement = document.getElementById('activeSymbols');
    if (activeSymbolsElement) {
        activeSymbolsElement.textContent = activeSymbols;
    }
}

// Update Wheels Grid
function updateWheelsGrid(symbols) {
    const wheelsGrid = document.getElementById('wheelsGrid');
    if (!wheelsGrid || !symbols) return;
    
    if (symbols.length === 0) {
        wheelsGrid.innerHTML = '<div class="empty-state">No active wheels</div>';
    } else {
        wheelsGrid.innerHTML = symbols.map(symbol => {
            let state = 'idle';
            let stateClass = '';
            
            if (symbol.calls > 0) {
                state = 'CALL';
                stateClass = 'call';
            } else if (symbol.shares > 0) {
                state = 'SHARES';
                stateClass = 'shares';
            } else if (symbol.puts > 0) {
                state = 'PUT';
                stateClass = 'put';
            }
            
            return `
                <div class="wheel-card">
                    <div class="wheel-symbol">${symbol.symbol}</div>
                    <div class="wheel-state ${stateClass}">${state}</div>
                    <div class="wheel-info">
                        <span>Contracts: ${symbol.contracts}</span>
                        <span>Layer: ${symbol.current_layers}/${symbol.max_layers}</span>
                        <span>Can Add: ${symbol.can_add_position ? 'Yes' : 'No'}</span>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// Update Configuration Form
function updateConfigForm(config) {
    if (!config) return;
    
    // Helper to safely set element value
    const setElementValue = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.value = value;
    };
    
    const setElementChecked = (id, checked) => {
        const element = document.getElementById(id);
        if (element) element.checked = checked;
    };
    
    // Balance settings
    const allocation = (config.balance_settings?.allocation_percentage || 0) * 100;
    setElementValue('allocationPercentage', allocation);
    setElementValue('allocationRange', allocation);
    setElementValue('maxWheelLayers', config.balance_settings?.max_wheel_layers || 2);
    
    // Option filters
    setElementValue('deltaMin', config.option_filters?.delta_min || 0.15);
    setElementValue('deltaMax', config.option_filters?.delta_max || 0.30);
    setElementValue('dteMin', config.option_filters?.expiration_min_days || 0);
    setElementValue('dteMax', config.option_filters?.expiration_max_days || 21);
    setElementValue('yieldMin', config.option_filters?.yield_min || 0.04);
    setElementValue('yieldMax', config.option_filters?.yield_max || 1.00);
    setElementValue('openInterestMin', config.option_filters?.open_interest_min || 100);
    
    // Rolling settings
    setElementChecked('rollingEnabled', config.rolling_settings?.enabled || false);
    setElementValue('daysBeforeExpiry', config.rolling_settings?.days_before_expiry || 1);
    setElementValue('minPremiumToRoll', config.rolling_settings?.min_premium_to_roll || 0.05);
    setElementValue('rollDeltaTarget', config.rolling_settings?.roll_delta_target || 0.25);
    
    // Update symbols grid
    updateSymbolsGrid(config.symbols);
}

// Update Symbols Grid
function updateSymbolsGrid(symbols) {
    const symbolsGrid = document.getElementById('symbolsGrid');
    if (!symbolsGrid || !symbols) return;
    
    symbolsGrid.innerHTML = Object.entries(symbols).map(([symbol, config]) => `
        <div class="symbol-card" data-symbol="${symbol}">
            <div class="symbol-header">
                <div class="symbol-name">${symbol}</div>
                <label class="switch-label symbol-toggle">
                    <input type="checkbox" class="switch-input" ${config.enabled ? 'checked' : ''} 
                           onchange="toggleSymbol('${symbol}', this.checked)">
                    <span class="switch-slider"></span>
                </label>
            </div>
            <div class="symbol-info">
                <div class="symbol-detail">
                    <label>Contracts:</label>
                    <span>${config.contracts}</span>
                </div>
                <div class="symbol-detail">
                    <label>Rolling:</label>
                    <span>${config.rolling?.enabled ? 'Yes' : 'No'}</span>
                </div>
            </div>
            <div class="symbol-actions">
                <button class="btn-icon" onclick="editSymbol('${symbol}')">
                    <i class="ri-edit-line"></i>
                </button>
                <button class="btn-icon" onclick="removeSymbol('${symbol}')">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Strategy Control
async function toggleStrategy() {
    const btn = document.getElementById('strategyControl');
    btn.disabled = true;
    
    try {
        const endpoint = strategyRunning ? '/api/strategy/stop' : '/api/strategy/start';
        const response = await fetch(endpoint, { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            strategyRunning = !strategyRunning;
            updateStrategyButton();
        } else {
            notyf.error('Failed to toggle strategy');
        }
    } catch (error) {
        console.error('Error toggling strategy:', error);
        notyf.error('Failed to toggle strategy');
    } finally {
        btn.disabled = false;
    }
}

function updateStrategyButton() {
    const btn = document.getElementById('strategyControl');
    if (btn) {
        btn.classList.toggle('running', strategyRunning);
        btn.innerHTML = strategyRunning 
            ? '<i class="ri-stop-circle-line"></i><span>Stop Strategy</span>'
            : '<i class="ri-play-circle-line"></i><span>Start Strategy</span>';
    }
}

// Save Configuration
async function saveConfiguration() {
    showLoading(true);
    
    try {
        // Helper to safely get element value
        const getElementValue = (id, defaultValue = 0) => {
            const element = document.getElementById(id);
            return element ? element.value : defaultValue;
        };
        
        const getElementChecked = (id, defaultValue = false) => {
            const element = document.getElementById(id);
            return element ? element.checked : defaultValue;
        };
        
        // Gather form data with safe access
        const configData = {
            balance_settings: {
                allocation_percentage: parseFloat(getElementValue('allocationPercentage', 50)) / 100,
                max_wheel_layers: parseInt(getElementValue('maxWheelLayers', 2))
            },
            option_filters: {
                delta_min: parseFloat(getElementValue('deltaMin', 0.15)),
                delta_max: parseFloat(getElementValue('deltaMax', 0.30)),
                yield_min: parseFloat(getElementValue('yieldMin', 0.04)),
                yield_max: parseFloat(getElementValue('yieldMax', 1.00)),
                expiration_min_days: parseInt(getElementValue('dteMin', 0)),
                expiration_max_days: parseInt(getElementValue('dteMax', 21)),
                open_interest_min: parseInt(getElementValue('openInterestMin', 100)),
                score_min: currentConfig.option_filters?.score_min || 0.05
            },
            rolling_settings: {
                enabled: getElementChecked('rollingEnabled', false),
                days_before_expiry: parseInt(getElementValue('daysBeforeExpiry', 1)),
                min_premium_to_roll: parseFloat(getElementValue('minPremiumToRoll', 0.05)),
                roll_delta_target: parseFloat(getElementValue('rollDeltaTarget', 0.25))
            },
            symbols: currentConfig.symbols || {},
            default_contracts: currentConfig.default_contracts || 1
        };
        
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        if (response.ok) {
            currentConfig = configData;
            notyf.success('Configuration saved successfully');
        } else {
            throw new Error('Failed to save configuration');
        }
    } catch (error) {
        console.error('Error saving configuration:', error);
        notyf.error('Failed to save configuration');
    } finally {
        showLoading(false);
    }
}

// Symbol Management
function toggleSymbol(symbol, enabled) {
    if (currentConfig.symbols && currentConfig.symbols[symbol]) {
        currentConfig.symbols[symbol].enabled = enabled;
    }
}

function editSymbol(symbol) {
    // TODO: Implement symbol editing modal
    notyf.info(`Edit ${symbol} - Feature coming soon`);
}

async function removeSymbol(symbol) {
    if (confirm(`Are you sure you want to remove ${symbol}?`)) {
        if (currentConfig.symbols && currentConfig.symbols[symbol]) {
            delete currentConfig.symbols[symbol];
            await saveConfiguration();
            updateSymbolsGrid(currentConfig.symbols);
        }
    }
}

async function addNewSymbol() {
    const symbol = document.getElementById('newSymbol').value.toUpperCase();
    const contracts = parseInt(document.getElementById('newSymbolContracts').value);
    const enabled = document.getElementById('newSymbolEnabled').checked;
    
    if (!symbol) {
        notyf.error('Please enter a symbol');
        return;
    }
    
    if (!currentConfig.symbols) {
        currentConfig.symbols = {};
    }
    
    currentConfig.symbols[symbol] = {
        enabled: enabled,
        contracts: contracts,
        rolling: {
            enabled: false,
            strategy: 'both'
        }
    };
    
    await saveConfiguration();
    updateSymbolsGrid(currentConfig.symbols);
    hideModal('addSymbolModal');
    
    // Reset form
    document.getElementById('addSymbolForm').reset();
}

// Export Positions
function exportPositions() {
    // TODO: Implement CSV export
    notyf.info('Export feature coming soon');
}

// Modal Management
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

// Loading State
function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.toggle('active', show);
    }
}

// Market Status
function updateMarketStatus(connected) {
    const statusElement = document.getElementById('marketStatus');
    if (statusElement && !connected) {
        statusElement.classList.remove('open', 'closed');
        statusElement.querySelector('.status-text').textContent = 'Disconnected';
    }
}

// Utility Functions
function formatNumber(num) {
    if (num === undefined || num === null) return '0.00';
    return Math.abs(num).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function updateChartPeriod(period) {
    // TODO: Implement chart period filtering
    console.log('Update chart period:', period);
}

// Position Actions (placeholders)
window.rollPosition = function(symbol) {
    notyf.info(`Rolling ${symbol} - Feature coming soon`);
};

window.sellCall = function(symbol) {
    notyf.info(`Selling call for ${symbol} - Feature coming soon`);
};

// Auto-refresh
setInterval(() => {
    if (socket && socket.connected) {
        socket.emit('request_update');
    }
}, 30000); // Refresh every 30 seconds