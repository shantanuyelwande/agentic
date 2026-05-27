---
name: financial-market-advisor
description: Daily financial news analysis and stock portfolio recommendations
---

# Financial Market Advisor Skill

Performs comprehensive daily market analysis and provides actionable stock recommendations.

## What It Does

1. **Gathers News**: Searches global financial news from previous day
   - Major economic events
   - Geopolitical developments
   - Oil/commodity price changes
   - Corporate earnings reports
   - Fed decisions and interest rate impacts

2. **Analyzes Market Impact**: Evaluates how events affect stock market
   - Macro drivers (yields, oil, inflation)
   - Sector tailwinds/headwinds
   - Momentum indicators

3. **Evaluates Portfolio**: Assesses each stock for buy/hold/sell signals
   - Portfolio: META, AAPL, AMZN, GOOGL, MSFT, NVDA, VOO
   - Individual catalysts
   - Risk/reward ratios

4. **Provides Recommendations**: 
   - Buy/Hold/Sell ratings with targets
   - New investment opportunities in high-growth areas
   - Risk factors to monitor

5. **Sends Report**: Email formatted report to shantanu.y@gmail.com

## Usage

```bash
# Run the financial advisor (manual)
claude "Daily market analysis: gather news and analyze my portfolio (META, AAPL, AMZN, GOOGL, MSFT, NVDA, VOO). Provide buy/hold/sell recommendations."

# Or schedule daily at 9 AM
/loop 1d "Daily market analysis..." --run-at 9:00
```

## Key Features

- **Token Efficient**: Uses Tavily search for fresh news (doesn't load stale data)
- **Portfolio Focused**: Analyzes YOUR specific stocks
- **Actionable**: Concrete buy/hold/sell + price targets
- **Risk-Aware**: Flags macro risks and valuation concerns
- **Opportunity Hunting**: Identifies new investment prospects

## Data Sources

- Tavily API for latest financial news
- Public market data
- Economic calendars
- Earnings reports

## Output

- Formatted analysis with sections:
  - Market sentiment
  - Portfolio recommendations (NVDA, MSFT, GOOGL, AMZN, AAPL, META, VOO)
  - New opportunities
  - Risk factors
  - Action summary

## Implementation Notes

- Designed to run at 9 AM before market open (9:30 AM ET)
- Searches for previous day's news (May 26 → May 27)
- Respects current date context
- Requires internet for Tavily API calls
- Gmail integration for email delivery (OAuth required)
