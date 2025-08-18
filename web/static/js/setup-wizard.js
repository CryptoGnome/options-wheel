// Setup Wizard JavaScript
// Handles first-time setup flow and configuration

class SetupWizard {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 4;
        this.setupData = {
            apiKey: '',
            secretKey: '',
            isPaper: true,
            allocation: 30,
            wheelLayers: 2,
            deltaMin: 0.15,
            deltaMax: 0.30,
            dteMin: 0,
            dteMax: 21,
            symbols: {}
        };
        
        this.init();
    }
    
    init() {
        // Check if setup is needed
        this.checkSetupStatus();
        
        // Initialize event listeners
        this.initEventListeners();
        
        // Initialize slider sync
        this.initSliders();
    }
    
    async checkSetupStatus() {
        try {
            const response = await fetch('/api/setup/status');
            const data = await response.json();
            
            if (data.needsSetup) {
                this.show();
            }
        } catch (error) {
            console.log('Checking setup status...', error);
            // If API doesn't exist yet, assume setup is needed
            const hasConfig = localStorage.getItem('wheelforge_configured');
            if (!hasConfig) {
                this.show();
            }
        }
    }
    
    show() {
        document.getElementById('setupWizard').classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    
    hide() {
        document.getElementById('setupWizard').classList.remove('active');
        document.body.style.overflow = '';
    }
    
    initEventListeners() {
        // Navigation buttons
        document.getElementById('setupNext').addEventListener('click', () => this.nextStep());
        document.getElementById('setupBack').addEventListener('click', () => this.previousStep());
        document.getElementById('setupComplete').addEventListener('click', () => this.completeSetup());
        
        // Symbol chips
        document.querySelectorAll('.symbol-chip').forEach(chip => {
            chip.addEventListener('click', (e) => this.toggleSymbol(e.currentTarget));
        });
        
        // Custom symbol add
        document.getElementById('addCustomSymbol').addEventListener('click', () => this.addCustomSymbol());
        document.getElementById('setupCustomSymbol').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addCustomSymbol();
        });
    }
    
    initSliders() {
        const slider = document.getElementById('setupAllocationSlider');
        const input = document.getElementById('setupAllocation');
        
        if (slider && input) {
            slider.addEventListener('input', (e) => {
                input.value = e.target.value;
                this.setupData.allocation = parseInt(e.target.value);
            });
            
            input.addEventListener('input', (e) => {
                slider.value = e.target.value;
                this.setupData.allocation = parseInt(e.target.value);
            });
        }
    }
    
    nextStep() {
        if (!this.validateCurrentStep()) {
            return;
        }
        
        if (this.currentStep < this.totalSteps) {
            this.saveStepData();
            this.currentStep++;
            this.updateUI();
        }
    }
    
    previousStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.updateUI();
        }
    }
    
    validateCurrentStep() {
        switch (this.currentStep) {
            case 1:
                // Validate API keys
                const apiKey = document.getElementById('setupApiKey').value;
                const secretKey = document.getElementById('setupSecretKey').value;
                
                if (!apiKey || !secretKey) {
                    this.showError('Please enter both API key and secret key');
                    return false;
                }
                
                if (!apiKey.startsWith('PK') && !apiKey.startsWith('AK')) {
                    this.showError('API key should start with PK or AK');
                    return false;
                }
                
                return true;
                
            case 2:
                // Risk settings are always valid (have defaults)
                return true;
                
            case 3:
                // Check if at least one symbol is selected
                if (Object.keys(this.setupData.symbols).length === 0) {
                    this.showError('Please select at least one symbol to trade');
                    return false;
                }
                return true;
                
            case 4:
                // Review step is always valid
                return true;
                
            default:
                return true;
        }
    }
    
    saveStepData() {
        switch (this.currentStep) {
            case 1:
                this.setupData.apiKey = document.getElementById('setupApiKey').value;
                this.setupData.secretKey = document.getElementById('setupSecretKey').value;
                this.setupData.isPaper = document.querySelector('input[name="tradingMode"]:checked').value === 'true';
                break;
                
            case 2:
                this.setupData.allocation = parseInt(document.getElementById('setupAllocation').value);
                this.setupData.wheelLayers = parseInt(document.getElementById('setupWheelLayers').value);
                this.setupData.deltaMin = parseFloat(document.getElementById('setupDeltaMin').value);
                this.setupData.deltaMax = parseFloat(document.getElementById('setupDeltaMax').value);
                this.setupData.dteMin = parseInt(document.getElementById('setupDTEMin').value);
                this.setupData.dteMax = parseInt(document.getElementById('setupDTEMax').value);
                break;
                
            case 3:
                // Symbols are saved as they're selected
                break;
        }
    }
    
    updateUI() {
        // Update progress bar
        const progress = (this.currentStep / this.totalSteps) * 100;
        document.getElementById('setupProgress').style.width = progress + '%';
        
        // Update step indicators
        document.querySelectorAll('.step').forEach((step, index) => {
            if (index < this.currentStep) {
                step.classList.add('active');
            } else {
                step.classList.remove('active');
            }
        });
        
        // Show/hide steps
        document.querySelectorAll('.setup-step').forEach((step, index) => {
            if (index === this.currentStep - 1) {
                step.classList.add('active');
            } else {
                step.classList.remove('active');
            }
        });
        
        // Update buttons
        const backBtn = document.getElementById('setupBack');
        const nextBtn = document.getElementById('setupNext');
        const completeBtn = document.getElementById('setupComplete');
        
        backBtn.style.display = this.currentStep > 1 ? 'flex' : 'none';
        
        if (this.currentStep === this.totalSteps) {
            nextBtn.style.display = 'none';
            completeBtn.style.display = 'flex';
            this.updateReviewStep();
        } else {
            nextBtn.style.display = 'flex';
            completeBtn.style.display = 'none';
        }
    }
    
    updateReviewStep() {
        // Update review display
        document.getElementById('reviewApiKey').textContent = 
            this.setupData.apiKey.substring(0, 6) + '...' + this.setupData.apiKey.slice(-4);
        document.getElementById('reviewMode').textContent = 
            this.setupData.isPaper ? 'Paper Trading' : 'Live Trading';
        document.getElementById('reviewAllocation').textContent = 
            this.setupData.allocation + '%';
        document.getElementById('reviewLayers').textContent = 
            this.setupData.wheelLayers;
        document.getElementById('reviewDelta').textContent = 
            `${this.setupData.deltaMin} - ${this.setupData.deltaMax}`;
        document.getElementById('reviewDTE').textContent = 
            `${this.setupData.dteMin} - ${this.setupData.dteMax} days`;
        
        // Update symbols list
        const symbolsContainer = document.getElementById('reviewSymbols');
        symbolsContainer.innerHTML = '';
        
        Object.entries(this.setupData.symbols).forEach(([symbol, data]) => {
            const div = document.createElement('div');
            div.className = 'review-symbol';
            div.textContent = `${symbol} (${data.contracts} contract${data.contracts > 1 ? 's' : ''})`;
            symbolsContainer.appendChild(div);
        });
    }
    
    toggleSymbol(chip) {
        const symbol = chip.dataset.symbol;
        const contracts = parseInt(chip.dataset.contracts);
        
        if (chip.classList.contains('selected')) {
            chip.classList.remove('selected');
            delete this.setupData.symbols[symbol];
        } else {
            chip.classList.add('selected');
            this.setupData.symbols[symbol] = {
                enabled: true,
                contracts: contracts
            };
        }
        
        this.updateSelectedSymbolsList();
    }
    
    addCustomSymbol() {
        const symbolInput = document.getElementById('setupCustomSymbol');
        const contractsInput = document.getElementById('setupCustomContracts');
        
        const symbol = symbolInput.value.toUpperCase().trim();
        const contracts = parseInt(contractsInput.value) || 1;
        
        if (!symbol) {
            this.showError('Please enter a symbol');
            return;
        }
        
        if (this.setupData.symbols[symbol]) {
            this.showError('Symbol already added');
            return;
        }
        
        this.setupData.symbols[symbol] = {
            enabled: true,
            contracts: contracts
        };
        
        // Clear inputs
        symbolInput.value = '';
        contractsInput.value = '1';
        
        this.updateSelectedSymbolsList();
        
        // Show success
        if (window.notyf) {
            window.notyf.success(`Added ${symbol} with ${contracts} contract${contracts > 1 ? 's' : ''}`);
        }
    }
    
    updateSelectedSymbolsList() {
        const container = document.getElementById('selectedSymbolsList');
        
        if (Object.keys(this.setupData.symbols).length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="ri-stock-line"></i>
                    <p>No symbols selected yet</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = '';
        Object.entries(this.setupData.symbols).forEach(([symbol, data]) => {
            const div = document.createElement('div');
            div.className = 'symbol-item';
            div.innerHTML = `
                <span>${symbol} (${data.contracts})</span>
                <button onclick="setupWizard.removeSymbol('${symbol}')">
                    <i class="ri-close-line"></i>
                </button>
            `;
            container.appendChild(div);
        });
    }
    
    removeSymbol(symbol) {
        delete this.setupData.symbols[symbol];
        
        // Unselect chip if exists
        const chip = document.querySelector(`.symbol-chip[data-symbol="${symbol}"]`);
        if (chip) {
            chip.classList.remove('selected');
        }
        
        this.updateSelectedSymbolsList();
    }
    
    async completeSetup() {
        // Save final step data
        this.saveStepData();
        
        // Show loading
        const completeBtn = document.getElementById('setupComplete');
        const originalContent = completeBtn.innerHTML;
        completeBtn.innerHTML = '<i class="ri-loader-4-line"></i> Setting up...';
        completeBtn.disabled = true;
        
        try {
            // Create configuration object
            const config = {
                // API Credentials (.env file)
                credentials: {
                    api_key: this.setupData.apiKey,
                    secret_key: this.setupData.secretKey,
                    is_paper: this.setupData.isPaper
                },
                
                // Strategy Configuration (strategy_config.json)
                strategy: {
                    balance_settings: {
                        allocation_percentage: this.setupData.allocation / 100,
                        max_wheel_layers: this.setupData.wheelLayers
                    },
                    option_filters: {
                        delta_min: this.setupData.deltaMin,
                        delta_max: this.setupData.deltaMax,
                        yield_min: 0.04,
                        yield_max: 1.00,
                        expiration_min_days: this.setupData.dteMin,
                        expiration_max_days: this.setupData.dteMax,
                        open_interest_min: 100,
                        score_min: 0.05
                    },
                    rolling_settings: {
                        enabled: false,
                        days_before_expiry: 1,
                        min_premium_to_roll: 0.05,
                        roll_delta_target: 0.25
                    },
                    symbols: this.setupData.symbols,
                    default_contracts: 1
                }
            };
            
            // Send to backend
            const response = await fetch('/api/setup/complete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
            
            if (response.ok) {
                // Mark setup as complete
                localStorage.setItem('wheelforge_configured', 'true');
                
                // Show success message
                if (window.notyf) {
                    window.notyf.success('Setup complete! Welcome to WheelForge!');
                }
                
                // Hide wizard and reload page
                setTimeout(() => {
                    this.hide();
                    window.location.reload();
                }, 1500);
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Setup failed');
            }
        } catch (error) {
            console.error('Setup error:', error);
            this.showError('Setup failed: ' + error.message);
            
            // Restore button
            completeBtn.innerHTML = originalContent;
            completeBtn.disabled = false;
        }
    }
    
    showError(message) {
        if (window.notyf) {
            window.notyf.error(message);
        } else {
            alert(message);
        }
    }
}

// Initialize setup wizard when DOM is ready
let setupWizard;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setupWizard = new SetupWizard();
    });
} else {
    setupWizard = new SetupWizard();
}

// Export for global access
window.setupWizard = setupWizard;