# ==============================================================================
# TREND TARGETS PRO — MANDALORIAN WARRIOR EDITION (PRODUCTION MODE)
# ==============================================================================
# Mirrors "Trend Targets Pro - Probability [ZedSauce FA]" (Pine v6):
#   Supertrend(10, 3.0) · ADX(14) · HTF EMA(50) on 1h · body ratio 0.50 ·
#   consolidating (ADX<15) forces LOW · tier 3=HIGH, 2=MEDIUM, else LOW ·
#   SL = 3-bar swing before signal · TP1=1R · TP2=2R.
#
# Round 8 (this version):
#   - BOTH symbols now on Twelve Data. Free tier, 800 credits/day, no card.
#     XAUUSD: "XAU/USD" (genuine spot gold — matches the user's OANDA chart
#     far more closely than PAXG-USD ever could; the PAXG experiment showed
#     the flip firing 25 min early on the wrong candle, which is exactly the
#     class of error that destroys a statistical edge).
#     NDX: "NDX" (Nasdaq 100 index). Fixes Yahoo's chronic 5-15 min stale
#     feed that was silently hiding NDX flips.
#     Credit budget: 288 lower-TF calls/symbol/day + 24 hourly HTF calls/
#     symbol/day = ~624/day total, safely under the 800/day cap.
#   - Per-symbol HTF cache (previously XAU-only), keyed by symbol name.
#   - min_body_ratio 0.40 -> 0.50 (matches Pine default).
#   - SL swing lookback 5 -> 3 (matches Pine scalp_lookback default).
#   - File de-duplicated (was two copies concatenated).
#   - "Close Manually" invalidation notification removed entirely.
#   - One setup per session per symbol.
# ==============================================================================

import os
import json
import random
import requests
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import yfinance as yf  # kept only as a fallback; not used by SYMBOLS below

# ------------------------------------------------------------------- CONFIG
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

for _n, _v in [("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL),
               ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
               ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
               ("TWELVE_DATA_API_KEY", TWELVE_DATA_API_KEY)]:
    if not _v:
        print(f"[CONFIG] WARNING: {_n} is empty — check GitHub Secrets "
              f"and the env block in main.yml.")

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
HTF_CACHE_FILE = "htf_cache.json"          # per-symbol 1h HTF cache
STATE_FILE     = "active_trades.json"
ZAMBIA_TZ      = pytz.timezone("Africa/Lusaka")

FLIP_LOOKBACK_MINUTES = 120                # 2h safety net vs delayed runs

# ---- Pine-matching thresholds (do NOT change without changing the chart too)
ADX_STRONG        = 20.0   # adx_min
ADX_CONSOLIDATION = 15.0   # consolidation_adx_max
BODY_STRONG       = 0.50   # min_body_ratio
SL_SWING_LOOKBACK = 3      # scalp_lookback
SL_BUFFER         = 0.0    # scalp_sl_buffer

def interval_minutes(s):
    return int(s.rstrip("m"))

def lookback_bars_for(s):
    return max(4, round(FLIP_LOOKBACK_MINUTES / interval_minutes(s)))

def to_twelvedata_interval(s):
    return f"{interval_minutes(s)}min"

# ------------------------------------------------------------------- SYMBOLS
SYMBOLS = {
    "NDX":    {"ticker": "QQQ",    "session": "ASIAN",    "interval": "5m",
               "source": "twelvedata"},
    "XAUUSD": {"ticker": "XAU/USD", "session": "NEW_YORK", "interval": "5m",
               "source": "twelvedata"},
}

# ------------------------------------------------------------------- MESSAGES
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

# ------------------------------------------------------------------- SESSIONS
SESSION_WINDOWS = {
    "ASIAN":    (2 * 60,        10 * 60),        # 02:00 - 10:00 CAT — NDX
    "NEW_YORK": (15 * 60 + 30, 21 * 60 + 55),    # 15:30 - 21:55 CAT — XAUUSD
}

def to_cat(ts):
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(ZAMBIA_TZ)

def is_time_in_session(cat_dt, session_type):
    w = SESSION_WINDOWS.get(session_type)
    if w is None:
        return False
    t = cat_dt.hour * 60 + cat_dt.minute
    return w[0] <= t <= w[1]

def is_bar_in_session(bar_ts, session_type):
    return is_time_in_session(to_cat(bar_ts), session_type)

def session_key_for(cat_dt, session_type):
    return f"{cat_dt.strftime('%Y-%m-%d')}_{session_type}"

# ------------------------------------------------------------- TWELVE DATA
def fetch_twelvedata_series(symbol, interval, outputsize=300):
    """
    Fetch a time series from Twelve Data and return it shaped like yfinance:
    UTC-aware DatetimeIndex, Open/High/Low/Close, oldest-to-newest.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "timezone": "UTC",
        "order": "ASC",
        "apikey": TWELVE_DATA_API_KEY,
    }
    r = requests.get(f"{TWELVE_DATA_BASE_URL}/time_series",
                     params=params, timeout=20)
    d = r.json()

    # Twelve Data returns {"status":"error","message":"..."} on failure,
    # including "you have run out of API credits" — surface that clearly.
    if d.get("status") == "error" or "values" not in d:
        raise RuntimeError(f"Twelve Data error for {symbol} ({interval}): {d}")

    df = pd.DataFrame(d["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns={"open": "Open", "high": "High",
                            "low": "Low", "close": "Close"})
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = df[c].astype(float)
    return df[["Open", "High", "Low", "Close"]]

# ------------------------------------------------------------- HTF CACHE
def load_htf_cache():
    if os.path.exists(HTF_CACHE_FILE):
        try:
            with open(HTF_CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_htf_cache(c):
    with open(HTF_CACHE_FILE, "w") as f:
        json.dump(c, f, indent=2)

def get_htf_df(symbol, cache_key, interval="1h", outputsize=200):
    """
    Return the 1h OHLC DataFrame for `symbol`, refetched from Twelve Data at
    most once per hour and cached on disk between refreshes. 1h candles can't
    change faster than once an hour anyway, so re-fetching every 5-minute
    scan would just burn credits for identical data. This keeps total daily
    usage around ~624 credits against the 800/day free cap.

    Cache is keyed per symbol so two symbols don't overwrite each other.
    """
    cache = load_htf_cache()
    now_utc = datetime.now(pytz.UTC)
    entry = cache.get(cache_key)
    cached_time = entry.get("fetched_at") if entry else None

    needs_refresh = cached_time is None
    if not needs_refresh:
        cached_dt = datetime.fromisoformat(cached_time)
        needs_refresh = (now_utc - cached_dt).total_seconds() >= 3600

    if needs_refresh:
        print(f"[{symbol}] Refreshing Twelve Data {interval} HTF series.")
        df_1h = fetch_twelvedata_series(symbol, interval, outputsize=outputsize)
        cache[cache_key] = {
            "fetched_at": now_utc.isoformat(),
            "data": df_1h.reset_index().to_json(orient="records",
                                                date_format="iso"),
        }
        save_htf_cache(cache)
    else:
        age_min = (now_utc - datetime.fromisoformat(cached_time)).total_seconds() / 60
        print(f"[{symbol}] Using cached {interval} HTF series (age {age_min:.0f} min).")

    records = json.loads(cache[cache_key]["data"])
    df_1h = pd.DataFrame(records).rename(columns={"datetime": "dt"})
    df_1h["dt"] = pd.to_datetime(df_1h["dt"], utc=True)
    df_1h = df_1h.set_index("dt").sort_index()
    return df_1h[["Open", "High", "Low", "Close"]]

# ------------------------------------------------------------- INDICATORS
def calculate_indicators(df_lower, df_1h):
    df_1h = df_1h.copy()
    df_1h["HTF_EMA"] = df_1h["Close"].ewm(span=50, adjust=False).mean()

    df_lower = pd.merge_asof(
        df_lower.sort_index(),
        df_1h[["HTF_EMA"]].sort_index(),
        left_index=True, right_index=True, direction="backward",
    )

    high, low, close, open_p = (df_lower["High"], df_lower["Low"],
                                df_lower["Close"], df_lower["Open"])

    # --- Supertrend(10, 3.0) — bar-for-bar match to the Pine ---
    tr = pd.concat([high - low,
                    (high - close.shift(1)).abs(),
                    (low  - close.shift(1)).abs()], axis=1).max(axis=1)
    atr10 = tr.ewm(alpha=1/10, adjust=False).mean()
    hl2 = (high + low) / 2
    basic_ub = hl2 + 3.0 * atr10
    basic_lb = hl2 - 3.0 * atr10

    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()
    st = pd.Series(1, index=df_lower.index)
    for i in range(1, len(df_lower)):
        final_ub.iloc[i] = (
            basic_ub.iloc[i]
            if (basic_ub.iloc[i] < final_ub.iloc[i-1]
                or close.iloc[i-1] > final_ub.iloc[i-1])
            else final_ub.iloc[i-1]
        )
        final_lb.iloc[i] = (
            basic_lb.iloc[i]
            if (basic_lb.iloc[i] > final_lb.iloc[i-1]
                or close.iloc[i-1] < final_lb.iloc[i-1])
            else final_lb.iloc[i-1]
        )
        if st.iloc[i-1] == 1:
            st.iloc[i] = -1 if close.iloc[i] < final_lb.iloc[i] else 1
        else:
            st.iloc[i] =  1 if close.iloc[i] > final_ub.iloc[i] else -1
    df_lower["ST_Trend"] = st

    # --- ADX(14) Wilder — same as Pine's ta.dmi(14,14) ---
    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm   = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm  = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr14   = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = (100 * pd.Series(plus_dm,  index=df_lower.index)
                     .ewm(alpha=1/14, adjust=False).mean() / atr14)
    minus_di = (100 * pd.Series(minus_dm, index=df_lower.index)
                      .ewm(alpha=1/14, adjust=False).mean() / atr14)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df_lower["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()

    # --- Body ratio — matches Pine's body_ratio ---
    df_lower["BodyRatio"] = (close - open_p).abs() / np.maximum(high - low, 0.0001)
    return df_lower

def drop_unclosed_candles(df, interval_str, tolerance_seconds=2):
    """
    Remove any trailing candle that hasn't fully closed yet. Pine confirms
    signals only on closed bars (barstate.isconfirmed); without this, the
    in-progress candle can produce a flip that vanishes by its close.
    """
    if df.empty:
        return df, 0
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    bar_len = pd.Timedelta(minutes=interval_minutes(interval_str))
    now_utc = pd.Timestamp(datetime.now(pytz.UTC))
    closed = (idx + bar_len) <= (now_utc + pd.Timedelta(seconds=tolerance_seconds))
    return df[closed], int((~closed).sum())

def find_recent_flip(df, lookback):
    """
    Scan the last `lookback` closed bars for a Supertrend flip. Returns
    (index, "BUY"/"SELL", timestamp) of the MOST RECENT flip in the window,
    or (None, None, None). The lookback window means a delayed/skipped run
    can still pick the flip up a bar or two later.
    """
    t = df["ST_Trend"]
    n = len(t)
    start = max(1, n - lookback)
    for i in range(n - 1, start - 1, -1):
        if t.iloc[i] == 1 and t.iloc[i-1] == -1:
            return i, "BUY",  df.index[i]
        if t.iloc[i] == -1 and t.iloc[i-1] == 1:
            return i, "SELL", df.index[i]
    return None, None, None

# ------------------------------------------------------------- DISPATCH
def send_notification(title, body, color_code=3447003):
    if DISCORD_WEBHOOK_URL:
        payload = {
            "content": "@everyone",
            "embeds": [{
                "title": title,
                "description": body,
                "color": color_code,
                "footer": {"text": "Trend Targets Pro • Mandalorian Warrior Creed"},
            }],
        }
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            print(f"[DISPATCH] Discord status={r.status_code}")
            if r.status_code >= 300:
                print(f"[DISPATCH] Discord body: {r.text[:300]}")
        except Exception as e:
            print(f"[DISPATCH] Discord error: {e}")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        msg = f"*{title}*\n\n{body}\n\n_Trend Targets Pro • Warrior Creed_"
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                      "parse_mode": "Markdown"},
                timeout=5,
            )
            print(f"[DISPATCH] Telegram status={r.status_code}")
            if r.status_code >= 300:
                print(f"[DISPATCH] Telegram body: {r.text[:300]}")
        except Exception as e:
            print(f"[DISPATCH] Telegram error: {e}")

# ------------------------------------------------------------- STATE
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)

def get_last_flip_seen(s, n):
    return s.get("_meta", {}).get(n)

def set_last_flip_seen(s, n, iso):
    s.setdefault("_meta", {})[n] = iso

def get_session_taken(s, n):
    return s.get("_session_taken", {}).get(n)

def set_session_taken(s, n, key):
    s.setdefault("_session_taken", {})[n] = key

DECISION_LOG_FILE = "decision_log.txt"

def log_decision(line):
    ts = datetime.now(ZAMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S CAT")
    entry = f"{ts} | {line}"
    print(f"[DECISION LOG] {entry}")
    try:
        with open(DECISION_LOG_FILE, "a") as f:
            f.write(entry + "\n")
    except Exception as e:
        print(f"[DECISION LOG] write error: {e}")

# ------------------------------------------------------------- SCANNER
def run_scanner():
    state = load_state()
    print(f"\n===== SCAN START — "
          f"{datetime.now(ZAMBIA_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')} =====")

    for name, cfg in SYMBOLS.items():
        ticker       = cfg["ticker"]
        session_type = cfg["session"]
        source       = cfg["source"]
        interval     = cfg["interval"]
        lookback_bars = lookback_bars_for(interval)

        print(f"\n--- {name} ({ticker}, session={session_type}, "
              f"source={source}, interval={interval}) ---")

        # ---------------------------------------------------- DATA FETCH
        try:
            if source == "twelvedata":
                df_lower = fetch_twelvedata_series(
                    ticker, to_twelvedata_interval(interval), outputsize=300)
                df_1h = get_htf_df(ticker, cache_key=f"{name}_1h",
                                   interval="1h", outputsize=200)
            elif source == "yfinance":                       # fallback only
                df_lower = yf.download(ticker, period="5d",
                                       interval=interval, progress=False)
                df_1h    = yf.download(ticker, period="10d",
                                       interval="1h", progress=False)
                if isinstance(df_lower.columns, pd.MultiIndex):
                    df_lower.columns = df_lower.columns.get_level_values(0)
                if isinstance(df_1h.columns, pd.MultiIndex):
                    df_1h.columns = df_1h.columns.get_level_values(0)
            else:
                print(f"[{name}] SKIPPED — unknown source '{source}'")
                continue
        except Exception as e:
            print(f"[{name}] Download error: {e}")
            continue

        # Only ever act on CLOSED candles.
        df_lower, n_dropped = drop_unclosed_candles(df_lower, interval)
        if n_dropped:
            print(f"[{name}] Dropped {n_dropped} still-forming candle(s).")

        if df_lower.empty or len(df_lower) < 50 or df_1h.empty:
            print(f"[{name}] SKIPPED — insufficient data "
                  f"({interval}: {len(df_lower)}, 1h: {len(df_1h)})")
            continue

        # Feed freshness diagnostic.
        last_open = df_lower.index[-1]
        if last_open.tzinfo is None:
            last_open = last_open.tz_localize("UTC")
        age_min = (pd.Timestamp(datetime.now(pytz.UTC))
                   - (last_open + pd.Timedelta(minutes=interval_minutes(interval)))
                   ).total_seconds() / 60
        stale = age_min > interval_minutes(interval) + 1.5
        print(f"[{name}] Data age: {age_min:.1f} min "
              f"({'STALE — provider feed is behind' if stale else 'OK, live'}).")

        df = calculate_indicators(df_lower, df_1h)

        latest_cat = to_cat(df.index[-1])
        print(f"[{name}] {len(df)} bars loaded | latest bar: "
              f"{latest_cat.strftime('%Y-%m-%d %H:%M %Z')} (CAT) | "
              f"in_session_now={is_time_in_session(latest_cat, session_type)}")

        high_p = float(df.iloc[-1]["High"])
        low_p  = float(df.iloc[-1]["Low"])

        # ---------------------------------------------------- 1. MANAGE LIVE TRADE
        if name in state:
            t = state[name]
            d, e, sl, tp1, tp2 = (t["direction"], t["entry"], t["sl"],
                                  t["tp1"], t["tp2"])
            print(f"[{name}] Live {d} | entry={e:.2f} sl={sl:.2f} "
                  f"tp1={tp1:.2f} tp2={tp2:.2f} tp1_hit={t['tp1_hit']}")

            closed = False
            if d == "BUY":
                if not t["tp1_hit"] and high_p >= tp1:
                    t["tp1_hit"] = True
                    t["sl_moved_to_be"] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name} ({interval})",
                        f"{random.choice(TP1_MESSAGES)}\n\n"
                        f"• *Entry:* `{e:.2f}`\n• *TP1:* `{tp1:.2f}`\n"
                        f"• *New SL:* `{e:.2f} (Break Even)`",
                        color_code=65280,
                    )
                elif t["tp1_hit"] and high_p >= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} ({interval})",
                        f"{random.choice(TP2_MESSAGES)}\n\n"
                        f"• *Entry:* `{e:.2f}`\n• *TP2 (1:2):* `{tp2:.2f}`",
                        color_code=65280,
                    )
                    closed = True
                elif low_p <= (e if t["sl_moved_to_be"] else sl):
                    if t["sl_moved_to_be"]:
                        send_notification(
                            f"🛡️ BREAK EVEN HIT — {name}",
                            f"{random.choice(BE_HIT_MESSAGES)}\n\n"
                            f"• *Entry/BE:* `{e:.2f}`",
                            color_code=1752220,
                        )
                    else:
                        send_notification(
                            f"🛑 STOP LOSS HIT — {name}",
                            f"{random.choice(SL_HIT_MESSAGES)}\n\n"
                            f"• *Entry:* `{e:.2f}`\n• *SL:* `{sl:.2f}`",
                            color_code=15548997,
                        )
                    closed = True

            elif d == "SELL":
                if not t["tp1_hit"] and low_p <= tp1:
                    t["tp1_hit"] = True
                    t["sl_moved_to_be"] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name} ({interval})",
                        f"{random.choice(TP1_MESSAGES)}\n\n"
                        f"• *Entry:* `{e:.2f}`\n• *TP1:* `{tp1:.2f}`\n"
                        f"• *New SL:* `{e:.2f} (Break Even)`",
                        color_code=65280,
                    )
                elif t["tp1_hit"] and low_p <= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} ({interval})",
                        f"{random.choice(TP2_MESSAGES)}\n\n"
                        f"• *Entry:* `{e:.2f}`\n• *TP2 (1:2):* `{tp2:.2f}`",
                        color_code=65280,
                    )
                    closed = True
                elif high_p >= (e if t["sl_moved_to_be"] else sl):
                    if t["sl_moved_to_be"]:
                        send_notification(
                            f"🛡️ BREAK EVEN HIT — {name}",
                            f"{random.choice(BE_HIT_MESSAGES)}\n\n"
                            f"• *Entry/BE:* `{e:.2f}`",
                            color_code=1752220,
                        )
                    else:
                        send_notification(
                            f"🛑 STOP LOSS HIT — {name}",
                            f"{random.choice(SL_HIT_MESSAGES)}\n\n"
                            f"• *Entry:* `{e:.2f}`\n• *SL:* `{sl:.2f}`",
                            color_code=15548997,
                        )
                    closed = True

            if closed:
                del state[name]
                save_state(state)
                continue

        # ---------------------------------------------------- 2. NEW SETUP?
        fi, direction, ftime = find_recent_flip(df, lookback=lookback_bars)
        if fi is None:
            print(f"[{name}] No Supertrend flip in last {lookback_bars} bars.")
            continue

        ft_cat = to_cat(ftime)
        ft_iso = ftime.isoformat()
        print(f"[{name}] Flip found: {direction} at "
              f"{ft_cat.strftime('%Y-%m-%d %H:%M %Z')} (CAT)")

        # Deduplicate — never re-evaluate the same flip bar twice.
        if get_last_flip_seen(state, name) == ft_iso:
            print(f"[{name}] Flip already evaluated on a prior run — skipping.")
            continue
        set_last_flip_seen(state, name, ft_iso)
        save_state(state)

        # Session gate — flip's own candle timestamp must be in-window.
        if not is_bar_in_session(ftime, session_type):
            log_decision(f"{name} | {direction} @ "
                         f"{ft_cat.strftime('%Y-%m-%d %H:%M CAT')} | "
                         f"OUT OF SESSION ({session_type})")
            continue

        # One-setup-per-session gate.
        skey = session_key_for(ft_cat, session_type)
        if get_session_taken(state, name) == skey:
            log_decision(f"{name} | {direction} @ "
                         f"{ft_cat.strftime('%Y-%m-%d %H:%M CAT')} | "
                         f"session {skey} already traded")
            continue

        # Active-trade gate.
        if name in state:
            log_decision(f"{name} | {direction} @ "
                         f"{ft_cat.strftime('%Y-%m-%d %H:%M CAT')} | "
                         f"active trade still open")
            continue

        # --- Score the flip exactly like Pine ---
        bar    = df.iloc[fi]
        entry  = float(bar["Close"])
        htf    = float(bar["HTF_EMA"])
        adx    = float(bar["ADX"])
        body   = float(bar["BodyRatio"])
        is_buy = direction == "BUY"

        htf_ok  = (entry > htf) if is_buy else (entry < htf)
        adx_ok  = adx >= ADX_STRONG
        body_ok = body >= BODY_STRONG
        consol  = adx < ADX_CONSOLIDATION

        score = int(htf_ok) + int(adx_ok) + int(body_ok)
        if consol:
            tier = "LOW"
        elif score == 3:
            tier = "HIGH"
        elif score == 2:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        print(f"[{name}] Score {score}/3 — HTF={htf_ok} "
              f"(close={entry:.2f} vs HTF EMA={htf:.2f}) | "
              f"ADX>=20={adx_ok} (ADX={adx:.1f}) | "
              f"body>=0.50={body_ok} (body={body:.2f}) | "
              f"consolidating={consol} -> tier={tier}")

        if tier == "LOW":
            log_decision(f"{name} | {direction} @ "
                         f"{ft_cat.strftime('%Y-%m-%d %H:%M CAT')} | "
                         f"IN SESSION, tier=LOW (score={score}/3) | no alert")
            continue

        # Lock the session in, build the trade, dispatch.
        set_session_taken(state, name, skey)
        log_decision(f"{name} | {direction} @ "
                     f"{ft_cat.strftime('%Y-%m-%d %H:%M CAT')} | "
                     f"IN SESSION, tier={tier} (score={score}/3) | "
                     f"dispatching alert, session locked")

        # SL: swing of the SL_SWING_LOOKBACK bars before the signal bar.
        s = max(0, fi - SL_SWING_LOOKBACK)
        seg = df.iloc[s:fi]
        if seg.empty:
            # Extremely rare (flip on bar 1) — fall back to signal bar's own range.
            seg = df.iloc[fi:fi+1]
        sl_px = float(seg["Low"].min())  - SL_BUFFER if is_buy \
                else float(seg["High"].max()) + SL_BUFFER

        risk = abs(entry - sl_px) or entry * 0.001
        tp1 = entry + risk      if is_buy else entry - risk
        tp2 = entry + 2 * risk  if is_buy else entry - 2 * risk

        state[name] = {
            "direction": direction,
            "entry": entry, "sl": sl_px, "tp1": tp1, "tp2": tp2,
            "tp1_hit": False, "sl_moved_to_be": False,
        }
        save_state(state)

        tier_txt = ("HIGH PROBABILITY SETUP ⭐⭐⭐" if tier == "HIGH"
                    else "MEDIUM PROBABILITY SETUP ⭐⭐")
        emoji = "⚔️ 🟢" if is_buy else "⚔️ 🔴"
        color = 5763719 if is_buy else 15548997

        body_msg = (
            f"{emoji} *{direction} SIGNAL CONFIRMED on {name} ({interval})*\n"
            f"• *Tier:* `{tier_txt}`\n\n"
            f"• *Entry Price:* `{entry:.2f}`\n"
            f"• *Stop Loss:* `{sl_px:.2f}`\n"
            f"• *TP1 (1:1 R/R):* `{tp1:.2f}`\n"
            f"• *TP2 (1:2 R/R):* `{tp2:.2f}`\n\n"
            f"• *ADX:* `{adx:.1f}` | *Candle Body:* `{body*100:.1f}%`\n\n"
            f"*Honor the risk rules and execute with courage. This is the way.*"
        )
        send_notification(f"🚨 TREND TARGETS PRO — {name}", body_msg,
                          color_code=color)

# ------------------------------------------------------------- MAIN
if __name__ == "__main__":
    try:
        run_scanner()
    except Exception as e:
        print(f"Scanner Exception: {e}")