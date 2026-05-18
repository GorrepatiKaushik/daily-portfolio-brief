"""
Focused Daily Brief Generator
Tracks a specific list of stocks/ETFs/indexes, pulls prices + targeted news,
summarizes via Claude, sends to Telegram.

Runs on a schedule via GitHub Actions.
"""

import os
import sys
import time
from datetime import datetime
from urllib.parse import quote_plus

import feedparser
import requests
import yfinance as yf
from anthropic import Anthropic

# ============================================================================
# CONFIGURATION — EDIT THIS SECTION
# ============================================================================

# Indian mutual funds don't have reliable Yahoo Finance tickers, so we track
# the underlying index they replicate. Index moves match fund NAV within
# 0.1-0.3% tracking error and are available daily without lag.

PORTFOLIO = [
    # ----- US ETFs / Stocks -----
    {
        "ticker": "VOO",
        "display_name": "Vanguard S&P 500 ETF (VOO)",
        "search_terms": "S&P 500 OR VOO ETF",
        "currency": "USD",
    },
    {
        "ticker": "QQQ",
        "display_name": "Invesco QQQ Trust / Nasdaq-100 (QQQ)",
        "search_terms": "Nasdaq 100 OR QQQ ETF OR tech stocks",
        "currency": "USD",
    },
    # ----- Indian index funds (tracked via underlying indexes) -----
    {
        "ticker": "NIFTYMIDCAP150.NS",
        "display_name": "Motilal Oswal Nifty Midcap 150 (via Nifty Midcap 150 index)",
        "search_terms": "Nifty Midcap 150 OR Indian midcap stocks",
        "currency": "INR",
    },
    {
        "ticker": "NIFTYSMLCAP250.NS",
        "display_name": "Nippon India Nifty Smallcap 250 (via Nifty Smallcap 250 index)",
        "search_terms": "Nifty Smallcap 250 OR Indian smallcap stocks",
        "currency": "INR",
    },
]

# Alert threshold — flag any holding that falls by this % or more
DROP_ALERT_THRESHOLD = -2.0  # percent

# News articles to fetch per holding
NEWS_ITEMS_PER_HOLDING = 4

# Claude model
CLAUDE_MODEL = "claude-sonnet-4-5"

# Telegram message size limit (Telegram max is 4096; leave headroom)
TELEGRAM_MAX_LEN = 4000


# ============================================================================
# Secrets (set in GitHub Actions, not in this file)
# ============================================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

for name, val in [
    ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
    ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
    ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
]:
    if not val:
        print(f"ERROR: Missing environment variable: {name}", file=sys.stderr)
        sys.exit(1)


# ============================================================================
# Price fetching (Yahoo Finance via yfinance)
# ============================================================================

def fetch_price_data(ticker):
    """Fetch previous close, current price, and % change for a ticker."""
    try:
        t = yf.Ticker(ticker)
        # Pull 7 days to be safe across weekends/holidays
        hist = t.history(period="7d")
        if len(hist) < 2:
            print(f"  Not enough history for {ticker}", file=sys.stderr)
            return None

        latest = hist.iloc[-1]
        previous = hist.iloc[-2]

        latest_close = float(latest["Close"])
        prev_close = float(previous["Close"])
        change_pct = ((latest_close - prev_close) / prev_close) * 100

        return {
            "latest_close": latest_close,
            "previous_close": prev_close,
            "change_pct": round(change_pct, 2),
            "latest_date": latest.name.strftime("%Y-%m-%d"),
            "day_high": float(latest.get("High", latest_close)),
            "day_low": float(latest.get("Low", latest_close)),
        }
    except Exception as e:
        print(f"  yfinance failed for {ticker}: {e}", file=sys.stderr)
        return None


def fetch_all_prices():
    """Fetch price data for every item in the portfolio."""
    print("Fetching price data...")
    results = []
    for item in PORTFOLIO:
        print(f"  {item['ticker']} ({item['display_name']})")
        price = fetch_price_data(item["ticker"])
        results.append({"config": item, "price": price})
        time.sleep(0.3)
    return results


# ============================================================================
# News fetching (targeted per holding)
# ============================================================================

def fetch_news_for_holding(search_terms, currency, limit=NEWS_ITEMS_PER_HOLDING):
    """Fetch targeted news via Google News RSS."""
    # Bias regional results: INR → India edition, USD → US edition
    if currency == "INR":
        region_params = "hl=en-IN&gl=IN&ceid=IN:en"
    else:
        region_params = "hl=en-US&gl=US&ceid=US:en"

    query = quote_plus(f"{search_terms} when:1d")
    url = f"https://news.google.com/rss/search?q={query}&{region_params}"

    try:
        parsed = feedparser.parse(url)
        items = []
        for entry in parsed.entries[:limit]:
            items.append({
                "title": entry.get("title", "").strip(),
                "source": (
                    entry.get("source", {}).get("title", "Unknown")
                    if isinstance(entry.get("source"), dict)
                    else "Unknown"
                ),
            })
        return items
    except Exception as e:
        print(f"  News fetch failed for '{search_terms}': {e}", file=sys.stderr)
        return []


def fetch_all_news(holdings):
    """For each holding, fetch its specific news."""
    print("Fetching targeted news...")
    for h in holdings:
        cfg = h["config"]
        print(f"  News for: {cfg['search_terms']}")
        h["news"] = fetch_news_for_holding(cfg["search_terms"], cfg["currency"])
        time.sleep(0.5)
    return holdings


# ============================================================================
# Claude summarization
# ============================================================================

def format_data_for_prompt(holdings):
    """Format price + news data into a string Claude can work with."""
    sections = []
    for h in holdings:
        cfg = h["config"]
        price = h.get("price")
        news = h.get("news", [])
        currency_symbol = "₹" if cfg["currency"] == "INR" else "$"

        section = [f"### {cfg['display_name']}"]

        if price:
            section.append(
                f"Latest close: {currency_symbol}{price['latest_close']:,.2f} (on {price['latest_date']})\n"
                f"Previous close: {currency_symbol}{price['previous_close']:,.2f}\n"
                f"Change: {price['change_pct']:+.2f}%\n"
                f"Day range: {currency_symbol}{price['day_low']:,.2f} – {currency_symbol}{price['day_high']:,.2f}"
            )
            if price["change_pct"] <= DROP_ALERT_THRESHOLD:
                section.append(
                    f"⚠️ ALERT: Drop of {price['change_pct']:.2f}% "
                    f"exceeds {DROP_ALERT_THRESHOLD}% threshold"
                )
        else:
            section.append("Price data unavailable")

        if news:
            section.append("Recent news:")
            for n in news:
                section.append(f"  - {n['title']} ({n['source']})")
        else:
            section.append("No targeted news found")

        sections.append("\n".join(section))

    return "\n\n".join(sections)


def build_prompt(holdings):
    today_str = datetime.utcnow().strftime("%A, %B %d, %Y")
    data_block = format_data_for_prompt(holdings)

    return f"""You are producing a focused daily portfolio brief. Today is {today_str}.

Below is data for the user's specific holdings: previous close, latest close, % change, and targeted news. The user is investing for the long term (20-25 years), partly on behalf of their father. They want to know what moved their holdings yesterday and whether anything is worth attention today.

OUTPUT FORMAT (plain text, no markdown symbols like ** or ## — this goes to Telegram):

DAILY PORTFOLIO BRIEF — {today_str}

📊 YOUR HOLDINGS
[For each holding: one line with name, latest close, and % change. Use ⬇️ for drops over 1%, ⬆️ for rises over 1%, ➡️ for moves under 1%. Be specific with numbers. Group US first, then India.]

📰 WHAT MOVED THEM
[2-3 short paragraphs explaining the news / market context behind the biggest moves. Reference the news headlines provided. If a holding moved but no news explains it, say so honestly. Cover both US and Indian moves.]

🌐 INDEX/SECTOR CONTEXT
[1-2 sentences on broader market context for US (S&P 500, Nasdaq) and India (Nifty 50, Sensex) movements yesterday.]

🚨 ALERTS
[List any holdings that triggered the -2% drop threshold. If none, say "No holdings hit the -2% alert threshold today." Be explicit.]

👀 WHAT TO WATCH
[2-3 specific things to monitor today that could affect these holdings — earnings, economic data, central bank events, sector news. Be specific.]

RULES:
- Total length: 500-800 words
- Plain text only, no markdown
- Be honest when data is sparse — don't pad
- Do not give buy/sell recommendations
- Be neutral and factual

DATA:
{data_block}
"""


def summarize_with_claude(holdings):
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = build_prompt(holdings)

    print(f"Calling Claude ({CLAUDE_MODEL})...")
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(
        block.text for block in message.content if block.type == "text"
    )
    return text.strip()


# ============================================================================
# Telegram delivery
# ============================================================================

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > TELEGRAM_MAX_LEN:
            if current.strip():
                chunks.append(current.strip())
            current = paragraph
        else:
            current = current + "\n\n" + paragraph if current else paragraph
    if current.strip():
        chunks.append(current.strip())

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        print(f"Sending Telegram message {i+1}/{len(chunks)}...")
        resp = requests.post(url, json=payload, timeout=30)
        if not resp.ok:
            print(f"Telegram error: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)
        time.sleep(1)


# ============================================================================
# Main
# ============================================================================

def main():
    print(f"=== Focused Daily Brief — {datetime.utcnow().isoformat()} UTC ===")
    print(f"Tracking {len(PORTFOLIO)} holdings")

    holdings = fetch_all_prices()
    holdings = fetch_all_news(holdings)

    brief = summarize_with_claude(holdings)
    send_telegram(brief)

    print("Done.")


if __name__ == "__main__":
    main()
