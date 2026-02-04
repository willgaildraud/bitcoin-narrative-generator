"""Report generation module using Claude API or template-based fallback."""

import json
import os
from datetime import datetime
from pathlib import Path
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
        self.glossary = self._load_glossary()

        if self.use_ai:
            import anthropic
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def _load_glossary(self) -> dict:
        """Load glossary data from JSON file."""
        glossary_path = Path(__file__).parent / "data" / "glossary.json"
        try:
            with open(glossary_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"metrics": {}, "categories": {}}

    def _get_glossary_json(self) -> str:
        """Return glossary data as JSON string for embedding in HTML."""
        return json.dumps(self.glossary, indent=None)

    def _info_icon(self, metric_key: str) -> str:
        """Generate an info icon with tooltip for a metric."""
        metric = self.glossary.get("metrics", {}).get(metric_key)
        if not metric:
            return ""
        return f'<span class="info-icon" data-metric="{metric_key}" aria-label="Learn more about {metric.get("displayName", metric_key)}">i</span>'

    def _calculate_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """Calculate rule-based market signals from data."""
        signals = {}
        bitcoin = data.get("bitcoin", {})
        history_200d = data.get("price_history_200d", {})
        history_90d = data.get("price_history_90d", {})
        history_30d = data.get("price_history_30d", {})
        blockchain = data.get("blockchain", {})
        block_stats = data.get("block_stats", {})
        market_data = data.get("market_data", {})

        # Use 200d history for MA200, fallback to 90d for shorter MAs
        ma_data_200 = history_200d.get("moving_averages", {}) if history_200d else {}
        ma_data_90 = history_90d.get("moving_averages", {}) if history_90d else {}

        price = bitcoin.get("price_usd", 0) or 0
        sma_50 = ma_data_200.get("sma_50_current") or ma_data_90.get("sma_50_current", 0) or 0
        sma_200 = ma_data_200.get("sma_200_current", 0) or 0

        # MA50 Trend Signal
        if price and sma_50:
            if price > sma_50:
                signals["ma50_trend"] = {"status": "bullish", "label": "Above 50D MA", "icon": "up"}
            else:
                signals["ma50_trend"] = {"status": "bearish", "label": "Below 50D MA", "icon": "down"}
        else:
            signals["ma50_trend"] = {"status": "neutral", "label": "N/A", "icon": "neutral"}

        # MA200 Trend Signal (long-term trend)
        if price and sma_200:
            if price > sma_200:
                signals["ma200_trend"] = {"status": "bullish", "label": "Above 200D MA", "icon": "up"}
            else:
                signals["ma200_trend"] = {"status": "bearish", "label": "Below 200D MA", "icon": "down"}
        else:
            signals["ma200_trend"] = {"status": "neutral", "label": "N/A", "icon": "neutral"}

        # Golden/Death Cross Signal (50D vs 200D)
        if sma_50 and sma_200:
            if sma_50 > sma_200:
                signals["cross"] = {"status": "bullish", "label": "Golden Cross", "icon": "up"}
            else:
                signals["cross"] = {"status": "bearish", "label": "Death Cross", "icon": "down"}
        else:
            signals["cross"] = {"status": "neutral", "label": "N/A", "icon": "neutral"}

        # Volume Signal (compare 24h volume to 30d average)
        current_vol = bitcoin.get("volume_24h_usd", 0) or 0
        avg_vol = history_30d.get("avg_volume", 0) or 1
        vol_ratio = current_vol / avg_vol if avg_vol else 1

        if vol_ratio > 1.5:
            signals["volume"] = {"status": "high", "label": "High Volume", "icon": "up", "ratio": vol_ratio}
        elif vol_ratio < 0.7:
            signals["volume"] = {"status": "low", "label": "Low Volume", "icon": "down", "ratio": vol_ratio}
        else:
            signals["volume"] = {"status": "normal", "label": "Normal Volume", "icon": "neutral", "ratio": vol_ratio}

        # Mempool/Fee Signal
        fee_fastest = block_stats.get("fee_fastest", 0) or 0
        if fee_fastest > 50:
            signals["mempool"] = {"status": "congested", "label": "Congested", "icon": "up", "fee": fee_fastest}
        elif fee_fastest > 20:
            signals["mempool"] = {"status": "moderate", "label": "Moderate Fees", "icon": "neutral", "fee": fee_fastest}
        else:
            signals["mempool"] = {"status": "clear", "label": "Clear", "icon": "down", "fee": fee_fastest}

        # Hash Rate Signal (7d vs 30d average)
        hr_current = blockchain.get("hash_rate_current", 0) or 0
        hr_avg = blockchain.get("hash_rate_30d_avg", 0) or 1
        hr_change = ((hr_current - hr_avg) / hr_avg * 100) if hr_avg else 0

        if hr_change > 5:
            signals["hash_rate"] = {"status": "rising", "label": "Rising", "icon": "up", "change": hr_change}
        elif hr_change < -5:
            signals["hash_rate"] = {"status": "falling", "label": "Falling", "icon": "down", "change": hr_change}
        else:
            signals["hash_rate"] = {"status": "stable", "label": "Stable", "icon": "neutral", "change": hr_change}

        # BTC Dominance Signal (use 7d change if available, otherwise estimate)
        btc_dom = market_data.get("btc_dominance", 0) or 0
        # For now we'll just show current dominance level as the signal
        if btc_dom > 55:
            signals["dominance"] = {"status": "strong", "label": f"{btc_dom:.1f}% Dominant", "icon": "up", "value": btc_dom}
        elif btc_dom > 45:
            signals["dominance"] = {"status": "moderate", "label": f"{btc_dom:.1f}%", "icon": "neutral", "value": btc_dom}
        else:
            signals["dominance"] = {"status": "weak", "label": f"{btc_dom:.1f}% Low", "icon": "down", "value": btc_dom}

        return signals

    def _trend_arrow(self, change: float, threshold: float = 0) -> str:
        """Generate a trend arrow based on change percentage."""
        if change > threshold:
            return '<span class="trend-arrow up" title="Increasing">&#8593;</span>'
        elif change < -threshold:
            return '<span class="trend-arrow down" title="Decreasing">&#8595;</span>'
        else:
            return '<span class="trend-arrow neutral" title="Stable">&#8594;</span>'

    def _generate_sparkline(self, values: list, width: int = 60, height: int = 20, color: str = "#f6851b") -> str:
        """Generate an inline SVG sparkline from a list of values."""
        if not values or len(values) < 2:
            return ""

        # Normalize values
        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val if max_val != min_val else 1

        points = []
        for i, v in enumerate(values):
            x = (i / (len(values) - 1)) * width
            y = height - ((v - min_val) / val_range) * height
            points.append(f"{x:.1f},{y:.1f}")

        path = "M" + " L".join(points)

        # Determine color based on trend
        start_val = values[0]
        end_val = values[-1]
        if end_val > start_val:
            stroke_color = "#3fb950"  # green
        elif end_val < start_val:
            stroke_color = "#f85149"  # red
        else:
            stroke_color = color

        return f'''<svg class="sparkline" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <path d="{path}" fill="none" stroke="{stroke_color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>'''

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

*Report generated by The Bitcoin Pulse ({generation_method})*
"""
        return full_report

    def convert_to_html(self, markdown_content: str, data: dict[str, Any] = None) -> str:
        """Convert Markdown report to styled HTML."""
        bitcoin = data.get("bitcoin", {}) if data else {}
        fear_greed = data.get("fear_greed", {}) if data else {}
        blockchain = data.get("blockchain", {}) if data else {}
        history_30d = data.get("price_history_30d", {}) if data else {}
        history_90d = data.get("price_history_90d", {}) if data else {}
        block_stats = data.get("block_stats", {}) if data else {}
        network_stats = data.get("network_stats", {}) if data else {}
        address_stats = data.get("address_stats", {}) if data else {}
        supply_stats = data.get("supply_stats", {}) if data else {}
        historical_prices = data.get("historical_on_this_day", []) if data else []
        historical_yearly = data.get("historical_yearly_data", {}) if data else {}
        onchain = data.get("onchain_analytics", {}) if data else {}
        market = data.get("market_data", {}) if data else {}
        bitcoin_news = data.get("bitcoin_news", []) if data else []

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

        # Moving averages data (from 90d history for better accuracy)
        ma_data = history_90d.get('moving_averages', {}) if history_90d else {}
        sma_7 = ma_data.get('sma_7_current', 0) or 0
        sma_20 = ma_data.get('sma_20_current', 0) or 0
        sma_50 = ma_data.get('sma_50_current', 0) or 0
        price_vs_sma_7 = ma_data.get('price_vs_sma_7', 0) or 0
        price_vs_sma_20 = ma_data.get('price_vs_sma_20', 0) or 0
        price_vs_sma_50 = ma_data.get('price_vs_sma_50', 0) or 0

        # Full price data for chart with MAs
        full_price_data = history_90d.get('full_price_data', []) if history_90d else []
        sma_7_data = ma_data.get('sma_7', []) if ma_data else []
        sma_20_data = ma_data.get('sma_20', []) if ma_data else []
        sma_50_data = ma_data.get('sma_50', []) if ma_data else []

        # Calculate market signals
        signals = self._calculate_signals(data) if data else {}

        # Convert news to JSON for embedding in JavaScript
        news_json = json.dumps(bitcoin_news) if bitcoin_news else "[]"

        # Generate sparklines for key metrics
        price_sparkline = ""
        if full_price_data:
            recent_prices = [p[1] for p in full_price_data[-30:]]
            price_sparkline = self._generate_sparkline(recent_prices, width=60, height=20)

        # Generate signals card HTML
        def signal_icon(icon_type):
            if icon_type == "up":
                return '<span class="signal-icon">&#8593;</span>'
            elif icon_type == "down":
                return '<span class="signal-icon">&#8595;</span>'
            else:
                return '<span class="signal-icon">&#8594;</span>'

        signals_html = ""
        if signals:
            signals_html = f'''
            <!-- Market Signals Card -->
            <div class="card mt-24" style="margin-bottom: 24px;">
                <div class="card-header">
                    <div class="card-icon">&#128161;</div>
                    <h3 class="card-title">Market Signals</h3>
                </div>
                <div class="signals-grid">
                    <div class="signal-item">
                        <div class="signal-label">50D MA Trend</div>
                        <div class="signal-value {signals.get("ma50_trend", {}).get("status", "neutral")}">
                            {signal_icon(signals.get("ma50_trend", {}).get("icon", "neutral"))}
                            {signals.get("ma50_trend", {}).get("label", "N/A")}
                        </div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-label">200D MA Trend</div>
                        <div class="signal-value {signals.get("ma200_trend", {}).get("status", "neutral")}">
                            {signal_icon(signals.get("ma200_trend", {}).get("icon", "neutral"))}
                            {signals.get("ma200_trend", {}).get("label", "N/A")}
                        </div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-label">MA Cross</div>
                        <div class="signal-value {signals.get("cross", {}).get("status", "neutral")}">
                            {signal_icon(signals.get("cross", {}).get("icon", "neutral"))}
                            {signals.get("cross", {}).get("label", "N/A")}
                        </div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-label">Volume</div>
                        <div class="signal-value {signals.get("volume", {}).get("status", "neutral")}">
                            {signal_icon(signals.get("volume", {}).get("icon", "neutral"))}
                            {signals.get("volume", {}).get("label", "Normal")}
                        </div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-label">Mempool</div>
                        <div class="signal-value {signals.get("mempool", {}).get("status", "neutral")}">
                            {signal_icon(signals.get("mempool", {}).get("icon", "neutral"))}
                            {signals.get("mempool", {}).get("label", "Normal")}
                        </div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-label">Hash Rate</div>
                        <div class="signal-value {signals.get("hash_rate", {}).get("status", "neutral")}">
                            {signal_icon(signals.get("hash_rate", {}).get("icon", "neutral"))}
                            {signals.get("hash_rate", {}).get("label", "Stable")}
                        </div>
                    </div>
                </div>
                <div class="signals-disclaimer">
                    Rule-based signals for informational purposes only. Not financial advice.
                </div>
            </div>
            '''

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

        # Generate historical prices HTML as a clean table
        historical_section = ""
        if historical_prices:
            # Build table rows
            table_rows = ""
            for i, hp in enumerate(historical_prices[:12]):
                year = hp["year"]
                price_val = hp["price"]
                # Calculate year-over-year change if we have previous year data
                yoy_change = ""
                if i < len(historical_prices) - 1:
                    prev_price = historical_prices[i + 1]["price"]
                    if prev_price > 0:
                        change_pct = ((price_val - prev_price) / prev_price) * 100
                        change_color = "var(--green)" if change_pct >= 0 else "var(--red)"
                        yoy_change = f'<span style="color: {change_color}">{change_pct:+.1f}%</span>'

                table_rows += f'''<tr>
                    <td class="history-year-cell">{year}</td>
                    <td class="history-price-cell">${price_val:,.0f}</td>
                    <td class="history-change-cell">{yoy_change}</td>
                </tr>'''

            historical_section = f'''<div class="section-header mt-40">
                <h2 class="section-title">Bitcoin on {today_short}</h2>
                <p class="section-subtitle">Historical prices for this date across the years</p>
            </div>
            <div class="card mb-24">
                <div class="history-table-wrapper">
                    <table class="history-table">
                        <thead>
                            <tr>
                                <th>Year</th>
                                <th>Price</th>
                                <th>YoY Change</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>
            </div>'''

        # Generate moving averages section
        # Determine trend signal
        if sma_20 and sma_50 and price:
            if price > sma_20 and sma_20 > sma_50:
                trend_signal = "Bullish"
                trend_color = "var(--green)"
            elif price < sma_20 and sma_20 < sma_50:
                trend_signal = "Bearish"
                trend_color = "var(--red)"
            else:
                trend_signal = "Neutral"
                trend_color = "var(--text-secondary)"
        else:
            trend_signal = "N/A"
            trend_color = "var(--text-secondary)"

        ma_section = f'''<div class="card">
            <div class="card-header">
                <div class="card-icon">&#128200;</div>
                <h3 class="card-title">Moving Averages</h3>
            </div>
            <div class="data-row">
                <span class="data-label">7-Day MA</span>
                <span class="data-value" style="color: {"var(--green)" if price > sma_7 and sma_7 else "var(--red)" if sma_7 else "var(--text-secondary)"}">{f"${sma_7:,.0f}" if sma_7 else "N/A"} {f"<small>({price_vs_sma_7:+.1f}%)</small>" if sma_7 else ""}</span>
            </div>
            <div class="data-row">
                <span class="data-label">20-Day MA</span>
                <span class="data-value" style="color: {"var(--green)" if price > sma_20 and sma_20 else "var(--red)" if sma_20 else "var(--text-secondary)"}">{f"${sma_20:,.0f}" if sma_20 else "N/A"} {f"<small>({price_vs_sma_20:+.1f}%)</small>" if sma_20 else ""}</span>
            </div>
            <div class="data-row">
                <span class="data-label">50-Day MA</span>
                <span class="data-value" style="color: {"var(--green)" if price > sma_50 and sma_50 else "var(--red)" if sma_50 else "var(--text-secondary)"}">{f"${sma_50:,.0f}" if sma_50 else "N/A"} {f"<small>({price_vs_sma_50:+.1f}%)</small>" if sma_50 else ""}</span>
            </div>
            <div class="data-row" style="border-top: 1px solid var(--border-color); margin-top: 12px; padding-top: 12px;">
                <span class="data-label">Trend Signal</span>
                <span class="data-value" style="color: {trend_color}">
                    {trend_signal}
                </span>
            </div>
        </div>'''

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Bitcoin Pulse - Live BTC Market Data & Analysis</title>

    <!-- SEO Meta Tags -->
    <meta name="description" content="Live Bitcoin price, market analysis, on-chain metrics, and sentiment data. Track BTC price movements, Fear & Greed Index, hash rate, and network statistics in real-time.">
    <meta name="keywords" content="Bitcoin, BTC, cryptocurrency, price tracker, market analysis, Fear and Greed Index, hash rate, blockchain, on-chain metrics">
    <meta name="author" content="The Bitcoin Pulse">
    <meta name="robots" content="index, follow">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://thebitcoinpulse.com/">
    <meta property="og:title" content="The Bitcoin Pulse - Live BTC Market Data & Analysis">
    <meta property="og:description" content="Live Bitcoin price, market analysis, on-chain metrics, and sentiment data. Track BTC in real-time.">
    <meta property="og:image" content="https://thebitcoinpulse.com/og-image.png">
    <meta property="og:site_name" content="The Bitcoin Pulse">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="https://thebitcoinpulse.com/">
    <meta name="twitter:title" content="The Bitcoin Pulse - Live BTC Market Data">
    <meta name="twitter:description" content="Live Bitcoin price, market analysis, on-chain metrics, and sentiment data.">
    <meta name="twitter:image" content="https://thebitcoinpulse.com/og-image.png">

    <!-- Canonical URL -->
    <link rel="canonical" href="https://thebitcoinpulse.com/">

    <!-- Favicon (placeholder) -->
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#8383;</text></svg>">

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
            margin: 0 0 16px 0;
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

        /* MA Legend */
        .ma-legend {{
            display: flex;
            gap: 16px;
            margin-top: 12px;
            flex-wrap: wrap;
        }}

        .ma-legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.75rem;
            color: var(--text-secondary);
        }}

        .ma-legend-line {{
            width: 20px;
            height: 2px;
            border-radius: 1px;
        }}

        .ma-toggle {{
            display: flex;
            gap: 8px;
            margin-left: auto;
        }}

        .ma-toggle-btn {{
            padding: 4px 8px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: transparent;
            color: var(--text-muted);
            font-size: 0.7rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .ma-toggle-btn.active {{
            background: rgba(255, 255, 255, 0.1);
            border-color: var(--text-secondary);
            color: var(--text-primary);
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
            margin: 0;
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

        /* Historical Table */
        .history-table-wrapper {{
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}

        .history-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
            min-width: 280px;
        }}

        .history-table thead {{
            background: var(--bg-darker);
        }}

        .history-table th {{
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border-color);
        }}

        .history-table th:last-child {{
            text-align: right;
        }}

        .history-table td {{
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }}

        .history-table tr:last-child td {{
            border-bottom: none;
        }}

        .history-table tr:hover {{
            background: var(--bg-card-hover);
        }}

        .history-year-cell {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        .history-price-cell {{
            font-weight: 700;
            color: var(--accent);
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
        }}

        .history-change-cell {{
            text-align: right;
            font-weight: 500;
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
        }}

        /* Section Headers */
        .section-header {{
            margin-bottom: 24px;
        }}

        .section-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0 0 8px 0;
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

        /* Info Icons and Tooltips */
        .info-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            font-size: 10px;
            font-weight: 700;
            font-style: normal;
            color: var(--text-muted);
            background: var(--bg-darker);
            border: 1px solid var(--border-color);
            border-radius: 50%;
            margin-left: 6px;
            cursor: help;
            transition: all 0.2s ease;
            vertical-align: middle;
        }}

        .info-icon:hover {{
            color: var(--accent);
            border-color: var(--accent);
            background: rgba(246, 133, 27, 0.1);
        }}

        /* Desktop Tooltip */
        .tooltip-container {{
            position: relative;
            display: inline-flex;
            align-items: center;
        }}

        .tooltip {{
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%);
            width: 280px;
            padding: 12px 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
            z-index: 1000;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s ease, visibility 0.2s ease;
            pointer-events: none;
        }}

        .tooltip::after {{
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: var(--border-color);
        }}

        .tooltip-container:hover .tooltip {{
            opacity: 1;
            visibility: visible;
        }}

        .tooltip-title {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
        }}

        .tooltip-desc {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            line-height: 1.5;
            margin-bottom: 8px;
        }}

        .tooltip-why {{
            font-size: 0.7rem;
            color: var(--accent);
            font-style: italic;
        }}

        /* Glossary Modal */
        .glossary-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(4px);
            z-index: 9999;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        }}

        .glossary-overlay.active {{
            opacity: 1;
            visibility: visible;
        }}

        .glossary-modal {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.95);
            width: 90%;
            max-width: 600px;
            max-height: 80vh;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            z-index: 10000;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s ease;
            display: flex;
            flex-direction: column;
        }}

        .glossary-overlay.active .glossary-modal {{
            opacity: 1;
            visibility: visible;
            transform: translate(-50%, -50%) scale(1);
        }}

        .glossary-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-color);
        }}

        .glossary-title {{
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0;
        }}

        .glossary-close {{
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-secondary);
            font-size: 18px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .glossary-close:hover {{
            background: var(--bg-darker);
            color: var(--text-primary);
        }}

        .glossary-search {{
            padding: 16px 24px;
            border-bottom: 1px solid var(--border-color);
        }}

        .glossary-search input {{
            width: 100%;
            padding: 10px 14px;
            background: var(--bg-darker);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 0.9rem;
        }}

        .glossary-search input::placeholder {{
            color: var(--text-muted);
        }}

        .glossary-search input:focus {{
            outline: none;
            border-color: var(--accent);
        }}

        .glossary-filters {{
            display: flex;
            gap: 8px;
            padding: 12px 24px;
            border-bottom: 1px solid var(--border-color);
            flex-wrap: wrap;
        }}

        .filter-btn {{
            padding: 6px 12px;
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            color: var(--text-secondary);
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .filter-btn:hover {{
            border-color: var(--accent);
            color: var(--accent);
        }}

        .filter-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
            color: white;
        }}

        .glossary-content {{
            flex: 1;
            overflow-y: auto;
            padding: 16px 24px;
        }}

        .glossary-item {{
            padding: 16px;
            background: var(--bg-darker);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            margin-bottom: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .glossary-item:hover {{
            border-color: var(--accent);
        }}

        .glossary-item-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }}

        .glossary-item-name {{
            font-weight: 600;
            color: var(--text-primary);
            font-size: 0.95rem;
        }}

        .glossary-item-category {{
            font-size: 0.65rem;
            padding: 3px 8px;
            background: rgba(246, 133, 27, 0.1);
            border-radius: 10px;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .glossary-item-short {{
            color: var(--text-secondary);
            font-size: 0.8rem;
            margin-bottom: 8px;
        }}

        .glossary-item-full {{
            color: var(--text-secondary);
            font-size: 0.8rem;
            line-height: 1.6;
            display: none;
        }}

        .glossary-item.expanded .glossary-item-full {{
            display: block;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
        }}

        .glossary-item-why {{
            color: var(--accent);
            font-size: 0.75rem;
            font-style: italic;
            margin-top: 8px;
        }}

        /* Mobile Bottom Sheet */
        @media (max-width: 768px) {{
            .tooltip {{
                display: none !important;
            }}

            .glossary-modal {{
                top: auto;
                bottom: 0;
                left: 0;
                right: 0;
                transform: translateY(100%);
                width: 100%;
                max-width: none;
                max-height: 85vh;
                border-radius: 16px 16px 0 0;
            }}

            .glossary-overlay.active .glossary-modal {{
                transform: translateY(0);
            }}

            .glossary-filters {{
                padding: 12px 16px;
            }}

            .glossary-content {{
                padding: 12px 16px;
            }}
        }}

        /* Nav Learn Link */
        .nav-links {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .nav-link {{
            color: var(--text-secondary);
            font-size: 0.85rem;
            text-decoration: none;
            transition: color 0.2s ease;
            cursor: pointer;
        }}

        .nav-link:hover {{
            color: var(--accent);
        }}

        /* Halving Countdown Widget */
        .halving-widget {{
            background: linear-gradient(135deg, rgba(246, 133, 27, 0.1) 0%, rgba(246, 133, 27, 0.05) 100%);
            border: 1px solid rgba(246, 133, 27, 0.3);
            border-radius: 16px;
            padding: 24px;
            margin: 24px 0;
            text-align: center;
        }}

        .halving-title {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--accent);
            margin-bottom: 16px;
            font-weight: 600;
        }}

        .halving-countdown {{
            display: flex;
            justify-content: center;
            gap: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .countdown-item {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px 20px;
            min-width: 80px;
        }}

        .countdown-value {{
            font-size: 2rem;
            font-weight: 800;
            color: var(--text-primary);
            line-height: 1;
        }}

        .countdown-label {{
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-top: 6px;
        }}

        .halving-progress {{
            margin: 20px 0;
        }}

        .halving-progress-bar {{
            height: 8px;
            background: var(--bg-darker);
            border-radius: 4px;
            overflow: hidden;
            position: relative;
        }}

        .halving-progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--accent-light));
            border-radius: 4px;
            transition: width 0.5s ease;
        }}

        .halving-stats {{
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .halving-info {{
            display: flex;
            justify-content: center;
            gap: 24px;
            margin-top: 16px;
            flex-wrap: wrap;
        }}

        .halving-info-item {{
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}

        .halving-info-item strong {{
            color: var(--text-primary);
        }}

        /* Share Button */
        .share-btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-secondary);
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .share-btn:hover {{
            border-color: var(--accent);
            color: var(--accent);
        }}

        .share-dropdown {{
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 8px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 0;
            min-width: 160px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            z-index: 1000;
            display: none;
        }}

        .share-dropdown.active {{
            display: block;
        }}

        .share-option {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 16px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .share-option:hover {{
            background: var(--bg-darker);
            color: var(--text-primary);
        }}

        .share-container {{
            position: relative;
        }}

        .share-toast {{
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--bg-card);
            border: 1px solid var(--green);
            color: var(--green);
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 0.85rem;
            z-index: 10000;
            opacity: 0;
            transition: all 0.3s ease;
        }}

        .share-toast.show {{
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }}

        /* News Feed */
        .news-feed {{
            margin-top: 40px;
        }}

        .news-grid {{
            display: grid;
            gap: 16px;
        }}

        .news-item {{
            display: flex;
            gap: 16px;
            padding: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            transition: all 0.2s ease;
            text-decoration: none;
        }}

        .news-item:hover {{
            border-color: var(--accent);
            transform: translateY(-2px);
        }}

        .news-content {{
            flex: 1;
        }}

        .news-source {{
            font-size: 0.7rem;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }}

        .news-title {{
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.4;
            margin-bottom: 6px;
        }}

        .news-time {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .news-loading {{
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }}

        @media (max-width: 768px) {{
            .halving-countdown {{
                gap: 10px;
            }}
            .countdown-item {{
                padding: 12px 16px;
                min-width: 65px;
            }}
            .countdown-value {{
                font-size: 1.5rem;
            }}
            .halving-info {{
                gap: 12px;
            }}
        }}

        /* Market Signals Card */
        .signals-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
        }}

        .signal-item {{
            background: var(--bg-darker);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }}

        .signal-label {{
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-bottom: 6px;
        }}

        .signal-value {{
            font-size: 0.85rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}

        .signal-value.bullish, .signal-value.rising, .signal-value.high, .signal-value.strong {{
            color: var(--green);
        }}

        .signal-value.bearish, .signal-value.falling, .signal-value.low, .signal-value.weak {{
            color: var(--red);
        }}

        .signal-value.neutral, .signal-value.normal, .signal-value.stable, .signal-value.moderate, .signal-value.clear {{
            color: var(--text-secondary);
        }}

        .signal-icon {{
            font-size: 1rem;
        }}

        .signals-disclaimer {{
            margin-top: 16px;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
            font-size: 0.7rem;
            color: var(--text-muted);
            text-align: center;
            font-style: italic;
        }}

        /* Trend Arrows */
        .trend-arrow {{
            font-size: 0.85rem;
            font-weight: 700;
            margin-left: 4px;
        }}

        .trend-arrow.up {{
            color: var(--green);
        }}

        .trend-arrow.down {{
            color: var(--red);
        }}

        .trend-arrow.neutral {{
            color: var(--text-muted);
        }}

        /* Sparklines */
        .sparkline {{
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .sparkline-container {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* Lazy Load Chart Skeleton */
        .chart-skeleton {{
            background: linear-gradient(90deg, var(--bg-darker) 25%, var(--bg-card-hover) 50%, var(--bg-darker) 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 8px;
            height: 100%;
        }}

        @keyframes shimmer {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
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

        /* Tablet */
        @media (max-width: 1024px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
            .grid-3 {{ grid-template-columns: 1fr; }}
            .mini-stats {{ grid-template-columns: repeat(3, 1fr); }}
        }}

        /* Mobile landscape / small tablet */
        @media (max-width: 768px) {{
            .container {{ padding: 0 16px; }}

            .hero {{ padding: 40px 0 30px; }}
            .hero-price {{ font-size: 2.5rem; }}
            .hero-change {{ font-size: 0.95rem; padding: 6px 12px; }}
            .hero-label {{ font-size: 0.65rem; margin-bottom: 16px; }}

            .stats-row {{
                grid-template-columns: repeat(2, 1fr);
                margin: 24px 0;
            }}
            .stat-item {{ padding: 16px 12px; }}
            .stat-label {{ font-size: 0.65rem; }}
            .stat-value {{ font-size: 1.2rem; }}

            .chart-container {{ padding: 16px; margin: 16px 0 24px; }}
            .chart-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 12px;
            }}
            .chart-header > div {{
                width: 100%;
                justify-content: space-between;
            }}
            .chart-timeframes {{
                width: 100%;
                justify-content: flex-start;
            }}
            .ma-toggle {{
                width: 100%;
                justify-content: flex-start;
                margin-bottom: 8px;
            }}
            .chart-wrapper {{ height: 250px; }}
            .chart-stats {{
                flex-wrap: wrap;
                gap: 12px;
            }}
            .chart-stat {{
                flex: 1 1 40%;
                min-width: 80px;
            }}

            .card {{ padding: 16px; }}
            .card-header {{ margin-bottom: 12px; padding-bottom: 12px; }}
            .card-icon {{ width: 32px; height: 32px; font-size: 14px; }}
            .card-title {{ font-size: 0.9rem; }}
            .data-row {{ padding: 10px 0; }}
            .data-label {{ font-size: 0.8rem; }}
            .data-value {{ font-size: 0.85rem; }}

            .section-header {{ margin-bottom: 16px; }}
            .section-title {{ font-size: 1.2rem; }}
            .section-subtitle {{ font-size: 0.85rem; }}

            .mini-stats {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
            .mini-stat {{ padding: 12px; }}
            .mini-stat-label {{ font-size: 0.6rem; }}
            .mini-stat-value {{ font-size: 1rem; }}

            .history-table {{ font-size: 0.85rem; }}
            .history-table th, .history-table td {{ padding: 10px 12px; }}

            .ma-legend {{ gap: 10px; }}
            .ma-legend-item {{ font-size: 0.65rem; }}

            .nav-date {{ font-size: 0.75rem; }}
            .logo-text {{ font-size: 0.95rem; }}
            .logo-icon {{ width: 30px; height: 30px; font-size: 16px; }}

            footer {{ padding: 24px 0; }}
            .footer-text {{ font-size: 0.8rem; }}
            .footer-links {{ font-size: 0.7rem; }}
        }}

        /* Mobile portrait */
        @media (max-width: 480px) {{
            .container {{ padding: 0 12px; }}

            .hero {{ padding: 30px 0 20px; }}
            .hero-price {{ font-size: 2rem; }}
            .hero-change {{ font-size: 0.85rem; }}

            .stats-row {{
                grid-template-columns: 1fr 1fr;
                gap: 1px;
            }}
            .stat-item {{ padding: 12px 8px; }}
            .stat-label {{ font-size: 0.6rem; }}
            .stat-value {{ font-size: 1rem; }}

            .chart-container {{ padding: 12px; }}
            .chart-wrapper {{ height: 200px; }}
            .timeframe-btn {{ padding: 5px 8px; font-size: 0.65rem; }}
            .ma-toggle-btn {{ padding: 3px 6px; font-size: 0.6rem; }}
            .chart-stat-label {{ font-size: 0.6rem; }}
            .chart-stat-value {{ font-size: 0.85rem; }}

            .mini-stats {{ grid-template-columns: repeat(2, 1fr); }}

            .history-table {{ font-size: 0.8rem; }}
            .history-table th, .history-table td {{ padding: 8px; }}
            .history-year-cell {{ font-size: 0.85rem; }}
            .history-price-cell {{ font-size: 0.85rem; }}
            .history-change-cell {{ font-size: 0.75rem; }}

            .data-row {{
                flex-direction: column;
                align-items: flex-start;
                gap: 4px;
            }}
            .data-label {{ font-size: 0.75rem; }}
            .data-value {{ font-size: 0.9rem; }}

            .fg-value {{ font-size: 3rem; }}
            .fg-label {{ font-size: 0.95rem; }}

            .logo-text {{ display: none; }}
            .nav-date {{ font-size: 0.7rem; }}
        }}

        /* Very small screens */
        @media (max-width: 360px) {{
            .hero-price {{ font-size: 1.75rem; }}
            .stat-value {{ font-size: 0.9rem; }}
            .chart-timeframes {{ gap: 4px; }}
            .timeframe-btn {{ padding: 4px 6px; }}
        }}

        /* Community Section */
        .community-section {{
            margin-top: 40px;
        }}

        .community-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 24px;
            margin-bottom: 32px;
        }}

        /* Daily Poll */
        .poll-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
        }}

        .poll-question {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 20px;
            text-align: center;
        }}

        .poll-options {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .poll-option {{
            position: relative;
            background: var(--bg-darker);
            border: 2px solid var(--border-color);
            border-radius: 8px;
            padding: 14px 16px;
            cursor: pointer;
            transition: all 0.2s ease;
            overflow: hidden;
        }}

        .poll-option:hover:not(.voted) {{
            border-color: var(--accent);
        }}

        .poll-option.selected {{
            border-color: var(--accent);
            background: rgba(246, 133, 27, 0.1);
        }}

        .poll-option.voted {{
            cursor: default;
        }}

        .poll-option-bar {{
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            background: rgba(246, 133, 27, 0.15);
            transition: width 0.5s ease;
            z-index: 0;
        }}

        .poll-option-content {{
            position: relative;
            z-index: 1;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .poll-option-text {{
            font-weight: 500;
            color: var(--text-primary);
        }}

        .poll-option-pct {{
            font-weight: 600;
            color: var(--accent);
            opacity: 0;
            transition: opacity 0.3s ease;
        }}

        .poll-option.voted .poll-option-pct {{
            opacity: 1;
        }}

        .poll-total {{
            text-align: center;
            margin-top: 16px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        /* Sentiment Widget */
        .sentiment-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
        }}

        .sentiment-question {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 20px;
            text-align: center;
        }}

        .sentiment-buttons {{
            display: flex;
            gap: 16px;
            justify-content: center;
            margin-bottom: 20px;
        }}

        .sentiment-btn {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            padding: 20px 32px;
            background: var(--bg-darker);
            border: 2px solid var(--border-color);
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .sentiment-btn:hover:not(.voted) {{
            transform: translateY(-2px);
        }}

        .sentiment-btn.bullish:hover:not(.voted),
        .sentiment-btn.bullish.selected {{
            border-color: var(--green);
            background: rgba(34, 197, 94, 0.1);
        }}

        .sentiment-btn.bearish:hover:not(.voted),
        .sentiment-btn.bearish.selected {{
            border-color: var(--red);
            background: rgba(239, 68, 68, 0.1);
        }}

        .sentiment-btn.voted {{
            cursor: default;
        }}

        .sentiment-icon {{
            font-size: 2rem;
        }}

        .sentiment-label {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        .sentiment-bar-container {{
            background: var(--bg-darker);
            border-radius: 20px;
            height: 32px;
            overflow: hidden;
            display: flex;
        }}

        .sentiment-bar-bull {{
            background: linear-gradient(90deg, var(--green), #4ade80);
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            padding-left: 12px;
            transition: width 0.5s ease;
        }}

        .sentiment-bar-bear {{
            background: linear-gradient(90deg, #f87171, var(--red));
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 12px;
            transition: width 0.5s ease;
        }}

        .sentiment-bar-pct {{
            font-size: 0.75rem;
            font-weight: 700;
            color: white;
            text-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }}

        .sentiment-total {{
            text-align: center;
            margin-top: 12px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        /* Comments Section */
        .comments-section {{
            margin-top: 32px;
        }}

        .comments-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
        }}

        .comments-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }}

        .comments-icon {{
            font-size: 1.5rem;
        }}

        .comments-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0;
        }}

        .giscus {{
            margin-top: 16px;
        }}

        .giscus-loading {{
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }}

        @media (max-width: 768px) {{
            .community-grid {{
                grid-template-columns: 1fr;
            }}
            .sentiment-btn {{
                padding: 16px 24px;
            }}
            .sentiment-icon {{
                font-size: 1.5rem;
            }}
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
                        <span class="logo-text">The Bitcoin Pulse</span>
                    </a>
                    <div class="nav-links">
                        <span class="nav-link" id="open-glossary">Learn</span>
                        <div class="share-container">
                            <button class="share-btn" id="share-btn">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/>
                                </svg>
                                Share
                            </button>
                            <div class="share-dropdown" id="share-dropdown">
                                <div class="share-option" data-action="copy">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                                    Copy Link
                                </div>
                                <div class="share-option" data-action="twitter">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                                    Share on X
                                </div>
                            </div>
                        </div>
                        <span class="nav-date">{today}</span>
                    </div>
                </div>
            </div>
        </nav>

        <div class="container">
            <section class="hero">
                <span class="hero-label">Live Market Data</span>
                <h1 class="hero-price">${price:,.0f}</h1>
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

            <!-- Halving Countdown Widget -->
            <div class="halving-widget">
                <div class="halving-title">Next Bitcoin Halving</div>
                <div class="halving-countdown" id="halving-countdown">
                    <div class="countdown-item">
                        <div class="countdown-value" id="countdown-days">--</div>
                        <div class="countdown-label">Days</div>
                    </div>
                    <div class="countdown-item">
                        <div class="countdown-value" id="countdown-hours">--</div>
                        <div class="countdown-label">Hours</div>
                    </div>
                    <div class="countdown-item">
                        <div class="countdown-value" id="countdown-mins">--</div>
                        <div class="countdown-label">Minutes</div>
                    </div>
                    <div class="countdown-item">
                        <div class="countdown-value" id="countdown-blocks">--</div>
                        <div class="countdown-label">Blocks</div>
                    </div>
                </div>
                <div class="halving-progress">
                    <div class="halving-progress-bar">
                        <div class="halving-progress-fill" id="halving-progress" style="width: 0%"></div>
                    </div>
                    <div class="halving-stats">
                        <span>Last Halving (2024)</span>
                        <span id="halving-progress-pct">0%</span>
                        <span>Next Halving (~{next_halving})</span>
                    </div>
                </div>
                <div class="halving-info">
                    <div class="halving-info-item">Current Block: <strong>{block_height:,}</strong></div>
                    <div class="halving-info-item">Current Reward: <strong>{block_reward} BTC</strong></div>
                    <div class="halving-info-item">Post-Halving: <strong>{block_reward/2} BTC</strong></div>
                </div>
            </div>

            {signals_html}

            <!-- Price Chart -->
            <div class="chart-container">
                <div class="chart-header">
                    <div style="display: flex; align-items: center; gap: 16px;">
                        <span class="chart-title">Price Chart</span>
                        <span class="live-indicator"><span class="live-dot"></span> Live</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 16px;">
                        <div class="ma-toggle">
                            <button class="ma-toggle-btn active" data-ma="7">7D MA</button>
                            <button class="ma-toggle-btn active" data-ma="20">20D MA</button>
                            <button class="ma-toggle-btn" data-ma="50">50D MA</button>
                        </div>
                        <div class="chart-timeframes">
                            <button class="timeframe-btn" data-days="1">24H</button>
                            <button class="timeframe-btn active" data-days="7">7D</button>
                            <button class="timeframe-btn" data-days="30">30D</button>
                            <button class="timeframe-btn" data-days="90">90D</button>
                        </div>
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
                <div class="ma-legend">
                    <div class="ma-legend-item"><span class="ma-legend-line" style="background: #f6851b;"></span> Price</div>
                    <div class="ma-legend-item" id="legend-ma7"><span class="ma-legend-line" style="background: #58a6ff;"></span> 7D MA</div>
                    <div class="ma-legend-item" id="legend-ma20"><span class="ma-legend-line" style="background: #3fb950;"></span> 20D MA</div>
                    <div class="ma-legend-item" id="legend-ma50" style="display: none;"><span class="ma-legend-line" style="background: #f85149;"></span> 50D MA</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <main class="main-content">
        <div class="container">
            <div class="grid-3 mb-24">
                <!-- Price Range Card -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128200;</div>
                        <h3 class="card-title">30-Day Price Range</h3>
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

                <!-- Moving Averages Card -->
                {ma_section}

                <!-- Fear & Greed Card -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128161;</div>
                        <h3 class="card-title">Market Sentiment<span class="info-icon" data-metric="fear_greed" aria-label="Learn more">i</span></h3>
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
                        <h3 class="card-title">Block Info</h3>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Block Height<span class="info-icon" data-metric="block_height" aria-label="Learn more">i</span></span>
                        <span class="data-value">{block_height:,}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Block Reward<span class="info-icon" data-metric="block_reward" aria-label="Learn more">i</span></span>
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
                        <h3 class="card-title">Next Halving</h3>
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
                        <h3 class="card-title">Supply</h3>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Circulating<span class="info-icon" data-metric="circulating_supply" aria-label="Learn more">i</span></span>
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
                        <span class="data-label">Sats per $1<span class="info-icon" data-metric="sats_per_dollar" aria-label="Learn more">i</span></span>
                        <span class="data-value">{sats_per_dollar:,}</span>
                    </div>
                </div>
            </div>

            <!-- Mini Stats -->
            <div class="mini-stats">
                <div class="mini-stat">
                    <div class="mini-stat-label">Hash Rate<span class="info-icon" data-metric="hash_rate" aria-label="Learn more">i</span></div>
                    <div class="mini-stat-value">{hash_rate/1e6:,.0f} EH/s</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Transactions<span class="info-icon" data-metric="tx_count" aria-label="Learn more">i</span></div>
                    <div class="mini-stat-value">{tx_count:,.0f}</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Fee Rate<span class="info-icon" data-metric="fee_rate" aria-label="Learn more">i</span></div>
                    <div class="mini-stat-value">{fee_fastest} sat/vB</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Nodes<span class="info-icon" data-metric="nodes" aria-label="Learn more">i</span></div>
                    <div class="mini-stat-value">{nodes:,}</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-stat-label">Difficulty<span class="info-icon" data-metric="difficulty" aria-label="Learn more">i</span></div>
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
                        <h3 class="card-title">Address Activity</h3>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Active Addresses (24h)<span class="info-icon" data-metric="active_addresses" aria-label="Learn more">i</span></span>
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
                        <span class="data-label">Whale Txs (Recent)<span class="info-icon" data-metric="whale_transactions" aria-label="Learn more">i</span></span>
                        <span class="data-value">{whale_txs}</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128176;</div>
                        <h3 class="card-title">Transaction Volume</h3>
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
                        <span class="data-label">Mempool Size<span class="info-icon" data-metric="mempool" aria-label="Learn more">i</span></span>
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
                        <h3 class="card-title">Market Dominance</h3>
                    </div>
                    <div class="data-row">
                        <span class="data-label">BTC Dominance<span class="info-icon" data-metric="btc_dominance" aria-label="Learn more">i</span></span>
                        <span class="data-value accent">{btc_dominance:.1f}%</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">Total Crypto MCap</span>
                        <span class="data-value">{fmt(total_crypto_mcap)}</span>
                    </div>
                    <div class="data-row">
                        <span class="data-label">BTC Market Cap<span class="info-icon" data-metric="market_cap" aria-label="Learn more">i</span></span>
                        <span class="data-value">{fmt(market_cap)}</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">&#128200;</div>
                        <h3 class="card-title">Trading Volume</h3>
                    </div>
                    <div class="data-row">
                        <span class="data-label">24h Volume<span class="info-icon" data-metric="volume_24h" aria-label="Learn more">i</span></span>
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

            <!-- Bitcoin News Feed -->
            <div class="section-header mt-40">
                <h2 class="section-title">Bitcoin News</h2>
                <p class="section-subtitle">Latest headlines from around the web</p>
            </div>
            <div class="card mb-24">
                <div class="news-grid" id="news-feed">
                    <div class="news-loading">Loading latest news...</div>
                </div>
            </div>

            <!-- Community Section -->
            <div class="section-header mt-40">
                <h2 class="section-title">Community Pulse</h2>
                <p class="section-subtitle">What does the community think?</p>
            </div>

            <div class="community-grid">
                <!-- Daily Poll -->
                <div class="poll-card">
                    <div class="poll-question">Where will BTC be in 24 hours?</div>
                    <div class="poll-options" id="poll-options">
                        <div class="poll-option" data-option="up10">
                            <div class="poll-option-bar" style="width: 0%"></div>
                            <div class="poll-option-content">
                                <span class="poll-option-text">Up 5%+ </span>
                                <span class="poll-option-pct">0%</span>
                            </div>
                        </div>
                        <div class="poll-option" data-option="up">
                            <div class="poll-option-bar" style="width: 0%"></div>
                            <div class="poll-option-content">
                                <span class="poll-option-text">Slightly up (0-5%)</span>
                                <span class="poll-option-pct">0%</span>
                            </div>
                        </div>
                        <div class="poll-option" data-option="flat">
                            <div class="poll-option-bar" style="width: 0%"></div>
                            <div class="poll-option-content">
                                <span class="poll-option-text">Flat (sideways)</span>
                                <span class="poll-option-pct">0%</span>
                            </div>
                        </div>
                        <div class="poll-option" data-option="down">
                            <div class="poll-option-bar" style="width: 0%"></div>
                            <div class="poll-option-content">
                                <span class="poll-option-text">Slightly down (0-5%)</span>
                                <span class="poll-option-pct">0%</span>
                            </div>
                        </div>
                        <div class="poll-option" data-option="down10">
                            <div class="poll-option-bar" style="width: 0%"></div>
                            <div class="poll-option-content">
                                <span class="poll-option-text">Down 5%+ </span>
                                <span class="poll-option-pct">0%</span>
                            </div>
                        </div>
                    </div>
                    <div class="poll-total" id="poll-total">Cast your vote!</div>
                </div>

                <!-- Sentiment Widget -->
                <div class="sentiment-card">
                    <div class="sentiment-question">What's your outlook?</div>
                    <div class="sentiment-buttons" id="sentiment-buttons">
                        <button class="sentiment-btn bullish" data-sentiment="bullish">
                            <span class="sentiment-icon">&#128640;</span>
                            <span class="sentiment-label">Bullish</span>
                        </button>
                        <button class="sentiment-btn bearish" data-sentiment="bearish">
                            <span class="sentiment-icon">&#128059;</span>
                            <span class="sentiment-label">Bearish</span>
                        </button>
                    </div>
                    <div class="sentiment-bar-container" id="sentiment-bar">
                        <div class="sentiment-bar-bull" id="sentiment-bull" style="width: 50%">
                            <span class="sentiment-bar-pct" id="sentiment-bull-pct">50%</span>
                        </div>
                        <div class="sentiment-bar-bear" id="sentiment-bear" style="width: 50%">
                            <span class="sentiment-bar-pct" id="sentiment-bear-pct">50%</span>
                        </div>
                    </div>
                    <div class="sentiment-total" id="sentiment-total">Join the community!</div>
                </div>
            </div>

            <!-- Comments Section -->
            <div class="comments-section">
                <div class="comments-card">
                    <div class="comments-header">
                        <span class="comments-icon">&#128172;</span>
                        <h3 class="comments-title">Discussion</h3>
                    </div>
                    <div class="giscus" id="giscus-container">
                        <div class="giscus-loading">Loading comments...</div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer>
        <div class="container">
            <p class="footer-text">The Bitcoin Pulse</p>
            <p class="footer-links">Data: CoinGecko · Alternative.me · Blockchain.com · Mempool.space · Blockchair</p>
            <p class="footer-links" style="margin-top: 8px;">
                <span id="last-update">Last updated: {time_now}</span> ·
                <span id="update-status">Auto-refresh: ON</span>
            </p>
        </div>
    </footer>

    <!-- Glossary Modal -->
    <div class="glossary-overlay" id="glossary-overlay">
        <div class="glossary-modal">
            <div class="glossary-header">
                <h2 class="glossary-title">Bitcoin Glossary</h2>
                <button class="glossary-close" id="glossary-close" aria-label="Close glossary">&times;</button>
            </div>
            <div class="glossary-search">
                <input type="text" id="glossary-search-input" placeholder="Search metrics..." autocomplete="off">
            </div>
            <div class="glossary-filters">
                <button class="filter-btn active" data-category="all">All</button>
                <button class="filter-btn" data-category="price">Price & Market</button>
                <button class="filter-btn" data-category="sentiment">Sentiment</button>
                <button class="filter-btn" data-category="network">Network</button>
                <button class="filter-btn" data-category="supply">Supply</button>
                <button class="filter-btn" data-category="trading">Trading</button>
            </div>
            <div class="glossary-content" id="glossary-content">
                <!-- Populated by JavaScript -->
            </div>
        </div>
    </div>

    <script>
        // ===== Glossary Data =====
        const glossaryData = {self._get_glossary_json()};

        // ===== Configuration =====
        const PRICE_UPDATE_INTERVAL = 10000;  // 10 seconds for price
        const CHART_UPDATE_INTERVAL = 60000;  // 60 seconds for chart data
        const FULL_UPDATE_INTERVAL = 120000;  // 2 minutes for all other data

        let priceChart = null;
        let currentTimeframe = 7;
        let chartData = [];
        let lastPrice = {price};
        let isChartLoading = false;

        // MA visibility state
        let showMA7 = true;
        let showMA20 = true;
        let showMA50 = false;

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
        async function fetchChartData(days, retryCount = 0) {{
            const maxRetries = 3;
            const retryDelay = 2000;

            const url = `https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=${{days}}`;

            console.log('Fetching chart data:', url);

            try {{
                const response = await fetch(url);

                if (response.status === 429) {{
                    console.warn('Rate limited');
                    if (retryCount < maxRetries) {{
                        console.log(`Retrying in ${{retryDelay/1000}}s... (attempt ${{retryCount + 1}}/${{maxRetries}})`);
                        await new Promise(resolve => setTimeout(resolve, retryDelay * (retryCount + 1)));
                        return fetchChartData(days, retryCount + 1);
                    }}
                    console.warn('Max retries reached, using cached data');
                    return chartData.length > 0 ? chartData : [];
                }}

                if (!response.ok) {{
                    console.error('API error:', response.status);
                    if (retryCount < maxRetries) {{
                        await new Promise(resolve => setTimeout(resolve, retryDelay));
                        return fetchChartData(days, retryCount + 1);
                    }}
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
                if (retryCount < maxRetries) {{
                    await new Promise(resolve => setTimeout(resolve, retryDelay));
                    return fetchChartData(days, retryCount + 1);
                }}
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
                    datasets: [
                        {{
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
                            pointHoverBorderWidth: 2,
                            order: 0
                        }},
                        {{
                            label: '7D MA',
                            data: [],
                            borderColor: '#58a6ff',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.4,
                            pointRadius: 0,
                            hidden: !showMA7,
                            order: 1
                        }},
                        {{
                            label: '20D MA',
                            data: [],
                            borderColor: '#3fb950',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.4,
                            pointRadius: 0,
                            hidden: !showMA20,
                            order: 2
                        }},
                        {{
                            label: '50D MA',
                            data: [],
                            borderColor: '#f85149',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.4,
                            pointRadius: 0,
                            hidden: !showMA50,
                            order: 3
                        }}
                    ]
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
                            displayColors: true,
                            callbacks: {{
                                title: (items) => {{
                                    const date = new Date(items[0].label);
                                    return date.toLocaleString();
                                }},
                                label: (item) => item.dataset.label + ': ' + formatPriceDecimal(item.raw)
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

        // Calculate moving average from price data
        function calculateMA(prices, period) {{
            if (prices.length < period) return [];

            const ma = [];
            for (let i = 0; i < prices.length; i++) {{
                if (i < period - 1) {{
                    ma.push(null);
                }} else {{
                    const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
                    ma.push(sum / period);
                }}
            }}
            return ma;
        }}

        async function updateChart(days) {{
            if (isChartLoading) return;
            isChartLoading = true;

            // Show loading state
            const chartWrapper = document.querySelector('.chart-wrapper');
            if (chartWrapper) chartWrapper.style.opacity = '0.5';

            currentTimeframe = days;
            const newData = await fetchChartData(days);

            // Only update if we got data
            if (newData && newData.length > 0) {{
                chartData = newData;

                const labels = chartData.map(p => p[0]);
                const prices = chartData.map(p => p[1]);

                // Calculate moving averages
                const ma7 = calculateMA(prices, 7);
                const ma20 = calculateMA(prices, 20);
                const ma50 = calculateMA(prices, 50);

                priceChart.data.labels = labels;
                priceChart.data.datasets[0].data = prices;
                priceChart.data.datasets[1].data = ma7;
                priceChart.data.datasets[2].data = ma20;
                priceChart.data.datasets[3].data = ma50;

                // Update MA visibility
                priceChart.data.datasets[1].hidden = !showMA7;
                priceChart.data.datasets[2].hidden = !showMA20;
                priceChart.data.datasets[3].hidden = !showMA50;

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
            }} else {{
                console.warn('No chart data available for ' + days + ' days');
            }}

            // Remove loading state
            if (chartWrapper) chartWrapper.style.opacity = '1';
            isChartLoading = false;
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
            // Initialize main price chart
            initChart();

            // Set up MA toggle buttons
            document.querySelectorAll('.ma-toggle-btn').forEach(btn => {{
                btn.addEventListener('click', function(e) {{
                    e.preventDefault();

                    const ma = this.dataset.ma;
                    this.classList.toggle('active');

                    if (ma === '7') {{
                        showMA7 = !showMA7;
                        priceChart.data.datasets[1].hidden = !showMA7;
                        document.getElementById('legend-ma7').style.display = showMA7 ? 'flex' : 'none';
                    }} else if (ma === '20') {{
                        showMA20 = !showMA20;
                        priceChart.data.datasets[2].hidden = !showMA20;
                        document.getElementById('legend-ma20').style.display = showMA20 ? 'flex' : 'none';
                    }} else if (ma === '50') {{
                        showMA50 = !showMA50;
                        priceChart.data.datasets[3].hidden = !showMA50;
                        document.getElementById('legend-ma50').style.display = showMA50 ? 'flex' : 'none';
                    }}

                    priceChart.update('none');
                }});
            }});

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

            console.log('The Bitcoin Pulse: Live updates enabled');
            console.log('  - Price: every 10s');
            console.log('  - Chart: every 60s');
            console.log('  - Extended data: every 2min');
            console.log('  - Moving averages: 7D, 20D, 50D');

            // Initialize glossary
            initGlossary();

            // Initialize halving countdown
            initHalvingCountdown();

            // Initialize share button
            initShareButton();

            // Load news feed
            loadNewsFeed();

            // Initialize community features
            initPoll();
            initSentiment();
            initGiscus();
        }});

        // ===== Halving Countdown =====
        const HALVING_DATA = {{
            blocksUntilHalving: {blocks_until_halving},
            currentBlock: {block_height},
            nextHalvingBlock: {block_height + blocks_until_halving},
            lastHalvingBlock: {block_height + blocks_until_halving - 210000}
        }};

        function initHalvingCountdown() {{
            updateHalvingCountdown();
            setInterval(updateHalvingCountdown, 60000); // Update every minute
        }}

        function updateHalvingCountdown() {{
            const blocksLeft = HALVING_DATA.blocksUntilHalving;
            const minutesLeft = blocksLeft * 10; // Avg 10 min per block

            const days = Math.floor(minutesLeft / 1440);
            const hours = Math.floor((minutesLeft % 1440) / 60);
            const mins = Math.floor(minutesLeft % 60);

            document.getElementById('countdown-days').textContent = days;
            document.getElementById('countdown-hours').textContent = hours;
            document.getElementById('countdown-mins').textContent = mins;
            document.getElementById('countdown-blocks').textContent = blocksLeft.toLocaleString();

            // Calculate progress (blocks since last halving / 210000)
            const blocksSinceLastHalving = 210000 - blocksLeft;
            const progressPct = (blocksSinceLastHalving / 210000) * 100;

            document.getElementById('halving-progress').style.width = progressPct.toFixed(1) + '%';
            document.getElementById('halving-progress-pct').textContent = progressPct.toFixed(1) + '%';
        }}

        // ===== Share Button =====
        function initShareButton() {{
            const shareBtn = document.getElementById('share-btn');
            const shareDropdown = document.getElementById('share-dropdown');

            shareBtn.addEventListener('click', (e) => {{
                e.stopPropagation();
                shareDropdown.classList.toggle('active');
            }});

            document.addEventListener('click', () => {{
                shareDropdown.classList.remove('active');
            }});

            shareDropdown.querySelectorAll('.share-option').forEach(option => {{
                option.addEventListener('click', (e) => {{
                    e.stopPropagation();
                    const action = option.dataset.action;

                    if (action === 'copy') {{
                        copyToClipboard();
                    }} else if (action === 'twitter') {{
                        shareToTwitter();
                    }}

                    shareDropdown.classList.remove('active');
                }});
            }});
        }}

        function copyToClipboard() {{
            const url = window.location.href;
            navigator.clipboard.writeText(url).then(() => {{
                showToast('Link copied to clipboard!');
            }}).catch(() => {{
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = url;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                showToast('Link copied to clipboard!');
            }});
        }}

        function shareToTwitter() {{
            const price = document.querySelector('.hero-price').textContent;
            const change = document.querySelector('.hero-change').textContent;
            const text = `Bitcoin is at ${{price}} (${{change}})\\n\\nLive data from The Bitcoin Pulse`;
            const url = 'https://thebitcoinpulse.com';
            const twitterUrl = `https://twitter.com/intent/tweet?text=${{encodeURIComponent(text)}}&url=${{encodeURIComponent(url)}}`;
            window.open(twitterUrl, '_blank', 'width=550,height=420');
        }}

        function showToast(message) {{
            let toast = document.querySelector('.share-toast');
            if (!toast) {{
                toast = document.createElement('div');
                toast.className = 'share-toast';
                document.body.appendChild(toast);
            }}
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }}

        // ===== News Feed =====
        const NEWS_DATA = {news_json};

        function loadNewsFeed() {{
            const newsContainer = document.getElementById('news-feed');
            const news = NEWS_DATA;

            if (!news || news.length === 0) {{
                newsContainer.innerHTML = `
                    <div class="news-item" style="cursor: default;">
                        <div class="news-content">
                            <div class="news-source">Bitcoin News</div>
                            <div class="news-title">No recent news available. Visit bitcoinmagazine.com or coindesk.com for updates.</div>
                            <div class="news-time">--</div>
                        </div>
                    </div>
                `;
                return;
            }}

            newsContainer.innerHTML = news.map(item => `
                <a href="${{item.url}}" target="_blank" rel="noopener" class="news-item">
                    <div class="news-content">
                        <div class="news-source">${{item.source || 'Bitcoin News'}}</div>
                        <div class="news-title">${{item.title}}</div>
                        <div class="news-time">${{formatTimeAgo(item.published_at)}}</div>
                    </div>
                </a>
            `).join('');
        }}

        function formatTimeAgo(dateString) {{
            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            if (diffMins < 60) return `${{diffMins}}m ago`;
            if (diffHours < 24) return `${{diffHours}}h ago`;
            return `${{diffDays}}d ago`;
        }}

        // ===== Community Poll =====
        function initPoll() {{
            const pollOptions = document.querySelectorAll('.poll-option');
            const pollKey = 'btcpulse_poll_' + new Date().toISOString().split('T')[0];
            const votesKey = 'btcpulse_poll_votes';

            // Initialize or get simulated community votes
            let votes = JSON.parse(localStorage.getItem(votesKey) || '{{}}');
            const today = new Date().toISOString().split('T')[0];

            // Reset votes daily - start fresh with 0 votes
            if (votes.date !== today) {{
                votes = {{
                    date: today,
                    up10: 0,
                    up: 0,
                    flat: 0,
                    down: 0,
                    down10: 0
                }};
                localStorage.setItem(votesKey, JSON.stringify(votes));
            }}

            // Check if user already voted today
            const userVote = localStorage.getItem(pollKey);

            if (userVote) {{
                showPollResults(votes, userVote);
            }}

            pollOptions.forEach(option => {{
                option.addEventListener('click', () => {{
                    if (localStorage.getItem(pollKey)) return; // Already voted

                    const selected = option.dataset.option;
                    localStorage.setItem(pollKey, selected);

                    // Add user's vote
                    votes[selected] = (votes[selected] || 0) + 1;
                    localStorage.setItem(votesKey, JSON.stringify(votes));

                    showPollResults(votes, selected);
                }});
            }});
        }}

        function showPollResults(votes, userVote) {{
            const options = ['up10', 'up', 'flat', 'down', 'down10'];
            const total = options.reduce((sum, opt) => sum + (votes[opt] || 0), 0);

            document.querySelectorAll('.poll-option').forEach(option => {{
                const opt = option.dataset.option;
                const count = votes[opt] || 0;
                const pct = total > 0 ? Math.round((count / total) * 100) : 0;

                option.classList.add('voted');
                if (opt === userVote) {{
                    option.classList.add('selected');
                }}

                option.querySelector('.poll-option-bar').style.width = pct + '%';
                option.querySelector('.poll-option-pct').textContent = pct + '%';
            }});

            document.getElementById('poll-total').textContent = `${{total.toLocaleString()}} votes today`;
        }}

        // ===== Sentiment Widget =====
        function initSentiment() {{
            const buttons = document.querySelectorAll('.sentiment-btn');
            const sentimentKey = 'btcpulse_sentiment_' + new Date().toISOString().split('T')[0];
            const votesKey = 'btcpulse_sentiment_votes';

            // Initialize or get simulated community sentiment
            let sentiment = JSON.parse(localStorage.getItem(votesKey) || '{{}}');
            const today = new Date().toISOString().split('T')[0];

            // Reset daily - start fresh with 0 votes
            if (sentiment.date !== today) {{
                sentiment = {{
                    date: today,
                    bullish: 0,
                    bearish: 0
                }};
                localStorage.setItem(votesKey, JSON.stringify(sentiment));
            }}

            // Check if user already voted
            const userVote = localStorage.getItem(sentimentKey);

            updateSentimentBar(sentiment);

            if (userVote) {{
                buttons.forEach(btn => {{
                    btn.classList.add('voted');
                    if (btn.dataset.sentiment === userVote) {{
                        btn.classList.add('selected');
                    }}
                }});
            }}

            buttons.forEach(btn => {{
                btn.addEventListener('click', () => {{
                    if (localStorage.getItem(sentimentKey)) return; // Already voted

                    const vote = btn.dataset.sentiment;
                    localStorage.setItem(sentimentKey, vote);

                    // Add user's vote
                    sentiment[vote] = (sentiment[vote] || 0) + 1;
                    localStorage.setItem(votesKey, JSON.stringify(sentiment));

                    buttons.forEach(b => {{
                        b.classList.add('voted');
                        if (b.dataset.sentiment === vote) {{
                            b.classList.add('selected');
                        }}
                    }});

                    updateSentimentBar(sentiment);
                }});
            }});
        }}

        function updateSentimentBar(sentiment) {{
            const total = (sentiment.bullish || 0) + (sentiment.bearish || 0);
            const bullPct = total > 0 ? Math.round((sentiment.bullish / total) * 100) : 50;
            const bearPct = 100 - bullPct;

            document.getElementById('sentiment-bull').style.width = bullPct + '%';
            document.getElementById('sentiment-bear').style.width = bearPct + '%';
            document.getElementById('sentiment-bull-pct').textContent = bullPct + '%';
            document.getElementById('sentiment-bear-pct').textContent = bearPct + '%';
            document.getElementById('sentiment-total').textContent = `${{total.toLocaleString()}} votes today`;
        }}

        // ===== Discussion Section =====
        function initGiscus() {{
            const container = document.getElementById('giscus-container');

            container.innerHTML = `
                <div style="text-align: center; padding: 24px;">
                    <p style="color: var(--text-primary); font-size: 1rem; margin-bottom: 16px;">
                        Share your thoughts with the community
                    </p>
                    <a href="https://github.com/willgaildraud/bitcoin-narrative-generator/discussions"
                       target="_blank" rel="noopener"
                       style="display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px;
                              background: var(--accent); color: white; text-decoration: none;
                              border-radius: 8px; font-weight: 600; transition: opacity 0.2s;">
                        <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
                        </svg>
                        Join Discussion on GitHub
                    </a>
                    <p style="color: var(--text-muted); font-size: 0.8rem; margin-top: 16px;">
                        Free GitHub account required to comment
                    </p>
                </div>
            `;
        }}

        // ===== Glossary Functions =====
        function initGlossary() {{
            const overlay = document.getElementById('glossary-overlay');
            const closeBtn = document.getElementById('glossary-close');
            const openBtn = document.getElementById('open-glossary');
            const searchInput = document.getElementById('glossary-search-input');
            const content = document.getElementById('glossary-content');
            const filterBtns = document.querySelectorAll('.filter-btn');

            let currentFilter = 'all';

            // Open glossary
            openBtn.addEventListener('click', () => {{
                overlay.classList.add('active');
                document.body.style.overflow = 'hidden';
                renderGlossaryItems();
            }});

            // Close glossary
            closeBtn.addEventListener('click', closeGlossary);
            overlay.addEventListener('click', (e) => {{
                if (e.target === overlay) closeGlossary();
            }});

            // Escape key to close
            document.addEventListener('keydown', (e) => {{
                if (e.key === 'Escape' && overlay.classList.contains('active')) {{
                    closeGlossary();
                }}
            }});

            function closeGlossary() {{
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }}

            // Filter buttons
            filterBtns.forEach(btn => {{
                btn.addEventListener('click', () => {{
                    filterBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentFilter = btn.dataset.category;
                    renderGlossaryItems();
                }});
            }});

            // Search
            searchInput.addEventListener('input', () => {{
                renderGlossaryItems();
            }});

            // Render glossary items
            function renderGlossaryItems() {{
                const searchTerm = searchInput.value.toLowerCase();
                const metrics = glossaryData.metrics || {{}};
                const categories = glossaryData.categories || {{}};

                let html = '';
                Object.entries(metrics).forEach(([key, metric]) => {{
                    // Filter by category
                    if (currentFilter !== 'all' && metric.category !== currentFilter) return;

                    // Filter by search
                    const searchable = (metric.displayName + ' ' + metric.shortDescription + ' ' + metric.fullDescription).toLowerCase();
                    if (searchTerm && !searchable.includes(searchTerm)) return;

                    const categoryInfo = categories[metric.category] || {{ name: metric.category }};

                    html += `
                        <div class="glossary-item" data-metric="${{key}}">
                            <div class="glossary-item-header">
                                <span class="glossary-item-name">${{metric.displayName}}</span>
                                <span class="glossary-item-category">${{categoryInfo.name}}</span>
                            </div>
                            <div class="glossary-item-short">${{metric.shortDescription}}</div>
                            <div class="glossary-item-full">
                                ${{metric.fullDescription}}
                                <div class="glossary-item-why">${{metric.whyItMatters}}</div>
                            </div>
                        </div>
                    `;
                }});

                content.innerHTML = html || '<p style="color: var(--text-muted); text-align: center; padding: 20px;">No metrics found</p>';

                // Add click to expand
                content.querySelectorAll('.glossary-item').forEach(item => {{
                    item.addEventListener('click', () => {{
                        item.classList.toggle('expanded');
                    }});
                }});
            }}

            // Create floating tooltip element
            const tooltip = document.createElement('div');
            tooltip.className = 'floating-tooltip';
            tooltip.style.cssText = `
                position: fixed;
                z-index: 10000;
                max-width: 280px;
                padding: 12px 16px;
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.4);
                pointer-events: none;
                opacity: 0;
                transition: opacity 0.2s ease;
            `;
            document.body.appendChild(tooltip);

            // Handle info icon hover for desktop tooltips
            document.querySelectorAll('.info-icon').forEach(icon => {{
                const metricKey = icon.dataset.metric;
                const metric = glossaryData.metrics[metricKey];

                if (metric) {{
                    // Desktop hover
                    icon.addEventListener('mouseenter', (e) => {{
                        if (window.innerWidth > 768) {{
                            tooltip.innerHTML = `
                                <div style="font-size: 0.85rem; font-weight: 600; color: #f0f6fc; margin-bottom: 6px;">${{metric.displayName}}</div>
                                <div style="font-size: 0.75rem; color: #8b949e; line-height: 1.5; margin-bottom: 8px;">${{metric.fullDescription}}</div>
                                <div style="font-size: 0.7rem; color: #f6851b; font-style: italic;">${{metric.whyItMatters}}</div>
                            `;

                            const rect = icon.getBoundingClientRect();
                            const tooltipWidth = 280;

                            // Position tooltip above the icon
                            let left = rect.left + (rect.width / 2) - (tooltipWidth / 2);
                            let top = rect.top - 10;

                            // Keep within viewport
                            if (left < 10) left = 10;
                            if (left + tooltipWidth > window.innerWidth - 10) {{
                                left = window.innerWidth - tooltipWidth - 10;
                            }}

                            tooltip.style.left = left + 'px';
                            tooltip.style.top = 'auto';
                            tooltip.style.bottom = (window.innerHeight - top) + 'px';
                            tooltip.style.width = tooltipWidth + 'px';
                            tooltip.style.opacity = '1';
                        }}
                    }});

                    icon.addEventListener('mouseleave', () => {{
                        tooltip.style.opacity = '0';
                    }});

                    // Mobile/tablet click - open glossary
                    icon.addEventListener('click', (e) => {{
                        e.stopPropagation();
                        if (window.innerWidth <= 768) {{
                            overlay.classList.add('active');
                            document.body.style.overflow = 'hidden';
                            searchInput.value = metric.displayName || '';
                            currentFilter = 'all';
                            filterBtns.forEach(b => b.classList.remove('active'));
                            filterBtns[0].classList.add('active');
                            renderGlossaryItems();
                        }}
                    }});
                }}
            }});
        }}
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
