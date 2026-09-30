# ==============================================================================
# TREND TARGETS PRO — MANDALORIAN WARRIOR EDITION (PRODUCTION MODE)
# ==============================================================================
# Description: Live Continuous Scanner & Notification Engine for TradingView Setups
# Theme: Mandalorian / Warrior Creed
# Core Rule: "This is the way." in every alert message.
#
# FIX LOG (this version):
#   - Session filter now keys off the CANDLE's own timestamp instead of the
#     wall-clock time the script happens to execute. GitHub Actions cron
#     schedules are best-effort and can be delayed by several minutes, so a
#     signal that fires right at a session boundary (e.g. 07:45 CAT close of
#     the Asian session) could previously be evaluated a few minutes late,
#     fail the "in session" check, and be lost forever (flip detection only
#     compared the very last two bars). This was the root cause of the
#     missed XAUUSD Asian-session alert.
#   - Flip detection now scans a small lookback window of recent closed bars
#     (not just the latest one) and tracks the last flip we've already acted
#     on per symbol, so a delayed or occasionally-skipped Action run doesn't
#     silently drop a setup.
#   - GER40 is now restricted to the ASIAN session only (any GER40 flip on
#     any other session on the 15m is ignored), per request.
#
# FIX LOG (round 2 — after XAU Asian-session alert was STILL missed,
# with zero notification on Discord AND Telegram, which rules out a
# dispatch-side problem like a bad chat ID or blocked bot):
#   - Tried switching XAUUSD from GC=F to XAUUSD=X as a hypothesis about
#     futures data gaps. CONFIRMED WRONG by a live run: XAUUSD=X returns
#     HTTP 404, it isn't a real Yahoo symbol at all. Yahoo has no true
#     spot-gold cross — gold is only GC=F (futures) or GLD (US-hours ETF).
#     Reverted to GC=F. Its daily CME maintenance halt (~17:00-18:00 ET)
#     falls around 23:00-00:00 CAT, outside the 02:00-07:45 Asian window,
#     so it isn't expected to gap during the hours that matter here.
#   - FLIP_LOOKBACK_BARS increased from 4 to 8 (2 hours) for extra margin
#     against Actions scheduling delays.
#   - Verbose per-symbol logging added throughout run_scanner(): bar count,
#     latest bar timestamp (raw + converted to CAT), session check result,
#     flip search result, and — if a flip was found — each filter's
#     pass/fail. This prints to the GitHub Actions run log so a future
#     "why didn't I get notified" question has an actual answer instead of
#     another guess. send_notification() now also logs the HTTP status
#     code from Discord/Telegram so a silent rejection (bad token, blocked
#     bot, rate limit) shows up too.
#
# FIX LOG (round 3 — XAUUSD still missed a genuine Asian-session MEDIUM
# setup that showed on the TradingView chart. Two separate problems found):
#   1. The probability filter required ALL THREE scoring criteria (HTF AND
#      ADX AND Body) before alerting — mathematically only Pine's HIGH tier
#      (3/3). Every true MEDIUM setup (2/3, like this one) was silently
#      dropped regardless of session/data issues. Rewritten to score 0-3
#      and alert on MEDIUM (2/3) or HIGH (3/3), matching the Pine logic,
#      with consolidation (ADX<15) still forcing LOW regardless of score.
#   2. GC=F never produced a flip at all during this setup — a real
#      futures-vs-spot data divergence, not a filter issue. Tried PAXG-USD
#      (crypto gold proxy) as a free fix; switched again after confirming
#      the user's chart is actually OANDA:XAUUSD, which needs a genuine
#      spot/forex-style feed to match closely. OANDA's own v20 API was the
#      obvious next choice but turned out to be inaccessible — the user's
#      region was routed to "OANDA Global Markets", an MT4/MT5-only entity
#      with no fxTrade/API access; not fixable without a different
#      residency, which isn't something to work around. Landed on Twelve
#      Data's free tier instead: a genuine XAU/USD spot-style instrument,
#      no country gating, "Free Forever" (800 credits/day, 8/minute,
#      resets daily — not a trial). XAUUSD now pulls from Twelve Data;
#      BTCUSD/NDX/GER40 remain on yfinance, which has had no reported
#      issues. The 1h HTF-EMA series is cached and only refetched once an
#      hour (it can't change faster than that anyway) to keep daily credit
#      usage around ~310/day against the 800 cap, even scanning every 5min.
#
# FIX LOG (round 4 — trading plan restructure, per user):
#   - Sessions redefined entirely: BTCUSD now trades the NY/London overlap
#     (15:30-17:15 CAT) on the 5m timeframe instead of 15m. NDX now trades
#     the London session (09:30-17:15 CAT), still 15m. XAUUSD unchanged
#     (Asian session, 15m). GER40 removed — trading 3 pairs now.
#   - BTCUSD switched from yfinance to Coinbase's public Exchange API
#     (free, no key needed) to match the user's actual chart source.
#     NDX's chart source is CME:NQ1! (continuous front-month Nasdaq
#     future) — the same instrument family as yfinance's NQ=F, so no
#     change was needed there.
#   - Each symbol now carries its own "interval" in SYMBOLS instead of one
#     global 15m for everything. The flip-detection lookback window used to
#     be a fixed bar count (8 bars = 2h at 15m); it's now defined in MINUTES
#     (FLIP_LOOKBACK_MINUTES) and converted to a bar count per symbol, so a
#     5m symbol still gets ~2h of safety margin against scheduling gaps
#     instead of only 40 minutes (8 bars x 5m).
#   - CRITICAL BUG CAUGHT BEFORE SHIPPING: an earlier pass at this rewrite
#     left the code half-migrated — it referenced a session-check branch
#     for "LONDON"/"NY_LONDON_OVERLAP" that was never actually added to
#     is_time_in_session() (so those symbols would have silently never
#     fired), left GER40 in SYMBOLS, left BTCUSD on yfinance despite the
#     comment saying otherwise, and referenced a FLIP_LOOKBACK_BARS
#     constant that no longer existed — a NameError that would have
#     crashed the script immediately on every single run. Caught by
#     actually running `python3 script.py` locally before calling this
#     done, not just a syntax-level compile check. All of the above is
#     fixed in this version; is_time_in_session() now uses a proper
#     SESSION_WINDOWS table instead of scattered if/elif branches so this
#     class of drift is harder to reintroduce.
# FIX LOG (round 5 — trading plan restructure #2, per user):
#   - BTCUSD eliminated entirely (same treatment as GER40 earlier) — its
#     dedicated Coinbase fetch code is removed too, not left dormant.
#   - XAUUSD: Asian window end time moved 07:45 -> 07:55 CAT. Timeframe
#     moved 15m -> 5m.
#   - NDX: session moved from LONDON to a new NEW_YORK window, 15:30-21:55
#     CAT. Timeframe moved 15m -> 5m.
#   - Alerts now fire on HIGH probability only — MEDIUM setups are still
#     scored and logged (visible in the run log) but no longer alert or
#     open a trade. The invalidation rule is unaffected: an active trade
#     is still invalidated by ANY new opposing flip regardless of that
#     flip's own tier, exactly as before — this only changes which flips
#     are allowed to open a NEW trade in the first place.
# ==============================================================================

import os
import json
import math
import time
import random
import requests
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import yfinance as yf

# ==============================================================================
# PRODUCTION MODE CONFIGURATION
# ==============================================================================
# TEST_MODE is permanently False -> Strict 5m Timeframe, High probability setups only.
TEST_MODE = False

# Webhooks, bot tokens, and API keys — read from environment variables
# (populated by GitHub Actions Secrets, see main.yml) rather than hardcoded,
# so the repo is safe to make public. Locally, export these yourself before
# running, e.g.: export DISCORD_WEBHOOK_URL="..." (etc for the other three).
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

for _name, _val in [("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL),
                     ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
                     ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
                     ("TWELVE_DATA_API_KEY", TWELVE_DATA_API_KEY)]:
    if not _val:
        print(f"[CONFIG] WARNING: {_name} is empty — check it's set as a "
              f"GitHub Actions secret AND passed through in main.yml's env block.")

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
HTF_CACHE_FILE = "xauusd_htf_cache.json"  # caches the 1h series for up to an hour

STATE_FILE = "active_trades.json"
ZAMBIA_TZ = pytz.timezone("Africa/Lusaka")

# How much time to scan back for a flip we haven't acted on yet, regardless
# of a symbol's candle size. This is what protects you from a delayed/
# skipped GitHub Actions run. Converted to a per-symbol bar count below
# since different symbols now run different timeframes.
FLIP_LOOKBACK_MINUTES = 120

def interval_minutes(interval_str):
    """'5m' -> 5, '15m' -> 15."""
    return int(interval_str.rstrip("m"))

def lookback_bars_for(interval_str):
    """How many bars of `interval_str` fit in FLIP_LOOKBACK_MINUTES, floor 4."""
    return max(4, round(FLIP_LOOKBACK_MINUTES / interval_minutes(interval_str)))

def to_twelvedata_interval(interval_str):
    """'5m' -> '5min', '15m' -> '15min' (Twelve Data's own interval format)."""
    return f"{interval_minutes(interval_str)}min"

# Symbol mapping. Each entry: ticker/instrument symbol, trading session,
# candle timeframe, and which data source to pull from.
#   NDX:    New York session (15:30-21:55 CAT), 5m — chart source CME:NQ1!,
#           the continuous front-month Nasdaq future. yfinance's NQ=F is
#           the same instrument family, so it stays as-is.
#   XAUUSD: Asian session (02:00-07:55 CAT), 5m — unchanged source, still
#           Twelve Data (see FIX LOG round 3).
#   BTCUSD and GER40 both removed per request — trading 2 pairs now.
SYMBOLS = {
    "NDX":    {"ticker": "NQ=F",    "session": "NEW_YORK", "interval": "5m", "source": "yfinance"},
    "XAUUSD": {"ticker": "XAU/USD", "session": "ASIAN",    "interval": "5m", "source": "twelvedata"},
}

# ==============================================================================
# MANDALORIAN MESSAGES
# ==============================================================================

TP1_MESSAGES = [
    "Target 1 vanquished! 🎯 Partials stored in the foundry and armor reinforced at Break Even. This is the way.",
    "First blow struck with precision! ⚔️ TP1 claimed, risk eliminated. Move SL to Break Even. This is the way.",
    "The clan claims its first bounty! 💰 TP1 hit, SL moved to entry. We fight risk-free now. This is the way.",
    "BAM! TP1 struck like a Mandalorian spear! 🚀 Move SL to Break Even and let the rest run. This is the way.",
    "Beskar-grade execution! 🎯 TP1 achieved. SL adjusted to Break Even. Free trade activated. This is the way."
]

TP2_MESSAGES = [
    "FULL CONQUEST ACHIEVED! 🚀🔥 1:2 R/R completely liquidated! Maximum bounty claimed! This is the way.",
    "VICTORY IN THE ARENA! 💰 TP2 hit! Full target reached with absolute warrior perfection! This is the way.",
    "MAXIMUM REWARD UNLOCKED! 🎯 TP2 crushed! Time to count the spoils of war! This is the way.",
    "TRIUMPH FOR THE CLAN! 🏆 Full TP2 hit! Absolute masterclass from the Creed! This is the way."
]

SL_HIT_MESSAGES = [
    "A honorable scratch on our Beskar! 🛑 SL hit, but risk was tightly controlled. On to the next battle! This is the way.",
    "SL taken out, but our spirits stand tall! 🛡️ A loss is just the cost of war. The code remains intact! This is the way.",
    "SL hit! 📉 No fear, no hesitation — disciplined risk management keeps us strong for the big wins! This is the way."
]

BE_HIT_MESSAGES = [
    "Impenetrable defense! 🛡️ Break-Even hit with zero loss, capital completely safe! We took a free strike at the market! This is the way.",
    "SL at BE triggered! 🤝 No blood spilled, rules followed 100%. That is warrior discipline! This is the way.",
    "Break-Even exit! 🛡️ TP1 was hit, partials banked, and the rest exited at $0 cost! This is the way."
]

INVALIDATED_MESSAGES = [
    "The winds of battle have shifted! 🔄 A new setup overrides the old — no TP, no SL, just a tactical stand-down before the new charge. This is the way.",
    "Creed calls for adaptation! 🛡️ The previous setup is invalidated by a fresh signal in the other direction. Better to regroup than fight a battle already lost. This is the way.",
    "New orders from the Foundry! ⚔️ The old position stands down, untouched by TP or SL — a sharper blade has been drawn. This is the way."
]

# ==============================================================================
# SESSION FILTERING (Africa/Lusaka = CAT, UTC+2 year-round, no DST)
# ==============================================================================
# (start_minute, end_minute) since midnight CAT, inclusive.
SESSION_WINDOWS = {
    "ASIAN":    (2 * 60,        7 * 60 + 55),   # 02:00 - 07:55 CAT — XAUUSD
    "NEW_YORK": (15 * 60 + 30, 21 * 60 + 55),   # 15:30 - 21:55 CAT — NDX
}

def to_cat(ts: pd.Timestamp) -> pd.Timestamp:
    """
    Convert a pandas Timestamp (tz-aware in whatever timezone the source API
    returned it in, or tz-naive) into Africa/Lusaka time. Data sources don't
    consistently return the same source timezone — tz_convert handles it
    correctly regardless of what it started as. Zambia has no DST, so CAT is
    always a fixed UTC+2 — this conversion is exact year-round.
    """
    if ts.tzinfo is None:
        ts = ts.tz_localize('UTC')
    return ts.tz_convert(ZAMBIA_TZ)


def is_time_in_session(cat_dt, session_type):
    """Checks whether a given Africa/Lusaka datetime falls within a named session window."""
    window = SESSION_WINDOWS.get(session_type)
    if window is None:
        return False
    start_min, end_min = window
    time_min = cat_dt.hour * 60 + cat_dt.minute
    return start_min <= time_min <= end_min


def is_bar_in_session(bar_timestamp, session_type):
    """
    Session check anchored to the CANDLE's own close time, not to the
    wall-clock time the script happens to execute. This is what makes the
    filter immune to GitHub Actions scheduling delays/jitter.
    """
    return is_time_in_session(to_cat(bar_timestamp), session_type)

# ==============================================================================
# TWELVE DATA (XAUUSD only — see FIX LOG round 3)
# ==============================================================================
def fetch_twelvedata_series(symbol, interval, outputsize=300):
    """
    Fetch a time series from Twelve Data and return it shaped exactly like
    yfinance's output: a DataFrame with a UTC-aware DatetimeIndex, columns
    Open/High/Low/Close, sorted oldest-to-newest — so calculate_indicators()
    and everything downstream needs no special-casing.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "timezone": "UTC",
        "order": "ASC",
        "apikey": TWELVE_DATA_API_KEY,
    }
    resp = requests.get(f"{TWELVE_DATA_BASE_URL}/time_series", params=params, timeout=20)
    data = resp.json()

    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(f"Twelve Data error for {symbol} ({interval}): {data}")

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].astype(float)
    return df[["Open", "High", "Low", "Close"]]


def load_htf_cache():
    if os.path.exists(HTF_CACHE_FILE):
        try:
            with open(HTF_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_htf_cache(cache):
    with open(HTF_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def get_xauusd_htf_df():
    """
    Returns the 1h OHLC DataFrame for XAU/USD, refetched from Twelve Data
    at most once per hour and cached to disk in between. 1h candles can't
    meaningfully change more than once an hour anyway, so re-fetching every
    5-minute scan would just burn API credits for identical data — this
    keeps daily usage around ~310 credits against the 800/day free cap.
    """
    cache = load_htf_cache()
    now_utc = datetime.now(pytz.UTC)
    cached_time = cache.get("fetched_at")

    needs_refresh = cached_time is None
    if not needs_refresh:
        cached_dt = datetime.fromisoformat(cached_time)
        needs_refresh = (now_utc - cached_dt).total_seconds() >= 3600

    if needs_refresh:
        print("[XAUUSD] Refreshing Twelve Data 1h HTF series (cache expired/missing).")
        df_1h = fetch_twelvedata_series("XAU/USD", "1h", outputsize=200)
        cache = {
            "fetched_at": now_utc.isoformat(),
            "data": df_1h.reset_index().to_json(orient="records", date_format="iso")
        }
        save_htf_cache(cache)
    else:
        age_min = (now_utc - datetime.fromisoformat(cached_time)).total_seconds() / 60
        print(f"[XAUUSD] Using cached Twelve Data 1h HTF series (age {age_min:.0f} min).")

    records = json.loads(cache["data"])
    df_1h = pd.DataFrame(records)
    df_1h = df_1h.rename(columns={"datetime": "dt"})
    df_1h["dt"] = pd.to_datetime(df_1h["dt"], utc=True)
    df_1h = df_1h.set_index("dt").sort_index()
    return df_1h[["Open", "High", "Low", "Close"]]

# ==============================================================================
# INDICATOR ENGINE
# ==============================================================================
def calculate_indicators(df_lower, df_1h):
    df_1h['HTF_EMA'] = df_1h['Close'].ewm(span=50, adjust=False).mean()

    df_lower = pd.merge_asof(
        df_lower.sort_index(),
        df_1h[['HTF_EMA']].sort_index(),
        left_index=True,
        right_index=True,
        direction='backward'
    )

    high, low, close, open_p = df_lower['High'], df_lower['Low'], df_lower['Close'], df_lower['Open']

    # Supertrend (10, 3.0)
    tr0 = high - low
    tr1 = (high - close.shift(1)).abs()
    tr2 = (low - close.shift(1)).abs()
    tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)
    atr10 = tr.ewm(alpha=1/10, adjust=False).mean()

    hl2 = (high + low) / 2
    basic_ub = hl2 + (3.0 * atr10)
    basic_lb = hl2 - (3.0 * atr10)

    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()
    st_trend = pd.Series(1, index=df_lower.index)

    for i in range(1, len(df_lower)):
        final_ub.iloc[i] = basic_ub.iloc[i] if (basic_ub.iloc[i] < final_ub.iloc[i-1] or close.iloc[i-1] > final_ub.iloc[i-1]) else final_ub.iloc[i-1]
        final_lb.iloc[i] = basic_lb.iloc[i] if (basic_lb.iloc[i] > final_lb.iloc[i-1] or close.iloc[i-1] < final_lb.iloc[i-1]) else final_lb.iloc[i-1]

        if st_trend.iloc[i-1] == 1:
            st_trend.iloc[i] = -1 if close.iloc[i] < final_lb.iloc[i] else 1
        else:
            st_trend.iloc[i] = 1 if close.iloc[i] > final_ub.iloc[i] else -1

    df_lower['ST_Trend'] = st_trend

    # ADX (14)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df_lower.index).ewm(alpha=1/14, adjust=False).mean() / atr14)
    minus_di = 100 * (pd.Series(minus_dm, index=df_lower.index).ewm(alpha=1/14, adjust=False).mean() / atr14)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df_lower['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()

    # Candle Body Ratio
    df_lower['BodyRatio'] = (close - open_p).abs() / np.maximum(high - low, 0.0001)

    return df_lower


def find_recent_flip(df, lookback):
    """
    Scan the last `lookback` closed bars (instead of only the very last one)
    for a Supertrend flip. Returns (flip_index, direction, flip_timestamp)
    for the MOST RECENT flip found in the window, or (None, None, None).

    Scanning a window instead of just the last bar is what protects a signal
    from being lost if a scheduled run is delayed or occasionally skipped —
    the flip is still visible a bar or two later.
    """
    trend = df['ST_Trend']
    n = len(trend)
    start = max(1, n - lookback)
    for i in range(n - 1, start - 1, -1):
        if trend.iloc[i] == 1 and trend.iloc[i - 1] == -1:
            return i, "BUY", df.index[i]
        elif trend.iloc[i] == -1 and trend.iloc[i - 1] == 1:
            return i, "SELL", df.index[i]
    return None, None, None

# ==============================================================================
# DISPATCH MESSAGES
# ==============================================================================
def send_notification(title, message_body, color_code=3447003):
    if DISCORD_WEBHOOK_URL:
        payload = {
            "content": "@everyone",
            "embeds": [{
                "title": title,
                "description": message_body,
                "color": color_code,
                "footer": {"text": "Trend Targets Pro • Mandalorian Warrior Creed"}
            }]
        }
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            print(f"[DISPATCH] Discord status={r.status_code}")
            if r.status_code >= 300:
                print(f"[DISPATCH] Discord response body: {r.text[:300]}")
        except Exception as e:
            print(f"[DISPATCH] Discord dispatch error: {e}")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        full_msg = f"*{title}*\n\n{message_body}\n\n_Trend Targets Pro • Warrior Creed_"
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": full_msg, "parse_mode": "Markdown"},
                timeout=5
            )
            print(f"[DISPATCH] Telegram status={r.status_code}")
            if r.status_code >= 300:
                print(f"[DISPATCH] Telegram response body: {r.text[:300]}")
        except Exception as e:
            print(f"[DISPATCH] Telegram dispatch error: {e}")

# ==============================================================================
# STATE MANAGEMENT
# ==============================================================================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_last_flip_seen(state, name):
    return state.get("_meta", {}).get(name)


def set_last_flip_seen(state, name, flip_timestamp_iso):
    state.setdefault("_meta", {})[name] = flip_timestamp_iso

# ==============================================================================
# MAIN SCANNER ROUTINE
# ==============================================================================
def run_scanner():
    state = load_state()

    tf_period = "5d"  # yfinance lookback window (NDX only, now the sole yfinance symbol)

    run_started_cat = datetime.now(ZAMBIA_TZ)
    print(f"\n===== SCAN START — {run_started_cat.strftime('%Y-%m-%d %H:%M:%S %Z')} =====")

    for name, cfg in SYMBOLS.items():
        ticker, session_type, source, interval = cfg["ticker"], cfg["session"], cfg["source"], cfg["interval"]
        lookback_bars = lookback_bars_for(interval)
        print(f"\n--- {name} ({ticker}, session={session_type}, source={source}, interval={interval}) ---")

        try:
            if source == "yfinance":
                df_lower = yf.download(tickers=ticker, period=tf_period, interval=interval, progress=False)
                df_1h = yf.download(tickers=ticker, period="10d", interval="1h", progress=False)
                if isinstance(df_lower.columns, pd.MultiIndex):
                    df_lower.columns = df_lower.columns.get_level_values(0)
                if isinstance(df_1h.columns, pd.MultiIndex):
                    df_1h.columns = df_1h.columns.get_level_values(0)
            elif source == "twelvedata":
                df_lower = fetch_twelvedata_series(ticker, to_twelvedata_interval(interval), outputsize=300)
                df_1h = get_xauusd_htf_df()
            else:
                print(f"[{name}] SKIPPED — unknown data source '{source}'")
                continue
        except Exception as e:
            print(f"[{name}] Download error: {e}")
            continue

        if df_lower.empty or len(df_lower) < 50 or df_1h.empty:
            print(f"[{name}] SKIPPED — insufficient data "
                  f"(15m bars: {len(df_lower)}, 1h bars: {len(df_1h)})")
            continue

        df = calculate_indicators(df_lower, df_1h)

        latest_bar_time = df.index[-1]
        latest_bar_cat = to_cat(latest_bar_time)
        print(f"[{name}] {len(df)} bars loaded | latest bar: {latest_bar_time} "
              f"(raw) -> {latest_bar_cat.strftime('%Y-%m-%d %H:%M %Z')} (CAT) | "
              f"in_session_now={is_time_in_session(latest_bar_cat, session_type)}")

        latest_bar = df.iloc[-1]
        high_p  = float(latest_bar['High'])
        low_p   = float(latest_bar['Low'])

        # ----------------------------------------------------------------------
        # 1. MANAGE THE ACTIVE TRADE, IF ANY (always runs, regardless of
        #    session — you never want to miss closing/managing a live trade).
        #    Completion rules: before TP1 hits, exit is only at the original
        #    SL. After TP1 hits, SL moves to break-even and exit is either
        #    BE or TP2. Invalidation-by-opposing-flip is handled separately
        #    in section 2, since it can happen regardless of session/tier.
        # ----------------------------------------------------------------------
        if name in state:
            trade = state[name]
            direction = trade['direction']
            entry = trade['entry']
            sl    = trade['sl']
            tp1   = trade['tp1']
            tp2   = trade['tp2']
            print(f"[{name}] Active {direction} trade found — entry={entry:.2f} sl={sl:.2f} "
                  f"tp1={tp1:.2f} tp2={tp2:.2f} tp1_hit={trade['tp1_hit']}")

            if direction == "BUY":
                if not trade['tp1_hit'] and high_p >= tp1:
                    trade['tp1_hit'] = True
                    trade['sl_moved_to_be'] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name} ({interval})",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                elif trade['tp1_hit'] and high_p >= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} ({interval})",
                        f"{random.choice(TP2_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP2 (1:2):* `{tp2:.2f}`",
                        color_code=65280
                    )
                    del state[name]
                    save_state(state)
                    continue

                elif low_p <= (entry if trade['sl_moved_to_be'] else sl):
                    if trade['sl_moved_to_be']:
                        send_notification(
                            f"🛡️ BREAK EVEN HIT — {name}",
                            f"{random.choice(BE_HIT_MESSAGES)}\n\n• *Entry/BE Level:* `{entry:.2f}`",
                            color_code=1752220
                        )
                    else:
                        send_notification(
                            f"🛑 STOP LOSS HIT — {name}",
                            f"{random.choice(SL_HIT_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *SL:* `{sl:.2f}`",
                            color_code=15548997
                        )
                    del state[name]
                    save_state(state)
                    continue

            elif direction == "SELL":
                if not trade['tp1_hit'] and low_p <= tp1:
                    trade['tp1_hit'] = True
                    trade['sl_moved_to_be'] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name} ({interval})",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                elif trade['tp1_hit'] and low_p <= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} ({interval})",
                        f"{random.choice(TP2_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP2 (1:2):* `{tp2:.2f}`",
                        color_code=65280
                    )
                    del state[name]
                    save_state(state)
                    continue

                elif high_p >= (entry if trade['sl_moved_to_be'] else sl):
                    if trade['sl_moved_to_be']:
                        send_notification(
                            f"🛡️ BREAK EVEN HIT — {name}",
                            f"{random.choice(BE_HIT_MESSAGES)}\n\n• *Entry/BE Level:* `{entry:.2f}`",
                            color_code=1752220
                        )
                    else:
                        send_notification(
                            f"🛑 STOP LOSS HIT — {name}",
                            f"{random.choice(SL_HIT_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *SL:* `{sl:.2f}`",
                            color_code=15548997
                        )
                    del state[name]
                    save_state(state)
                    continue

        # ----------------------------------------------------------------------
        # 2. LOOK FOR A NEW, UNPROCESSED FLIP.
        #    Invalidation rule: ANY new opposing flip invalidates an active
        #    trade that hasn't hit SL/BE/TP2 yet — regardless of the new
        #    flip's own tier or session status. That's a separate question
        #    from whether the new flip ALSO qualifies for its own trade
        #    (session + HIGH tier only, as of round 5). Both can be true at once: you get the
        #    "close manually" warning for the old one AND the new-setup
        #    alert for the new one. If the old trade already closed
        #    naturally (SL/BE/TP2, handled in section 1 above and no longer
        #    in `state`), there's nothing to invalidate — no manual-close
        #    message is sent.
        # ----------------------------------------------------------------------
        flip_idx, direction, flip_time = find_recent_flip(df, lookback=lookback_bars)
        if flip_idx is None:
            print(f"[{name}] No Supertrend flip in the last {lookback_bars} bars.")
            continue

        flip_time_cat = to_cat(flip_time)
        flip_time_iso = flip_time.isoformat()
        print(f"[{name}] Flip found: {direction} at {flip_time} (raw) -> "
              f"{flip_time_cat.strftime('%Y-%m-%d %H:%M %Z')} (CAT)")

        if get_last_flip_seen(state, name) == flip_time_iso:
            # We've already evaluated this exact flip bar (pass or fail) — don't redo it.
            print(f"[{name}] Flip already evaluated on a prior run — skipping.")
            continue

        # Mark this flip as seen regardless of outcome below, so we never
        # re-evaluate the same bar again.
        set_last_flip_seen(state, name, flip_time_iso)
        save_state(state)

        # --- INVALIDATION: unconditional on any new opposing flip ---
        if name in state:
            old = state[name]
            print(f"[{name}] New {direction} flip found while a {old['direction']} trade was "
                  f"still open (no TP/SL/BE hit yet) — invalidating, manual close required.")
            send_notification(
                f"⚠️ CLOSE MANUALLY — {name}",
                f"{random.choice(INVALIDATED_MESSAGES)}\n\n"
                f"• *Old {old['direction']} Entry:* `{old['entry']:.2f}`\n"
                f"• *SL:* `{old['sl']:.2f}` | *TP1:* `{old['tp1']:.2f}` | *TP2:* `{old['tp2']:.2f}`\n"
                f"• *Reason:* opposing setup detected on {name} — no TP, SL or BE was hit, close this position manually.",
                color_code=15105570
            )
            del state[name]
            save_state(state)

        # --- Does THIS flip independently qualify for its own trade? ---
        in_session = is_bar_in_session(flip_time, session_type)
        print(f"[{name}] Flip in {session_type} session? {in_session}")
        if not in_session:
            continue

        flip_bar = df.iloc[flip_idx]
        flip_close = float(flip_bar['Close'])
        htf_ema = float(flip_bar['HTF_EMA'])
        adx_val = float(flip_bar['ADX'])
        body_ratio = float(flip_bar['BodyRatio'])

        buy_flip_here = direction == "BUY"

        # Score each of the 3 criteria exactly like the Pine indicator does
        # (HTF agreement, ADX strength, body strength), then classify as
        # HIGH (3/3), MEDIUM (2/3), or LOW (0-1/3, or forced LOW if the
        # market is consolidating regardless of score). Only HIGH now gets
        # a new-trade alert (round 5: tightened from Medium+High to High
        # only) — MEDIUM/LOW are still scored and logged for visibility,
        # just no longer alerted or opened. This tier check has no bearing
        # on the invalidation above, which already happened unconditionally
        # if applicable, regardless of this flip's tier.
        is_htf_aligned    = (flip_close > htf_ema) if buy_flip_here else (flip_close < htf_ema)
        is_adx_strong     = adx_val >= 20.0
        is_body_strong    = body_ratio >= 0.40
        is_consolidating  = adx_val < 15.0

        score = int(is_htf_aligned) + int(is_adx_strong) + int(is_body_strong)
        if is_consolidating:
            tier = "LOW"
        elif score == 3:
            tier = "HIGH"
        elif score == 2:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        print(f"[{name}] Score {score}/3 — HTF aligned: {is_htf_aligned} "
              f"(close={flip_close:.2f} vs HTF EMA={htf_ema:.2f}) | "
              f"ADX>=20: {is_adx_strong} (ADX={adx_val:.1f}) | "
              f"Body>=0.40: {is_body_strong} (body={body_ratio:.2f}) | "
              f"Consolidating (ADX<15): {is_consolidating} -> tier={tier}")

        if tier != "HIGH":
            print(f"[{name}] Flip is {tier} probability — no new-trade alert sent (HIGH only).")
            continue

        print(f"[{name}] Flip is HIGH probability — dispatching new-trade alert.")

        tier_txt = "HIGH PROBABILITY SETUP ⭐⭐⭐"

        sl_lookback_start = max(0, flip_idx - 5)
        sl_lookback_df = df.iloc[sl_lookback_start:flip_idx]
        sl_px = float(sl_lookback_df['Low'].min()) if buy_flip_here else float(sl_lookback_df['High'].max())

        risk = abs(flip_close - sl_px)
        if risk == 0:
            risk = flip_close * 0.001

        tp1_px = flip_close + risk if buy_flip_here else flip_close - risk
        tp2_px = flip_close + (risk * 2.0) if buy_flip_here else flip_close - (risk * 2.0)

        state[name] = {
            "direction": direction,
            "entry": flip_close,
            "sl": sl_px,
            "tp1": tp1_px,
            "tp2": tp2_px,
            "tp1_hit": False,
            "sl_moved_to_be": False
        }
        save_state(state)

        emoji = "⚔️ 🟢" if direction == "BUY" else "⚔️ 🔴"
        color = 5763719 if direction == "BUY" else 15548997

        msg_body = (
            f"{emoji} *{direction} SIGNAL CONFIRMED on {name} ({interval})*\n"
            f"• *Tier:* `{tier_txt}`\n\n"
            f"• *Entry Price:* `{flip_close:.2f}`\n"
            f"• *Stop Loss:* `{sl_px:.2f}`\n"
            f"• *TP1 (1:1 R/R):* `{tp1_px:.2f}`\n"
            f"• *TP2 (1:2 R/R):* `{tp2_px:.2f}`\n\n"
            f"• *ADX Strength:* `{adx_val:.1f}` | *Candle Body:* `{body_ratio*100:.1f}%`\n\n"
            f"*Honor the risk rules and execute with courage. This is the way.*"
        )
        send_notification(f"🚨 TREND TARGETS PRO — {name}", msg_body, color_code=color)

# ==============================================================================
# MAIN BATCH EXECUTION
# ==============================================================================
if __name__ == "__main__":
    try:
        run_scanner()
    except Exception as e:
        print(f"Scanner Exception: {e}")