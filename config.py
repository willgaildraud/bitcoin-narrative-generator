"""Configuration settings for Bitcoin Market Narrative Generator."""

import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# CoinGecko API (free, no key required)
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# Alternative.me Fear & Greed API
FEAR_GREED_URL = "https://api.alternative.me/fng/"

# Blockchain.com API
BLOCKCHAIN_BASE_URL = "https://api.blockchain.info"

# Rate limiting (CoinGecko free tier: ~10-30 calls/min)
API_DELAY_SECONDS = 6

# Claude Model
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Output settings
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
