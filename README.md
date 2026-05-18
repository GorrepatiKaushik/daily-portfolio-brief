# 📊 Daily Portfolio Brief

> A personal automation that turns scattered global market noise into a focused 500-word brief — delivered to my Telegram at 6:30 AM every morning.

![Status](https://img.shields.io/badge/status-running_daily-success)
![Cost](https://img.shields.io/badge/monthly_cost-~$1.50-blue)
![Stack](https://img.shields.io/badge/stack-Python_|_Claude_API_|_GitHub_Actions-orange)
![Markets](https://img.shields.io/badge/coverage-US_+_India-brightgreen)

---

## The story behind this

We're living through a strange moment. AI is reshaping every industry. Markets are moving on tweets, geopolitical shifts, and Fed minutes that drop at 2 AM. War headlines move oil prices, which move airline stocks, which ripple into ETFs I hold. The cost of being uninformed has never been higher — and neither has the cost of being overwhelmed by information.

I was waking up every morning checking 6 different apps — Yahoo Finance, Mint, Economic Times, CNBC, Twitter, Bloomberg — trying to figure out: *what actually happened overnight that affects what I own?*

Most of what I was reading wasn't relevant to my actual portfolio. The signal-to-noise ratio was terrible. I'd spend 30-40 minutes catching up and still walk away unsure whether anything actionable had changed.

So I built this.

It tracks **my specific holdings** (not the whole market), pulls **only targeted news** mentioning them or their underlying indexes, runs the raw data through **Claude** to produce a focused brief, and drops it in my Telegram before I've even had coffee.

This project sits at the intersection of three things I'm genuinely passionate about: **AI**, **software/data engineering**, and **financial markets**. Building it forced me to combine all three.

---

## What it actually looks like

Every morning at 6:30 AM, my Telegram pings with something like this:

```
DAILY PORTFOLIO BRIEF — Tuesday, May 19, 2026

📊 YOUR HOLDINGS
US:
⬆️ VOO: $548.23 (+0.4%)
➡️ BRK.B: $452.10 (+0.1%)
⬇️ QQQ: $478.50 (-1.2%)

India:
⬆️ Nifty 50: 24,580 (+0.3%)
⬇️ Nifty Next 50: 71,240 (-1.8%)
⬇️ Nifty Midcap 150: 22,890 (-2.4%) ⚠️
⬇️ Nifty Smallcap 250: 18,470 (-1.9%)

📰 WHAT MOVED THEM
US tech sold off after the Fed minutes signaled fewer rate cuts than 
markets expected, dragging QQQ. Indian midcaps extended their correction 
on profit-booking ahead of Q4 earnings season...

🚨 ALERTS
Nifty Midcap 150 dropped 2.4% — exceeds your -2% threshold.

👀 WHAT TO WATCH
- US: PCE inflation data drops Friday
- India: RBI meeting minutes scheduled Wednesday
- Watch oil prices given Middle East tensions
```

Concise. Personalized. Actionable. **No more 30-minute morning scrolls.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           GitHub Actions (cron @ 11:30 UTC daily)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    daily_brief.py                            │
│                                                              │
│   ┌──────────────┐    ┌──────────────┐   ┌──────────────┐  │
│   │   yfinance   │    │ Google News  │   │  Anthropic   │  │
│   │  (prices)    │    │  RSS feeds   │   │  Claude API  │  │
│   │              │    │  (targeted)  │   │ (synthesis)  │  │
│   └──────┬───────┘    └──────┬───────┘   └──────┬───────┘  │
│          │                   │                   │           │
│          └───────────────────┴───────────────────┘           │
│                              │                               │
│                              ▼                               │
│                    ┌──────────────────┐                      │
│                    │  Telegram Bot    │                      │
│                    │      API         │                      │
│                    └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                       📱 My phone, 6:30 AM
```

The pipeline does four things every morning:

1. **Fetches price data** for each tracked instrument via `yfinance` — including overnight % changes and trading ranges
2. **Pulls targeted news** from Google News RSS, with queries scoped to *my specific holdings* (not generic market news)
3. **Sends structured data to Claude** with a prompt designed to surface what's actionable, flag any -2% drops, and keep the brief between 500-800 words
4. **Pushes to Telegram** via the Bot API, splitting messages if they exceed Telegram's 4096-char limit

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Runtime** | Python 3.11 | Best ecosystem for data + LLM workflows |
| **Scheduling** | GitHub Actions | Free, zero-infra, declarative cron |
| **Market data** | yfinance | Free, reliable, covers US + Indian indexes |
| **News** | Google News RSS | Free, regional bias support, no API key |
| **AI** | Anthropic Claude API | Best-in-class for structured summarization |
| **Delivery** | Telegram Bot API | Free, instant push, works on every device |
| **Secrets** | GitHub Actions Secrets | No keys in code, ever |

**Monthly cost: ~$1.50.** Everything except the Claude API is free.

---

## Key engineering decisions

A few things I had to figure out while building this — and the tradeoffs I made.

### Tracking Indian mutual funds without NAV data

**Problem:** Yahoo Finance doesn't reliably cover Indian mutual fund NAVs. Tracking ICICI Prudential Nifty Next 50 directly was a dead end.

**Solution:** Track the **underlying index** (`^CNXNXT50`) instead. Index moves match fund NAV within 0.1-0.3% tracking error and are available real-time, while NAVs publish with a 1-day lag.

**Engineering takeaway:** When the obvious data source doesn't exist, find the proxy that matters. The fund's tracking error is a feature, not a bug.

### Regional news bias

**Problem:** Generic news queries returned mostly US sources, even for Indian holdings.

**Solution:** Parameterized news queries by currency. INR holdings get the India edition of Google News (`hl=en-IN&gl=IN`); USD holdings get the US edition. Better local context.

### Prompt design for honest summarization

**Problem:** LLMs love to hedge and pad. I needed a brief, not a wall of text.

**Solution:** The Claude prompt explicitly says: *"Be honest when data is sparse — don't pad. Do not give buy/sell recommendations. If a holding moved meaningfully but no news explains it, say so."* The brief stays sharp because the system prompt resists fluff.

### Cost control

A daily brief generates ~$0.03-$0.05 in Claude API costs. Over a year, that's $11-$18. The GitHub Actions free tier handles the scheduling without any infrastructure to maintain. No servers, no Docker, no monitoring stack — just a YAML file and a Python script.

---

## What I learned

1. **The hardest part of personal automation is not the code.** It's deciding what to track and what to ignore. The signal-vs-noise problem is upstream of any tool.

2. **AI doesn't replace expertise — it scales it.** Without knowing what *should* be in a portfolio brief, no prompt would produce a useful one. Claude is great at synthesis when you know what synthesis you want.

3. **Free infrastructure has gotten absurdly good.** GitHub Actions + Telegram + Yahoo Finance + Google News RSS = a production-grade pipeline at $0/month before AI costs.

4. **Building tools for yourself first is the cheat code.** I use this every day, which is the strongest validation any side project can get.

---

## Setup

If you want to run this for your own portfolio, the setup is ~30 minutes.

**TL;DR:**
1. Create a Telegram bot via `@BotFather`
2. Get an Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
3. Fork this repo, add 3 secrets (`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
4. Edit the `PORTFOLIO` list in `daily_brief.py` with your tickers
5. Trigger the GitHub Action manually to test

---

## Customization

The `PORTFOLIO` config at the top of `daily_brief.py` is the only thing most people need to edit:

```python
PORTFOLIO = [
    {
        "ticker": "VOO",                            # Yahoo Finance ticker
        "display_name": "Vanguard S&P 500 ETF",     
        "search_terms": "S&P 500 OR VOO ETF",       # News search query
        "currency": "USD",                          # USD or INR
    },
    # add more...
]
```

Want to track crypto? Add `BTC-USD`. Want to track specific Indian stocks? Use NSE tickers with `.NS` (e.g., `RELIANCE.NS`). The pipeline is portfolio-agnostic.

---

## What's next

Things I'm thinking about:

- [ ] **Multi-recipient support** — let a friend or family member subscribe
- [ ] **Weekly summary** — Sundays, looking at the whole week + sectoral trends
- [ ] **Earnings calendar integration** — auto-flag earnings days for held companies
- [ ] **Sentiment scoring** — quantify the news tone alongside price moves
- [ ] **Web dashboard** — for visualization of historical performance + brief archive

---

## Disclaimer

This tool generates AI summaries of price and news data. The output may contain
errors, omissions, or misinterpretations. **It is not investment advice.** I do
not use it to make trades automatically — only to stay informed. For material
investment decisions, consult a licensed financial advisor.

---

## A note on what this represents

I built this in a weekend, but the thinking behind it took years.

It combines three fields I've been deepening in over time: **AI** (knowing how to design prompts that produce reliable structured output), **software engineering** (turning a one-off script into a self-running pipeline with proper secrets management and error handling), and **finance** (knowing what data and signals actually matter for long-term investing).

The world is moving fast. AI is the multiplier. Engineering is the lever. Finance is the destination. This project is a small proof that all three can be combined to make daily life — and daily decisions — meaningfully better.

If you found this useful, fork it. If you build something better, let me know — I'd love to see it.

---

*Built by [your name] · [your linkedin] · [your email]*
