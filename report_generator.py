"""Report generation module using Claude API or template-based fallback."""

import json
from datetime import datetime
from typing import Any

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


class ReportGenerator:
    """Generates narrative Bitcoin market reports using Claude or templates."""

    def __init__(self, use_ai: bool = True):
        """
        Initialize the report generator.

        Args:
            use_ai: If True, use Claude API. If False, use template-based generation.
        """
        self.use_ai = use_ai and bool(ANTHROPIC_API_KEY)
        self.client = None

        if self.use_ai:
            import anthropic
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def _format_number(self, num: float | None, decimals: int = 2) -> str:
        """Format large numbers with appropriate suffixes."""
        if num is None:
            return "N/A"

        if abs(num) >= 1_000_000_000_000:
            return f"${num / 1_000_000_000_000:.{decimals}f}T"
        elif abs(num) >= 1_000_000_000:
            return f"${num / 1_000_000_000:.{decimals}f}B"
        elif abs(num) >= 1_000_000:
            return f"${num / 1_000_000:.{decimals}f}M"
        elif abs(num) >= 1_000:
            return f"${num / 1_000:.{decimals}f}K"
        else:
            return f"${num:.{decimals}f}"

    def _build_data_summary(self, data: dict[str, Any]) -> str:
        """Build a structured summary of the market data for Claude."""
        bitcoin = data.get("bitcoin", {})
        fear_greed = data.get("fear_greed", {})
        blockchain = data.get("blockchain", {})
        history_30d = data.get("price_history_30d", {})
        history_7d = data.get("price_history_7d", {})

        summary = f"""
## Current Bitcoin Market Data

### Price & Market Metrics
- Current Price: ${bitcoin.get('price_usd', 'N/A'):,.2f}
- 24h Change: {bitcoin.get('price_change_24h_percent', 'N/A'):.2f}%
- 7d Change: {bitcoin.get('price_change_7d_percent', 'N/A'):.2f}%
- 30d Change: {bitcoin.get('price_change_30d_percent', 'N/A'):.2f}%
- Market Cap: {self._format_number(bitcoin.get('market_cap_usd'))}
- 24h Volume: {self._format_number(bitcoin.get('volume_24h_usd'))}
- All-Time High: ${bitcoin.get('ath_usd', 'N/A'):,.2f} ({bitcoin.get('ath_change_percent', 'N/A'):.1f}% from ATH)

### 30-Day Price Range
- High: ${history_30d.get('price_high', 'N/A'):,.2f}
- Low: ${history_30d.get('price_low', 'N/A'):,.2f}
- Period Start: ${history_30d.get('price_start', 'N/A'):,.2f}
- Period End: ${history_30d.get('price_end', 'N/A'):,.2f}
- Average Daily Volume: {self._format_number(history_30d.get('avg_volume'))}

### 7-Day Price Range
- High: ${history_7d.get('price_high', 'N/A'):,.2f}
- Low: ${history_7d.get('price_low', 'N/A'):,.2f}

### Market Sentiment
- Fear & Greed Index: {fear_greed.get('value', 'N/A')} ({fear_greed.get('classification', 'N/A')})
- 7-Day Sentiment History: {json.dumps(fear_greed.get('history', []), indent=2)}

### On-Chain Metrics
- Current Hash Rate: {blockchain.get('hash_rate_current', 'N/A'):,.0f} TH/s
- 30-Day Avg Hash Rate: {blockchain.get('hash_rate_30d_avg', 'N/A'):,.0f} TH/s
- Daily Transactions: {blockchain.get('tx_count_current', 'N/A'):,.0f}
- 30-Day Avg Transactions: {blockchain.get('tx_count_30d_avg', 'N/A'):,.0f}
- Network Difficulty: {blockchain.get('difficulty_current', 'N/A'):,.0f}
- 30-Day Difficulty Change: {blockchain.get('difficulty_30d_change', 'N/A'):.2f}%

### Supply Metrics
- Circulating Supply: {bitcoin.get('circulating_supply', 'N/A'):,.0f} BTC
- Total Supply: {bitcoin.get('total_supply', 'N/A'):,.0f} BTC
"""
        return summary

    def _build_prompt(self, data: dict[str, Any], report_type: str = "daily") -> str:
        """Build the prompt for Claude to generate the report."""
        data_summary = self._build_data_summary(data)

        time_context = {
            "daily": "today's",
            "weekly": "this week's",
        }.get(report_type, "the current")

        prompt = f"""You are a professional cryptocurrency market analyst writing a Bitcoin market report.
Analyze the following market data and write a comprehensive yet digestible narrative report.

{data_summary}

Write a market report covering:

1. **Price Action**: Summarize {time_context} price movements, noting significant changes and where BTC stands relative to recent ranges and ATH.

2. **Volume & Liquidity**: Analyze trading volume - is it above or below average? What does this suggest about market participation?

3. **Market Sentiment**: Interpret the Fear & Greed Index reading and its recent trajectory. What does sentiment suggest about near-term direction?

4. **On-Chain Health**: Analyze hash rate, transaction count, and difficulty. Is the network healthy? Any notable trends?

5. **Key Observations**: Highlight any anomalies, divergences, or particularly noteworthy signals in the data.

6. **Outlook**: Based on the data patterns, provide a brief, balanced perspective on what to watch for.

Guidelines:
- Write in a professional but accessible tone
- Use specific numbers from the data to support observations
- Avoid sensationalism - be balanced and factual
- Keep each section focused and concise
- Format as clean Markdown
- Do not include disclaimers about not being financial advice - this is understood

Output the report in Markdown format, starting with the sections above (no title needed, it will be added separately).
"""
        return prompt

    def _generate_template_report(self, data: dict[str, Any], report_type: str = "daily") -> str:
        """Generate a report using templates (no AI required)."""
        bitcoin = data.get("bitcoin", {})
        fear_greed = data.get("fear_greed", {})
        blockchain = data.get("blockchain", {})
        history_30d = data.get("price_history_30d", {})
        history_7d = data.get("price_history_7d", {})

        # Determine price trend
        change_24h = bitcoin.get('price_change_24h_percent', 0) or 0
        change_7d = bitcoin.get('price_change_7d_percent', 0) or 0
        change_30d = bitcoin.get('price_change_30d_percent', 0) or 0

        if change_24h > 3:
            price_action = "significant upward momentum"
        elif change_24h > 0:
            price_action = "modest gains"
        elif change_24h > -3:
            price_action = "slight decline"
        else:
            price_action = "notable selling pressure"

        # Volume analysis
        current_vol = bitcoin.get('volume_24h_usd', 0) or 0
        avg_vol = history_30d.get('avg_volume', 0) or 1
        vol_ratio = current_vol / avg_vol if avg_vol else 1

        if vol_ratio > 1.5:
            volume_analysis = "significantly elevated, indicating strong market participation"
        elif vol_ratio > 1.1:
            volume_analysis = "above average, suggesting healthy trading activity"
        elif vol_ratio > 0.9:
            volume_analysis = "near average levels"
        else:
            volume_analysis = "below average, indicating reduced market activity"

        # Sentiment interpretation
        fg_value = fear_greed.get('value', 50) or 50
        fg_class = fear_greed.get('classification', 'Neutral')

        if fg_value >= 75:
            sentiment_outlook = "Extreme greed levels historically suggest caution as markets may be overextended."
        elif fg_value >= 55:
            sentiment_outlook = "Greed territory indicates bullish sentiment, though not at extreme levels."
        elif fg_value >= 45:
            sentiment_outlook = "Neutral sentiment suggests market indecision and potential consolidation."
        elif fg_value >= 25:
            sentiment_outlook = "Fear levels may present accumulation opportunities for long-term holders."
        else:
            sentiment_outlook = "Extreme fear historically correlates with market bottoms and potential buying opportunities."

        # On-chain health
        hr_current = blockchain.get('hash_rate_current', 0) or 0
        hr_avg = blockchain.get('hash_rate_30d_avg', 0) or 1
        hr_trend = "stable" if abs(hr_current - hr_avg) / hr_avg < 0.05 else ("increasing" if hr_current > hr_avg else "decreasing")

        tx_current = blockchain.get('tx_count_current', 0) or 0
        tx_avg = blockchain.get('tx_count_30d_avg', 0) or 1
        tx_trend = "healthy" if tx_current >= tx_avg * 0.95 else "slightly reduced"

        # Price range context
        price = bitcoin.get('price_usd', 0) or 0
        high_30d = history_30d.get('price_high', price) or price
        low_30d = history_30d.get('price_low', price) or price
        range_position = (price - low_30d) / (high_30d - low_30d) * 100 if high_30d != low_30d else 50

        if range_position > 80:
            range_context = "near the top of its 30-day range"
        elif range_position > 60:
            range_context = "in the upper portion of its 30-day range"
        elif range_position > 40:
            range_context = "near the middle of its 30-day range"
        elif range_position > 20:
            range_context = "in the lower portion of its 30-day range"
        else:
            range_context = "near the bottom of its 30-day range"

        report_content = f"""## Price Action

Bitcoin is currently trading at **${price:,.2f}**, showing {price_action} with a **{change_24h:+.2f}%** change over the past 24 hours. Over the past week, BTC has moved **{change_7d:+.2f}%**, while the 30-day performance stands at **{change_30d:+.2f}%**.

The price is currently {range_context}, with the 30-day high at ${high_30d:,.2f} and the low at ${low_30d:,.2f}. Bitcoin remains **{abs(bitcoin.get('ath_change_percent', 0) or 0):.1f}%** below its all-time high of ${bitcoin.get('ath_usd', 0):,.2f}.

## Volume & Liquidity

Trading volume over the past 24 hours reached **{self._format_number(current_vol)}**, which is {volume_analysis}. The 30-day average daily volume is {self._format_number(avg_vol)}.

Market capitalization stands at **{self._format_number(bitcoin.get('market_cap_usd'))}**, reflecting Bitcoin's position as the dominant cryptocurrency asset.

## Market Sentiment

The Fear & Greed Index currently reads **{fg_value}** ({fg_class}). {sentiment_outlook}

Looking at the 7-day sentiment trend:
{self._format_sentiment_history(fear_greed.get('history', []))}

## On-Chain Health

Network fundamentals remain robust:

- **Hash Rate**: {hr_current:,.0f} TH/s (30-day avg: {hr_avg:,.0f} TH/s) - {hr_trend}
- **Daily Transactions**: {tx_current:,.0f} (30-day avg: {tx_avg:,.0f}) - {tx_trend}
- **Network Difficulty**: {blockchain.get('difficulty_current', 0):,.0f}
- **Difficulty Change (30d)**: {blockchain.get('difficulty_30d_change', 0):+.2f}%

The network hash rate trend is {hr_trend}, indicating {"strong miner confidence" if hr_trend == "increasing" else "consistent mining activity" if hr_trend == "stable" else "some miner capitulation"}.

## Key Observations

{"- **High Volume Alert**: Trading volume is significantly above average, suggesting strong market interest." if vol_ratio > 1.5 else ""}
{"- **Extreme Sentiment**: Fear & Greed at extreme levels often precedes trend reversals." if fg_value < 25 or fg_value > 75 else ""}
{"- **Price Near Range Boundary**: BTC is testing the edges of its recent trading range." if range_position < 10 or range_position > 90 else ""}
- **Supply Dynamics**: {bitcoin.get('circulating_supply', 0):,.0f} BTC in circulation out of {bitcoin.get('total_supply', 0):,.0f} total supply.

## Outlook

Based on current data patterns:
- {"Bullish momentum may continue if volume sustains" if change_24h > 2 and vol_ratio > 1 else "Watch for potential reversal signals" if change_24h < -3 else "Consolidation likely until a clear catalyst emerges"}
- Sentiment at {fg_value} suggests {"caution for new long positions" if fg_value > 70 else "potential accumulation zone" if fg_value < 30 else "balanced market conditions"}
- Network health metrics {"support the current price action" if hr_trend in ["stable", "increasing"] else "warrant monitoring"}

*Key levels to watch: ${low_30d:,.0f} (support) | ${high_30d:,.0f} (resistance)*"""

        return report_content

    def _format_sentiment_history(self, history: list) -> str:
        """Format sentiment history as a markdown list."""
        if not history:
            return "- No historical data available"
        lines = []
        for entry in history[:5]:
            lines.append(f"- {entry.get('date', 'N/A')}: {entry.get('value', 'N/A')} ({entry.get('classification', 'N/A')})")
        return "\n".join(lines)

    def generate_report(
        self, data: dict[str, Any], report_type: str = "daily"
    ) -> str:
        """Generate a narrative report using Claude or templates."""
        if self.use_ai and self.client:
            print(f"Generating {report_type} report with Claude...")
            prompt = self._build_prompt(data, report_type)

            message = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            report_content = message.content[0].text
        else:
            print(f"Generating {report_type} report using templates...")
            report_content = self._generate_template_report(data, report_type)

        # Add title and metadata
        today = datetime.now().strftime("%B %d, %Y")
        title_suffix = " - Weekly Summary" if report_type == "weekly" else ""
        generation_method = "Claude AI" if self.use_ai else "Template Engine"

        full_report = f"""# Bitcoin Market Report - {today}{title_suffix}

> Generated at {datetime.now().strftime("%H:%M UTC")} | Data sources: CoinGecko, Alternative.me, Blockchain.com

---

{report_content}

---

*Report generated by Bitcoin Market Narrative Generator ({generation_method})*
"""
        return full_report

    def convert_to_html(self, markdown_content: str, data: dict[str, Any] = None) -> str:
        """Convert Markdown report to styled HTML."""
        bitcoin = data.get("bitcoin", {}) if data else {}
        fear_greed = data.get("fear_greed", {}) if data else {}
        blockchain = data.get("blockchain", {}) if data else {}
        history_30d = data.get("price_history_30d", {}) if data else {}
        block_stats = data.get("block_stats", {}) if data else {}
        network_stats = data.get("network_stats", {}) if data else {}
        address_stats = data.get("address_stats", {}) if data else {}
        supply_stats = data.get("supply_stats", {}) if data else {}
        historical_prices = data.get("historical_on_this_day", []) if data else []
        onchain = data.get("onchain_analytics", {}) if data else {}
        market = data.get("market_data", {}) if data else {}

        price = bitcoin.get('price_usd', 0) or 0
        change_24h = bitcoin.get('price_change_24h_percent', 0) or 0
        change_7d = bitcoin.get('price_change_7d_percent', 0) or 0
        change_30d = bitcoin.get('price_change_30d_percent', 0) or 0
        market_cap = bitcoin.get('market_cap_usd', 0) or 0
        volume = bitcoin.get('volume_24h_usd', 0) or 0
        fg_value = fear_greed.get('value', 50) or 50
        fg_class = fear_greed.get('classification', 'Neutral')
        hash_rate = blockchain.get('hash_rate_current', 0) or 0
        tx_count = blockchain.get('tx_count_current', 0) or 0
        high_30d = history_30d.get('price_high', 0) or 0
        low_30d = history_30d.get('price_low', 0) or 0

        # Block stats (with fallbacks from address_stats)
        block_height = block_stats.get('block_height') or address_stats.get('best_block_height', 0) or 0
        block_reward = block_stats.get('block_reward', 3.125) or 3.125
        blocks_until_halving = block_stats.get('blocks_until_halving', 0) or 0
        next_halving = block_stats.get('next_halving_estimate', 'TBD')
        fee_fastest = block_stats.get('fee_fastest', 0) or 0
        mempool_count = block_stats.get('mempool_tx_count') or address_stats.get('mempool_count_backup', 0) or 0

        # Recalculate halving info if we got block height from fallback
        if block_height and not blocks_until_halving:
            halvings = block_height // 210000
            block_reward = 50 / (2 ** halvings)
            next_halving_block = (halvings + 1) * 210000
            blocks_until_halving = next_halving_block - block_height
            from datetime import timedelta
            minutes_until = blocks_until_halving * 10
            next_halving = (datetime.now() + timedelta(minutes=minutes_until)).strftime("%Y-%m-%d")

        # Network stats
        minutes_between = network_stats.get('minutes_between_blocks', 10) or 10
        avg_tx_fee = network_stats.get('avg_tx_fee_usd_7d', 0) or 0

        # Supply stats
        circulating = supply_stats.get('circulating_supply', 0) or 0
        remaining = supply_stats.get('remaining_to_mine', 0) or 0
        sats_per_dollar = supply_stats.get('sats_per_dollar', 0) or 0
        block_reward_usd = block_reward * price if price else 0

        # Address stats
        utxo_count = address_stats.get('utxo_count', 0) or 0
        nodes = address_stats.get('nodes', 0) or 0

        # ATH info
        ath = bitcoin.get('ath_usd', 0) or 0
        ath_change = bitcoin.get('ath_change_percent', 0) or 0
        ath_date = bitcoin.get('ath_date', '')

        # On-chain analytics
        active_addresses = onchain.get('active_addresses_today', 0) or 0
        active_addresses_avg = onchain.get('active_addresses_7d_avg', 0) or 0
        new_addresses = onchain.get('new_addresses_today', 0) or 0
        tx_volume_usd = onchain.get('tx_volume_usd_today', 0) or 0
        whale_txs = onchain.get('whale_transactions_recent', 0) or 0

        # Market/Trading data
        btc_dominance = market.get('btc_dominance', 0) or 0
        total_crypto_mcap = market.get('total_crypto_market_cap', 0) or 0
        open_interest = market.get('open_interest_usd', 0) or 0
        oi_change = market.get('open_interest_24h_change', 0) or 0
        funding_rate = market.get('funding_rate_avg', 0) or 0
        liq_long = market.get('liquidations_24h_long', 0) or 0
        liq_short = market.get('liquidations_24h_short', 0) or 0
        liq_total = market.get('liquidations_24h_total', 0) or 0

        # Determine sentiment color
        if fg_value >= 75:
            fg_color = "#22c55e"
            fg_gradient = "linear-gradient(135deg, #22c55e, #16a34a)"
        elif fg_value >= 55:
            fg_color = "#84cc16"
            fg_gradient = "linear-gradient(135deg, #84cc16, #65a30d)"
        elif fg_value >= 45:
            fg_color = "#eab308"
            fg_gradient = "linear-gradient(135deg, #eab308, #ca8a04)"
        elif fg_value >= 25:
            fg_color = "#f97316"
            fg_gradient = "linear-gradient(135deg, #f97316, #ea580c)"
        else:
            fg_color = "#ef4444"
            fg_gradient = "linear-gradient(135deg, #ef4444, #dc2626)"

        change_color_24h = "#22c55e" if change_24h >= 0 else "#ef4444"
        change_color_7d = "#22c55e" if change_7d >= 0 else "#ef4444"
        change_color_30d = "#22c55e" if change_30d >= 0 else "#ef4444"

        # Format large numbers
        def fmt(n):
            if n >= 1e12: return f"${n/1e12:.2f}T"
            if n >= 1e9: return f"${n/1e9:.2f}B"
            if n >= 1e6: return f"${n/1e6:.2f}M"
            return f"${n:,.0f}"

        def fmt_btc(n):
            if n >= 1e6: return f"{n/1e6:.2f}M"
            if n >= 1e3: return f"{n/1e3:.2f}K"
            return f"{n:,.2f}"

        today = datetime.now().strftime("%B %d, %Y")
        today_short = datetime.now().strftime("%B %d")
        time_now = datetime.now().strftime("%H:%M UTC")

        # Generate historical prices HTML for new Cloudflare-style design
        historical_section = ""
        if historical_prices:
            items = ""
            for hp in historical_prices[:12]:
                items += f'<div class="history-item"><span class="history-year">{hp["year"]}</span><span class="history-price">${hp["price"]:,.0f}</span></div>'
            historical_section = f'''<div class="section-header mt-40">
                <h2 class="section-title">Bitcoin on {today_short}</h2>
                <p class="section-subtitle">Historical prices for this date</p>
            </div>
            <div class="history-grid mb-24">{items}</div>'''

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bitcoin Market Report - {today}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        :root {{
            --bg-dark: #0d1117;
            --bg-darker: #010409;
            --bg-card: #161b22;
            --bg-card-hover: #1c2128;
            --border-color: #30363d;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            --accent: #f6851b;
            --accent-light: #ff9f43;
            --green: #3fb950;
            --red: #f85149;
            --blue: #58a6ff;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-darker);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}

        /* Hero gradient background */
        .hero-bg {{
            background: linear-gradient(180deg, #0d1117 0%, #010409 100%);
            position: relative;
            overflow: hidden;
        }}

        .hero-bg::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 50%;
            transform: translateX(-50%);
            width: 150%;
            height: 600px;
            background: radial-gradient(ellipse at center top, rgba(246, 133, 27, 0.15) 0%, transparent 60%);
            pointer-events: none;
        }}

        .container {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
            position: relative;
        }}

        /* Navigation */
        .nav {{
            padding: 16px 0;
            border-bottom: 1px solid var(--border-color);
        }}

        .nav-content {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .logo {{
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }}

        .logo-icon {{
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--accent), var(--accent-light));
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}

        .logo-text {{
            font-weight: 700;
            font-size: 1.1rem;
            color: var(--text-primary);
        }}

        .nav-date {{
            color: var(--text-secondary);
            font-size: 0.875rem;
        }}

        /* Hero Section */
        .hero {{
            padding: 80px 0 60px;
            text-align: center;
        }}

        .hero-label {{
            display: inline-block;
            padding: 6px 12px;
            background: rgba(246, 133, 27, 0.1);
            border: 1px solid rgba(246, 133, 27, 0.3);
            border-radius: 20px;
            color: var(--accent);
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 24px;
        }}

        .hero-price {{
            font-size: 5rem;
            font-weight: 800;
            color: var(--text-primary);
            letter-spacing: -0.02em;
            margin-bottom: 16px;
        }}

        .hero-change {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: {"rgba(63, 185, 80, 0.1)" if change_24h >= 0 else "rgba(248, 81, 73, 0.1)"};
            border-radius: 8px;
            color: {change_color_24h};
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .hero-change svg {{
            width: 20px;
            height: 20px;
        }}

        /* Stats Row */
        .stats-row {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1px;
            background: var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            margin: 40px 0;
        }}

        .stat-item {{
            background: var(--bg-card);
            padding: 24px;
            text-align: center;
        }}

        .stat-item:hover {{
            background: var(--bg-card-hover);
        }}

        .stat-label {{
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
        }}

        .stat-value.green {{ color: var(--green); }}
        .stat-value.red {{ color: var(--red); }}

        /* Price Chart */
        .chart-container {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            margin: 24px 0 40px;
        }}

        .chart-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}

        .chart-title {{
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .chart-timeframes {{
            display: flex;
            gap: 8px;
        }}

        .timeframe-btn {{
            padding: 6px 12px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: transparent;
            color: var(--text-secondary);
            font-size: 0.75rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .timeframe-btn:hover {{
            border-color: var(--accent);
            color: var(--accent);
        }}

        .timeframe-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
            color: white;
        }}

        .chart-wrapper {{
            height: 300px;
            position: relative;
        }}

        .chart-stats {{
            display: flex;
            gap: 24px;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid var(--border-color);
        }}

        .chart-stat {{
            text-align: center;
        }}

        .chart-stat-label {{
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .chart-stat-value {{
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-top: 4px;
        }}

        /* Live indicator */
        .live-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.7rem;
            color: var(--green);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .live-dot {{
            width: 8px;
            height: 8px;
            background: var(--green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}

        /* Main Content */
        .main-content {{
            background: var(--bg-dark);
            padding: 60px 0;
        }}

        .grid-2 {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
        }}

        .grid-3 {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
        }}

        /* Cards */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            transition: border-color 0.2s ease;
        }}

        .card:hover {{
            border-color: var(--text-muted);
        }}

        .card-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
        }}

        .card-icon {{
            width: 40px;
            height: 40px;
            background: rgba(246, 133, 27, 0.1);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--accent);
            font-size: 18px;
        }}

        .card-title {{
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        /* Fear & Greed */
        .fg-container {{
            text-align: center;
            padding: 20px 0;
        }}

        .fg-value {{
            font-size: 4rem;
            font-weight: 800;
            color: {fg_color};
            line-height: 1;
        }}

        .fg-label {{
            font-size: 1.1rem;
            font-weight: 600;
            color: {fg_color};
            margin-top: 8px;
        }}

        .fg-bar {{
            height: 8px;
            background: linear-gradient(90deg, #f85149, #f97316, #eab308, #84cc16, #3fb950);
            border-radius: 4px;
            margin: 20px 0 8px;
            position: relative;
        }}

        .fg-indicator {{
            position: absolute;
            top: -4px;
            left: {fg_value}%;
            transform: translateX(-50%);
            width: 16px;
            height: 16px;
            background: white;
            border-radius: 50%;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}

        .fg-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 0.7rem;
            color: var(--text-muted);
        }}

        /* Data Rows */
        .data-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid var(--border-color);
        }}

        .data-row:last-child {{
            border-bottom: none;
        }}

        .data-label {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        .data-value {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        .data-value.accent {{
            color: var(--accent);
        }}

        /* Historical Grid */
        .history-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 8px;
        }}

        .history-item {{
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 16px 12px;
            background: var(--bg-darker);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        .history-year {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 4px;
        }}

        .history-price {{
            font-weight: 700;
            color: var(--accent);
            font-size: 0.95rem;
        }}

        /* Section Headers */
        .section-header {{
            margin-bottom: 24px;
        }}

        .section-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 8px;
        }}

        .section-subtitle {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}

        /* Mini Stats Grid */
        .mini-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
        }}

        .mini-stat {{
            background: var(--bg-darker);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}

        .mini-stat-label {{
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .mini-stat-value {{
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 4px;
        }}

        /* Footer */
        footer {{
            background: var(--bg-darker);
            border-top: 1px solid var(--border-color);
            padding: 40px 0;
            text-align: center;
        }}

        .footer-text {{
            color: var(--text-muted);
            font-size: 0.875rem;
        }}

        .footer-links {{
            margin-top: 12px;
            color: var(--text-secondary);
            font-size: 0.8rem;
        }}

        /* Spacing utilities */
        .mt-24 {{ margin-top: 24px; }}
        .mt-40 {{ margin-top: 40px; }}
        .mb-24 {{ margin-bottom: 24px; }}

        @media (max-width: 1024px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
            .grid-3 {{ grid-template-columns: 1fr; }}
        }}

        @media (max-width: 768px) {{
            .hero-price {{ font-size: 3rem; }}
            .stats-row {{ grid-template-columns: repeat(2, 1fr); }}
            .history-grid {{ grid-template-columns: repeat(3, 1fr); }}
        }}

        @media (max-width: 480px) {{
            .stats-row {{ grid-template-columns: 1fr; }}
            .history-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <!-- Hero Section -->
    <div class="hero-bg">
        <nav class="nav">
            <div class="container">
                <div class="nav-content">
                    <a href="#" class="logo">
                        <div class="logo-icon">&#8383;</div>
                        <span class="logo-text">Bitcoin Report</span>
                    </a>
                    <span class="nav-date">{today}</span>
                </div>
            </div>
        </nav>

        <div class="container">
            <section class="hero">
                <span class="hero-label">Live Market Data</span>
                <div class="hero-price">${price:,.0f}</div>
                <div class="hero-change">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        {"<path d='M18 15l-6-6-6 6'/>" if change_24h >= 0 else "<path d='M6 9l6 6 6-6'/>"}
                    </svg>
                    {change_24h:+.2f}% (24h)
                </div>
            </section>

            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">Market Cap</div>
                    <div class="stat-value">{fmt(market_cap)}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">24h Volume</div>
                    <div class="stat-value">{fmt(volume)}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">7d Change</div>
                    <div class="stat-value {"green" if change_7d >= 0 else "red"}">{change_7d:+.2f}%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">30d Change</div>
                    <div class="stat-value {"green" if change_30d >= 0 else "red"}">{change_30d:+.2f}%</div>
                </div>
            </div>

            <!-- Price Chart -->
            <div class="chart-container">
                <div class="chart-header">
                    <div style="display: flex; align-items: center; gap: 16px;">
                        <span class="chart-title">Price Chart</span>
                        <span class="live-indicator"><span class="live-dot"></span> Live</span>
                    </div>
                    <div class="chart-timeframes">
                        <button class="timeframe-btn" data-days="1">24H</button>
                        <button class="timeframe-btn active" data-days="7">7D</button>
                        <button class="timeframe-btn" data-days="30">30D</button>
                        <button class="timeframe-btn" data-days="90">90D</button>
                    </div>
                </div>
                <div class="chart-wrapper">
                    <canvas id="priceChart"></canvas>
                </div>
                <div class="chart-stats">
                    <div class="chart-stat">
                        <div class="chart-stat-label">Period High</div>
                        <div class="chart-stat-value" id="chart-high">--</div>
                    </div>
                    <div class="chart-stat">
                        <div class="chart-stat-label">Period Low</div>
                        <div class="chart-stat-value" id="chart-low">--</div>
                    </div>
                    <div class="chart-stat">
                        <div class="chart-stat-label">Period Change</div>
                        <div class="chart-stat-value" id="chart-change">--</div>
                    </div>
                    <div class="chart-stat">
                        <div class="chart-stat-label">Avg Price</div>
                        <div class="chart-stat-value" id="chart-avg">--</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <main class="main-content">
        <div class="container">
            <div class="grid-2 mb-24">
                <!-- Price Range Card -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128200;</div>
                        <span class="card-title">30-Day Price Range</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Current Price</span>
                        <span class="data-value accent">${price:,.2f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">30d High</span>
                        <span class="data-value">${high_30d:,.2f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">30d Low</span>
                        <span class="data-value">${low_30d:,.2f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">All-Time High</span>
                        <span class="data-value">${ath:,.0f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">From ATH</span>
                        <span class="data-value" style="color: var(--red)">{ath_change:.1f}%</span>
                    </div>
                </div>

                <!-- Fear & Greed Card -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128161;</div>
                        <span class="card-title">Market Sentiment</span>
                    </div>
                    <div class="fg-container">
                        <div class="fg-value">{fg_value}</div>
                        <div class="fg-label">{fg_class}</div>
                        <div class="fg-bar">
                            <div class="fg-indicator"></div>
                        </div>
                        <div class="fg-labels">
                            <span>Extreme Fear</span>
                            <span>Extreme Greed</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Historical Prices -->
            {historical_section}

            <!-- Block Stats -->
            <div class="section-header mt-40">
                <h2 class="section-title">Network Statistics</h2>
                <p class="section-subtitle">On-chain metrics and block data</p>
            </div>

            <div class="grid-3 mb-24">
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#9939;</div>
                        <span class="card-title">Block Info</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Block Height</span>
                        <span class="data-value">{block_height:,}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Block Reward</span>
                        <span class="data-value accent">{block_reward} BTC</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Reward Value</span>
                        <span class="data-value">${block_reward_usd:,.0f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Avg Block Time</span>
                        <span class="data-value">{minutes_between:.1f} min</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#9201;</div>
                        <span class="card-title">Next Halving</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Blocks Until</span>
                        <span class="data-value">{blocks_until_halving:,}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Est. Date</span>
                        <span class="data-value accent">{next_halving}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">New Reward</span>
                        <span class="data-value">{block_reward/2} BTC</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Mempool TXs</span>
                        <span class="data-value">{mempool_count:,}</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128176;</div>
                        <span class="card-title">Supply</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Circulating</span>
                        <span class="data-value">{circulating/1e6:.2f}M BTC</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Remaining</span>
                        <span class="data-value accent">{remaining/1e6:.2f}M BTC</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">% Mined</span>
                        <span class="data-value">{(circulating/21000000)*100:.2f}%</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Sats per $1</span>
                        <span class="data-value">{sats_per_dollar:,}</span>
                    </div>
                </div>
            </div>

            <!-- Mini Stats -->
            <div class="mini-stats">
                <div class="mini-stat">
                    <div class="mini-stat-label">Hash Rate</div>
                    <div class="mini-stat-value">{hash_rate/1e6:,.0f} EH/s</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Transactions</div>
                    <div class="mini-stat-value">{tx_count:,.0f}</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Fee Rate</div>
                    <div class="mini-stat-value">{fee_fastest} sat/vB</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Nodes</div>
                    <div class="mini-stat-value">{nodes:,}</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Difficulty</div>
                    <div class="mini-stat-value">{blockchain.get('difficulty_current', 0)/1e12:.1f}T</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Avg Fee</div>
                    <div class="mini-stat-value">${avg_tx_fee:.2f}</div>
                </div>
            </div>

            <!-- On-Chain Analytics -->
            <div class="section-header mt-40">
                <h2 class="section-title">On-Chain Analytics</h2>
                <p class="section-subtitle">Network activity and address metrics</p>
            </div>

            <div class="grid-2 mb-24">
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128101;</div>
                        <span class="card-title">Address Activity</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Active Addresses (24h)</span>
                        <span class="data-value accent">{active_addresses:,.0f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">7-Day Average</span>
                        <span class="data-value">{active_addresses_avg:,.0f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">New Addresses</span>
                        <span class="data-value">{new_addresses:,.0f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Whale Txs (Recent)</span>
                        <span class="data-value">{whale_txs}</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128176;</div>
                        <span class="card-title">Transaction Volume</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">24h Volume (USD)</span>
                        <span class="data-value accent">{fmt(tx_volume_usd)}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Daily Transactions</span>
                        <span class="data-value">{tx_count:,.0f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Avg Tx Fee</span>
                        <span class="data-value">${avg_tx_fee:.2f}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Mempool Size</span>
                        <span class="data-value">{mempool_count:,} txs</span>
                    </div>
                </div>
            </div>

            <!-- Market & Trading Data -->
            <div class="section-header mt-40">
                <h2 class="section-title">Market & Trading Data</h2>
                <p class="section-subtitle">Futures, dominance, and liquidations</p>
            </div>

            <div class="grid-2 mb-24">
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#127760;</div>
                        <span class="card-title">Market Dominance</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">BTC Dominance</span>
                        <span class="data-value accent">{btc_dominance:.1f}%</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Total Crypto MCap</span>
                        <span class="data-value">{fmt(total_crypto_mcap)}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">BTC Market Cap</span>
                        <span class="data-value">{fmt(market_cap)}</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128200;</div>
                        <span class="card-title">Trading Volume</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">24h Volume</span>
                        <span class="data-value accent">{fmt(volume)}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Volume/MCap Ratio</span>
                        <span class="data-value">{(volume/market_cap*100) if market_cap else 0:.2f}%</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">24h Tx Volume</span>
                        <span class="data-value">{fmt(tx_volume_usd)}</span>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer>
        <div class="container">
            <p class="footer-text">Bitcoin Market Narrative Generator</p>
            <p class="footer-links">Data: CoinGecko · Alternative.me · Blockchain.com · Mempool.space · Blockchair</p>
            <p class="footer-links" style="margin-top: 8px;">
                <span id="last-update">Last updated: {time_now}</span> ·
                <span id="update-status">Auto-refresh: ON</span>
            </p>
        </div>
    </footer>

    <script>
        // ===== Configuration =====
        const PRICE_UPDATE_INTERVAL = 10000;  // 10 seconds for price
        const CHART_UPDATE_INTERVAL = 60000;  // 60 seconds for chart data
        const FULL_UPDATE_INTERVAL = 120000;  // 2 minutes for all other data

        let priceChart = null;
        let currentTimeframe = 7;
        let chartData = [];
        let lastPrice = {price};

        // ===== Formatters =====
        function formatPrice(n) {{
            return '$' + n.toLocaleString('en-US', {{maximumFractionDigits: 0}});
        }}

        function formatPriceDecimal(n) {{
            return '$' + n.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
        }}

        function formatPercent(n) {{
            const sign = n >= 0 ? '+' : '';
            return sign + n.toFixed(2) + '%';
        }}

        function formatLarge(n) {{
            if (n >= 1e12) return '$' + (n/1e12).toFixed(2) + 'T';
            if (n >= 1e9) return '$' + (n/1e9).toFixed(2) + 'B';
            if (n >= 1e6) return '$' + (n/1e6).toFixed(2) + 'M';
            return '$' + n.toLocaleString();
        }}

        // ===== Chart Functions =====
        async function fetchChartData(days) {{
            // Determine interval based on timeframe
            let interval = 'daily';
            if (days <= 1) interval = '';  // CoinGecko auto-selects for 1 day
            else if (days <= 7) interval = '';  // Auto for better resolution

            const url = `https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=${{days}}${{interval ? '&interval=' + interval : ''}}`;

            console.log('Fetching chart data:', url);

            try {{
                const response = await fetch(url);

                if (response.status === 429) {{
                    console.warn('Rate limited - using cached data');
                    return chartData.length > 0 ? chartData : [];
                }}

                if (!response.ok) {{
                    console.error('API error:', response.status);
                    return chartData.length > 0 ? chartData : [];
                }}

                const data = await response.json();

                if (data.prices && data.prices.length > 0) {{
                    console.log('Got ' + data.prices.length + ' data points');
                    return data.prices;
                }}

                return chartData.length > 0 ? chartData : [];
            }} catch (error) {{
                console.error('Chart data fetch failed:', error);
                return chartData.length > 0 ? chartData : [];
            }}
        }}

        function initChart() {{
            const ctx = document.getElementById('priceChart').getContext('2d');

            const gradient = ctx.createLinearGradient(0, 0, 0, 300);
            gradient.addColorStop(0, 'rgba(246, 133, 27, 0.3)');
            gradient.addColorStop(1, 'rgba(246, 133, 27, 0)');

            priceChart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: [],
                    datasets: [{{
                        label: 'BTC Price',
                        data: [],
                        borderColor: '#f6851b',
                        backgroundColor: gradient,
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 6,
                        pointHoverBackgroundColor: '#f6851b',
                        pointHoverBorderColor: '#fff',
                        pointHoverBorderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{
                        intersect: false,
                        mode: 'index'
                    }},
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            backgroundColor: '#161b22',
                            titleColor: '#f0f6fc',
                            bodyColor: '#f0f6fc',
                            borderColor: '#30363d',
                            borderWidth: 1,
                            padding: 12,
                            displayColors: false,
                            callbacks: {{
                                title: (items) => {{
                                    const date = new Date(items[0].label);
                                    return date.toLocaleString();
                                }},
                                label: (item) => formatPriceDecimal(item.raw)
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            display: true,
                            grid: {{ color: 'rgba(48, 54, 61, 0.5)', drawBorder: false }},
                            ticks: {{
                                color: '#6e7681',
                                maxTicksLimit: 6,
                                callback: function(val, index) {{
                                    const date = new Date(this.getLabelForValue(val));
                                    if (currentTimeframe <= 1) {{
                                        return date.toLocaleTimeString([], {{hour: '2-digit', minute: '2-digit'}});
                                    }}
                                    return date.toLocaleDateString([], {{month: 'short', day: 'numeric'}});
                                }}
                            }}
                        }},
                        y: {{
                            display: true,
                            position: 'right',
                            grid: {{ color: 'rgba(48, 54, 61, 0.5)', drawBorder: false }},
                            ticks: {{
                                color: '#6e7681',
                                callback: (val) => formatPrice(val)
                            }}
                        }}
                    }}
                }}
            }});
        }}

        async function updateChart(days) {{
            currentTimeframe = days;
            chartData = await fetchChartData(days);

            if (chartData.length === 0) return;

            const labels = chartData.map(p => p[0]);
            const prices = chartData.map(p => p[1]);

            priceChart.data.labels = labels;
            priceChart.data.datasets[0].data = prices;
            priceChart.update('none');

            // Update chart stats
            const high = Math.max(...prices);
            const low = Math.min(...prices);
            const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
            const change = ((prices[prices.length - 1] - prices[0]) / prices[0]) * 100;

            document.getElementById('chart-high').textContent = formatPriceDecimal(high);
            document.getElementById('chart-low').textContent = formatPriceDecimal(low);
            document.getElementById('chart-avg').textContent = formatPriceDecimal(avg);

            const changeEl = document.getElementById('chart-change');
            changeEl.textContent = formatPercent(change);
            changeEl.style.color = change >= 0 ? '#3fb950' : '#f85149';
        }}

        function addPriceToChart(newPrice) {{
            if (!priceChart || chartData.length === 0) return;

            const now = Date.now();
            chartData.push([now, newPrice]);

            // Remove old data points if too many
            const maxPoints = currentTimeframe <= 1 ? 96 : (currentTimeframe * 24);
            if (chartData.length > maxPoints) {{
                chartData.shift();
            }}

            priceChart.data.labels = chartData.map(p => p[0]);
            priceChart.data.datasets[0].data = chartData.map(p => p[1]);
            priceChart.update('none');
        }}

        // ===== Data Update Functions =====
        async function updatePrice() {{
            try {{
                const response = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true&include_market_cap=true&include_24hr_vol=true');
                const data = await response.json();

                if (data.bitcoin) {{
                    const btc = data.bitcoin;
                    const newPrice = btc.usd;

                    // Update hero price with flash effect
                    const heroPrice = document.querySelector('.hero-price');
                    if (heroPrice) {{
                        const oldPrice = lastPrice;
                        heroPrice.textContent = formatPrice(newPrice);
                        if (newPrice !== oldPrice) {{
                            heroPrice.style.transition = 'color 0.3s';
                            heroPrice.style.color = newPrice > oldPrice ? '#3fb950' : '#f85149';
                            setTimeout(() => {{ heroPrice.style.color = '#f0f6fc'; }}, 500);
                        }}
                        lastPrice = newPrice;
                    }}

                    // Update 24h change
                    const heroChange = document.querySelector('.hero-change');
                    if (heroChange) {{
                        const change = btc.usd_24h_change || 0;
                        const arrow = change >= 0 ? '↑' : '↓';
                        heroChange.innerHTML = arrow + ' ' + formatPercent(change) + ' (24h)';
                        heroChange.style.background = change >= 0 ? 'rgba(63, 185, 80, 0.1)' : 'rgba(248, 81, 73, 0.1)';
                        heroChange.style.color = change >= 0 ? '#3fb950' : '#f85149';
                    }}

                    // Update stats row
                    const statItems = document.querySelectorAll('.stat-item');
                    if (statItems[0]) statItems[0].querySelector('.stat-value').textContent = formatLarge(btc.usd_market_cap);
                    if (statItems[1]) statItems[1].querySelector('.stat-value').textContent = formatLarge(btc.usd_24h_vol);

                    // Update current price in cards
                    const priceValues = document.querySelectorAll('.data-value.accent');
                    if (priceValues[0]) priceValues[0].textContent = formatPriceDecimal(newPrice);

                    // Add to chart if timeframe is 24h
                    if (currentTimeframe <= 1) {{
                        addPriceToChart(newPrice);
                    }}

                    // Update timestamp
                    const now = new Date();
                    document.getElementById('last-update').textContent =
                        'Last updated: ' + now.toUTCString().slice(17, 25) + ' UTC';
                }}
            }} catch (error) {{
                console.log('Price update failed:', error);
            }}
        }}

        async function updateFearGreed() {{
            try {{
                const response = await fetch('https://api.alternative.me/fng/');
                const data = await response.json();

                if (data.data && data.data[0]) {{
                    const fg = data.data[0];
                    const value = parseInt(fg.value);
                    const classification = fg.value_classification;

                    const fgValue = document.querySelector('.fg-value');
                    const fgLabel = document.querySelector('.fg-label');
                    const fgIndicator = document.querySelector('.fg-indicator');

                    if (fgValue) fgValue.textContent = value;
                    if (fgLabel) fgLabel.textContent = classification;
                    if (fgIndicator) fgIndicator.style.left = value + '%';

                    // Update colors based on value
                    let color;
                    if (value >= 75) color = '#22c55e';
                    else if (value >= 55) color = '#84cc16';
                    else if (value >= 45) color = '#eab308';
                    else if (value >= 25) color = '#f97316';
                    else color = '#ef4444';

                    if (fgValue) fgValue.style.color = color;
                    if (fgLabel) fgLabel.style.color = color;
                }}
            }} catch (error) {{
                console.log('Fear & Greed update failed:', error);
            }}
        }}

        async function updateExtendedData() {{
            try {{
                // Fetch Bitcoin data with more details
                const response = await fetch('https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&community_data=false&developer_data=false');
                const data = await response.json();

                if (data.market_data) {{
                    const md = data.market_data;

                    // Update 7d and 30d changes
                    const statItems = document.querySelectorAll('.stat-item');
                    if (statItems[2]) {{
                        const change7d = md.price_change_percentage_7d || 0;
                        const el = statItems[2].querySelector('.stat-value');
                        el.textContent = formatPercent(change7d);
                        el.className = 'stat-value ' + (change7d >= 0 ? 'green' : 'red');
                    }}
                    if (statItems[3]) {{
                        const change30d = md.price_change_percentage_30d || 0;
                        const el = statItems[3].querySelector('.stat-value');
                        el.textContent = formatPercent(change30d);
                        el.className = 'stat-value ' + (change30d >= 0 ? 'green' : 'red');
                    }}
                }}
            }} catch (error) {{
                console.log('Extended data update failed:', error);
            }}

            // Also update Fear & Greed
            await updateFearGreed();
        }}

        // ===== Initialize =====
        document.addEventListener('DOMContentLoaded', async function() {{
            // Initialize chart
            initChart();

            // Set up timeframe button event listeners
            document.querySelectorAll('.timeframe-btn').forEach(btn => {{
                btn.addEventListener('click', async function(e) {{
                    e.preventDefault();

                    // Update button states
                    document.querySelectorAll('.timeframe-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');

                    // Show loading state
                    const chartWrapper = document.querySelector('.chart-wrapper');
                    chartWrapper.style.opacity = '0.5';

                    const days = parseInt(this.dataset.days);
                    console.log('Switching to ' + days + ' day view...');

                    try {{
                        await updateChart(days);
                    }} catch (err) {{
                        console.error('Chart update failed:', err);
                    }}

                    chartWrapper.style.opacity = '1';
                }});
            }});

            // Load initial chart data
            console.log('Loading initial 7-day chart...');
            await updateChart(7);

            // Start update intervals
            setInterval(updatePrice, PRICE_UPDATE_INTERVAL);
            setInterval(() => updateChart(currentTimeframe), CHART_UPDATE_INTERVAL);
            setInterval(updateExtendedData, FULL_UPDATE_INTERVAL);

            // Initial updates
            setTimeout(updatePrice, 2000);
            setTimeout(updateExtendedData, 5000);

            console.log('Bitcoin Report: Live updates enabled');
            console.log('  - Price: every 10s');
            console.log('  - Chart: every 60s');
            console.log('  - Extended data: every 2min');
        }});
    </script>
</body>
</html>'''
        return html


if __name__ == "__main__":
    # Test with sample data
    sample_data = {
        "bitcoin": {
            "price_usd": 95000,
            "price_change_24h_percent": 2.5,
            "price_change_7d_percent": -1.2,
            "price_change_30d_percent": 15.3,
            "market_cap_usd": 1850000000000,
            "volume_24h_usd": 45000000000,
            "ath_usd": 108000,
            "ath_change_percent": -12.0,
            "circulating_supply": 19500000,
            "total_supply": 21000000,
        },
        "fear_greed": {
            "value": 72,
            "classification": "Greed",
            "history": [
                {"value": 72, "classification": "Greed", "date": "2026-01-30"},
                {"value": 68, "classification": "Greed", "date": "2026-01-29"},
            ]
        },
        "blockchain": {
            "hash_rate_current": 550000000,
            "hash_rate_30d_avg": 540000000,
            "tx_count_current": 350000,
            "tx_count_30d_avg": 340000,
            "difficulty_current": 75000000000000,
            "difficulty_30d_change": 5.2,
        },
        "price_history_30d": {
            "price_high": 98000,
            "price_low": 82000,
            "price_start": 85000,
            "price_end": 95000,
            "avg_volume": 42000000000,
        },
        "price_history_7d": {
            "price_high": 96500,
            "price_low": 92000,
        }
    }

    generator = ReportGenerator()
    report = generator.generate_report(sample_data)
    print(report)
