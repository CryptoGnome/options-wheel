# Automated Wheel Strategy

Welcome to the Wheel Strategy automation project!
This script is designed to help you trade the classic ["wheel" options strategy](https://alpaca.markets/learn/options-wheel-strategy) with as little manual work as possible using the [Alpaca Trading API](https://docs.alpaca.markets/).

---

## Strategy Logic

Here's the basic idea:

1. **Sell cash-secured puts** on stocks you wouldn't mind owning.
2. If you **get assigned**, buy the stock.
3. Then **sell covered calls** on the stock you own.
4. Keep collecting premiums until the stock gets called away.
5. Repeat the cycle!

This code helps pick the right puts and calls to sell, tracks your positions, and automatically turns the wheel to the next step.

---

## How to Run the Code

1. **Clone the repository:**

   ```bash
   git clone https://github.com/alpacahq/options-wheel.git
   cd options-wheel
   ```

2. **Create a virtual environment using [`uv`](https://github.com/astral-sh/uv):**

   ```bash
   uv venv
   source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows
   ```

3. **Install the required packages:**

   ```bash
   uv pip install -e .
   ```

4. **Set up your credentials and configuration:**

   a. Create a `.env` file for API credentials:
   ```env
   ALPACA_API_KEY=your_public_key
   ALPACA_SECRET_KEY=your_private_key
   IS_PAPER=true  # Set to false if using a live account
   ```

   b. Configure your strategy in `config/strategy_config.json`:
   ```json
   {
     "balance_settings": {
       "allocation_percentage": 0.5,  // Use 50% of account balance
       "max_wheel_layers": 2          // Run up to 2 wheel cycles per symbol
     },
     "option_filters": {
       "delta_min": 0.15,
       "delta_max": 0.30,
       "yield_min": 0.04,
       "yield_max": 1.00,
       "expiration_min_days": 0,
       "expiration_max_days": 21,
       "open_interest_min": 100,
       "score_min": 0.05
     },
     "rolling_settings": {
       "enabled": false,              // Global rolling on/off
       "days_before_expiry": 1,       // When to consider rolling
       "min_premium_to_roll": 0.05,   // Minimum premium required
       "roll_delta_target": 0.25      // Target delta for new positions
     },
     "symbols": {
       "AAPL": {
         "enabled": true, 
         "contracts": 1,
         "rolling": {
           "enabled": false,           // Symbol-specific override
           "strategy": "forward"       // forward, down, or both
         }
       },
       "SPY": {"enabled": true, "contracts": 2}
     },
     "default_contracts": 1
   }
   ```
   
   Or use the interactive config manager:
   ```bash
   python scripts/config_manager.py
   ```

5. **Symbol Configuration:**

   Symbols are now configured in `config/strategy_config.json`. Each symbol can have:
   - `enabled`: Whether to trade this symbol
   - `contracts`: Number of contracts to trade per order
   
   The **wheel layers** concept allows multiple positions:
   - Layer 1: Initial put → shares → covered call
   - Layer 2: New put (while holding shares) for averaging down

6. **Trading Parameters:**

   All parameters are now in `config/strategy_config.json`:
   - **Balance Settings**: allocation percentage (% of account to use), wheel layers
   - **Option Filters**: delta range, DTE range, yield, open interest, minimum score
   - **Symbol Settings**: enabled/disabled, contracts per symbol
   
   **Key Features:**
   - **Dynamic Balance Allocation**: Uses actual account balance (non-marginable buying power)
   - **Wheel Layers**: Run multiple wheel cycles on same symbol for averaging down
   - **Per-Symbol Contracts**: Configure different contract sizes for each symbol
   - **Premium-Adjusted Cost Basis**: Tracks collected premiums to lower effective cost basis for better exits
   - **SQLite Database**: Tracks all trades, premiums, and positions
   - **Option Rolling**: Automatically roll short puts before expiration to manage risk and capture additional premium


7. **Run the strategy**

   Run the strategy (which assumes an empty or fully managed portfolio):
   
   ```bash
   run-strategy
   ```
   
   > **Tip:** On your first run, use `--fresh-start` to liquidate all existing positions and start clean.
   
   There are two types of logging:
   
   * **Strategy JSON logging** (`--strat-log`):
     Always saves detailed JSON files to disk for analyzing strategy performance.
   
   * **Runtime logging** (`--log-level` and `--log-to-file`):
     Controls console/file logs for monitoring the current run. Optional and configurable.
   
   **Flags:**
   
   * `--fresh-start` — Liquidate all positions before running (recommended first run).
   * `--strat-log` — Enable strategy JSON logging (always saved to disk).
   * `--log-level LEVEL` — Set runtime logging verbosity (default: INFO).
   * `--log-to-file` — Save runtime logs to file instead of console.
   
   Example:
   
   ```bash
   run-strategy --fresh-start --strat-log --log-level DEBUG --log-to-file
   ```
   
   For more info:
   
   ```bash
   run-strategy --help
   ```

8. **Monitor your positions and premiums:**

   Use the database viewer to track your strategy performance:
   
   ```bash
   # View overall summary
   python scripts/db_viewer.py --summary
   
   # View cost basis (shows premium-adjusted prices)
   python scripts/db_viewer.py --cost-basis
   
   # View all data for a specific symbol
   python scripts/db_viewer.py --symbol AAPL --all
   
   # View premium history for last 60 days
   python scripts/db_viewer.py --premiums --days 60
   ```

---

### What the Script Does

* **Position Management**: Checks current positions to identify assignments and sells covered calls
* **Balance Optimization**: Uses actual account balance (non-marginable buying power) with configurable allocation percentage
* **Smart Filtering**: Filters stocks based on available buying power (must afford 100 shares × number of allowed positions)
* **Premium Tracking**: Records all premiums in SQLite database for cost basis adjustments
* **Intelligent Scoring**: Ranks options by annualized return discounted by assignment probability
* **Multi-Position Support**: Allows multiple put positions per symbol for dollar-cost averaging
* **Cost Basis Adjustment**: Uses collected call premiums to lower effective cost basis for better exits
* **Automatic Rolling**: Rolls short puts before expiration based on configurable criteria (opt-in feature)

---

### Notes

* **Account state matters**: This strategy assumes full control of the account — all positions are expected to be managed by this script. For best results, start with a clean account (e.g. by using the `--fresh-start` flag).
* **Single Config File**: ALL strategy settings are in `config/strategy_config.json` (except API keys which stay in `.env` for security)
* **Wheel Layers**: Set `max_wheel_layers` to control how many wheel cycles can run simultaneously per symbol (enables averaging down while holding shares).
* **Per-Symbol Configuration**: Each symbol can have different contract sizes configured in the JSON.
* **Database tracking**: All trades and premiums are stored in a local SQLite database (`data/wheel_strategy.db`) for analysis and tax reporting.
* The **user agent** for API calls defaults to `OPTIONS-WHEEL` to help Alpaca track usage of runnable algos and improve user experience.  You can opt out by adjusting the `USER_AGENT` variable in `core/user_agent_mixin.py` — though we kindly hope you’ll keep it enabled to support ongoing improvements.  
* **Want to customize the strategy?** The `core/strategy.py` module is a great place to start exploring and modifying the logic.

---

## Automating the Wheel

Running the script once will only turn the wheel a single time. To keep it running as a long-term income strategy, you'll want to automate it to run several times per day. This can be done with a cron job on Mac or Linux.

### Setting Up a Cron Job (Mac / Linux)

1. **Find the full path to the `run-strategy` command** by running:

   ```bash
   which run-strategy
   ```

   This will output something like:

   ```bash
   /Users/yourname/.local/share/virtualenvs/options-wheel-abc123/bin/run-strategy
   ```

2. **Open your crontab** for editing:

   ```bash
   crontab -e
   ```

3. **Add the following lines to run the strategy at 10:00 AM, 1:00 PM, and 3:30 PM on weekdays:**

   ```cron
   0 10 * * 1-5 /full/path/to/run-strategy >> /path/to/logs/run_strategy_10am.log 2>&1
   0 13 * * 1-5 /full/path/to/run-strategy >> /path/to/logs/run_strategy_1pm.log 2>&1
   30 15 * * 1-5 /full/path/to/run-strategy >> /path/to/logs/run_strategy_330pm.log 2>&1
   ```

   Replace `/full/path/to/run-strategy` with the output from the `which run-strategy` command above. Also replace `/path/to/logs/` with the directory where you'd like to store log files (create it if needed).

---

## Test Results

To validate the code mechanics, the strategy was tested in an Alpaca paper account over the course of two weeks (May 14 – May 28, 2025). A full report and explanation of each decision point can be found in [`reports/options-wheel-strategy-test.pdf`](./reports/options-wheel-strategy-test.pdf). A high-level summary of the trading results is given below.

### Premiums Collected

| Underlying | Expiry     | Strike | Type | Date Sold  | Premium Collected |
| ---------- | ---------- | ------ | ---- | ---------- | ----------------- |
| PLTR       | 2025-05-23 | 124    | P    | 2025-05-14 | \$261.00          |
| NVDA       | 2025-05-30 | 127    | P    | 2025-05-14 | \$332.00          |
| MP         | 2025-05-23 | 20     | P    | 2025-05-14 | \$28.00           |
| AAL        | 2025-05-30 | 11     | P    | 2025-05-14 | \$20.00           |
| INTC       | 2025-05-30 | 20.50  | P    | 2025-05-14 | \$33.00           |
| CAT        | 2025-05-16 | 345    | P    | 2025-05-14 | \$140.00          |
| AAPL       | 2025-05-23 | 200    | P    | 2025-05-19 | \$110.00          |
| DLR        | 2025-05-30 | 165    | P    | 2025-05-20 | \$67.00           |
| AAPL       | 2025-05-30 | 202.50 | C    | 2025-05-27 | \$110.00          |
| MP         | 2025-05-30 | 20.50  | C    | 2025-05-27 | \$12.00           |
| PLTR       | 2025-05-30 | 132    | C    | 2025-05-27 | \$127.00          |

**Total Premiums Collected:** **\$1,240.00**

---

### Total PnL (Change in Account Liquidating Value)

| Metric                   | Value           |
| ------------------------ | --------------- |
| Starting Balance         | \$100,000.00    |
| Ending Balance           | \$100,951.89    |
| Net PnL                  | **+\$951.89** |

---

### Disclaimer

These results are based on historical, simulated trading in a paper account over a limited timeframe and **do not represent actual live trading performance**. They are provided solely to demonstrate the mechanics of the strategy and its ability to automate the Wheel process in a controlled environment. **Past performance is not indicative of future results.** Trading in live markets involves risk, and there is no guarantee that future performance will match these simulated results.

---

## Core Strategy Logic

The core logic is defined in `core/strategy.py`, with enhanced features in `core/database.py` for tracking.

* **Stock Filtering:**
  The strategy filters underlying stocks based on available buying power. It fetches the latest trade prices for each candidate symbol and retains only those where the cost to buy 100 shares (`price × 100`) is within your buying power limit. This keeps trades within capital constraints and can be extended to include custom filters like volatility or technical indicators.

* **Option Filtering:**
  Put options are filtered by absolute delta, which must lie between `DELTA_MIN` and `DELTA_MAX`, by open interest (`OPEN_INTEREST_MIN`) to ensure liquidity, and by yield (between `YIELD_MIN` and `YIELD_MAX`). For short calls, the strategy applies a minimum strike price filter (`min_strike`) to ensure the strike is above the underlying purchase price. This helps avoid immediate assignment and locks in profit if the call is assigned.

* **Option Scoring:**
  Options are scored to estimate their attractiveness based on annualized return, adjusted for assignment risk. The score formula is:

   `score = (1 - |Δ|) × (250 / (DTE + 5)) × (bid price / strike price)`

  Where:

  * $\Delta$ = option delta (a rough proxy for the probability of assignment)
  * DTE = days to expiration
  * The factor 250 approximates the number of trading days in a year
  * Adding 5 days to DTE smooths the score for near-term options

* **Option Selection:**
  The strategy respects wheel layers per symbol, allowing you to sell new puts even while holding shares and covered calls. This enables averaging down when positions move against you.

* **Cost Basis Management:**
  The system tracks all premiums collected from covered calls and automatically adjusts your cost basis. For example:
  - Buy shares at $100 (assigned from put)
  - Sell covered call for $2 premium → Adjusted cost basis: $98
  - If call expires worthless, sell another for $1.50 → Adjusted cost basis: $96.50
  - System now targets call strikes ≥ $96.50 instead of $100 for better exit probability

---

## Ideas for Customization

### Stock Picking

* Use technical indicators such as moving averages, RSI, or support/resistance levels to identify stocks likely to remain range-bound — ideal for selling options in the Wheel strategy.
* Incorporate fundamental filters like earnings growth, dividend history, or volatility to select stocks you’re comfortable holding long term.

### Scoring Function for Puts / Calls

* Modify the scoring formula to weight factors differently or separately for puts vs calls. For example, emphasize calls with strikes just below resistance levels or puts on stocks with strong support.
* Consider adding factors like implied volatility or premium decay to better capture option pricing nuances.

### Managing a Larger Portfolio

* **Dynamic Position Sizing**: Already implemented via `MAX_POSITIONS_PER_SYMBOL`
* **Balance Allocation**: Use `BALANCE_ALLOCATION` to control what percentage of your account to deploy
* **Database Analytics**: Query the SQLite database for position analysis and performance metrics
* **Sector Limits**: Can be added by extending the filtering logic in `core/strategy.py`

### Stop Loss When Puts Get Assigned

* Implement logic to cut losses if a stock price falls sharply after assignment, protecting capital from downside.

### Rolling Short Puts as Expiration Nears (Now Implemented!)

* **Automatic Rolling**: The strategy now supports automatic rolling of short puts before expiration
* **Flexible Configuration**: Enable rolling globally or per-symbol with customizable parameters:
  - `days_before_expiry`: When to consider rolling (default: 1 day)
  - `min_premium_to_roll`: Minimum premium required to execute a roll
  - `roll_delta_target`: Target delta for new positions
* **Rolling Strategies**:
  - **Forward**: Roll to same or higher strike with later expiration
  - **Down**: Roll to lower strike to improve assignment probability
  - **Both**: Choose best available option based on scoring
* **Symbol-Specific Control**: Each symbol can have its own rolling settings and strategy
* **Full Tracking**: All rolls are logged in the database and strategy logs for analysis

To enable rolling:
1. Run `python scripts/config_manager.py`
2. Select option 6 to configure rolling settings
3. Enable globally or per-symbol as desired
4. The system will automatically roll eligible positions on each run

(For more on rolling strategies, see [this Learn article](https://alpaca.markets/learn/options-wheel-strategy).)

---

## Final Notes

This is a great starting point for automating your trading, but always double-check your live trades — no system is completely hands-off.

Happy wheeling! 🚀

---
<div style="font-size: 0.8em;">
Disclosures

Options trading is not suitable for all investors due to its inherent high risk, which can potentially result in significant losses. Please read [Characteristics and Risks of Standardized Options](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document) before investing in options

The Paper Trading API is offered by AlpacaDB, Inc. and does not require real money or permit a user to transact in real securities in the market. Providing use of the Paper Trading API is not an offer or solicitation to buy or sell securities, securities derivative or futures products of any kind, or any type of trading or investment advice, recommendation or strategy, given or in any manner endorsed by AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate and the information made available through the Paper Trading API is not an offer or solicitation of any kind in any jurisdiction where AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate (collectively, “Alpaca”) is not authorized to do business.

All investments involve risk, and the past performance of a security, or financial product does not guarantee future results or returns. There is no guarantee that any investment strategy will achieve its objectives. Please note that diversification does not ensure a profit, or protect against loss. There is always the potential of losing money when you invest in securities, or other financial products. Investors should consider their investment objectives and risks carefully before investing.

Please note that this article is for general informational purposes only and is believed to be accurate as of the posting date but may be subject to change. The examples above are for illustrative purposes only and should not be considered investment advice. 

Securities brokerage services are provided by Alpaca Securities LLC ("Alpaca Securities"), member [FINRA](https://www.finra.org/)/[SIPC](https://www.sipc.org/), a wholly-owned subsidiary of AlpacaDB, Inc. Technology and services are offered by AlpacaDB, Inc.

This is not an offer, solicitation of an offer, or advice to buy or sell securities or open a brokerage account in any jurisdiction where Alpaca Securities is not registered or licensed, as applicable.
</div>
