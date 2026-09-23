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
# TEST_MODE is permanently False -> Strict 15m Timeframe, Medium/High prob setups only.
TEST_MODE = False

# Webhooks and Bot tokens for dispatching warrior dispatches
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550985326770528266/9oOJm2yH7o7RLaQBBjeH7AW9_Q31tAKBu2ae8w3dk1GIUuFY0NRtlm3AyLv8RQb2vouZ"
TELEGRAM_BOT_TOKEN = "8946173658:AAGw-lqdxlgmraOcQyJbyHTlCL7P1dxWbW4"
TELEGRAM_CHAT_ID = "5754432239"

STATE_FILE = "active_trades.json"
ZAMBIA_TZ = pytz.timezone("Africa/Lusaka")

# How many recent closed bars to scan for a flip we haven't acted on yet.
# This is what protects you from a delayed/skipped GitHub Actions run.
FLIP_LOOKBACK_BARS = 8

# Symbol mapping: (yfinance ticker, session constraint)
# GER40 is ASIAN-only, per request — any flip outside the Asian session
# window on the 15m is ignored for this symbol.
# XAUUSD: Yahoo has no true spot-gold cross (XAUUSD=X does not exist —
# confirmed by a live 404 on 2026-09-23). Gold is only available via
# GC=F (COMEX futures) or GLD (US-hours-only ETF, no good for Asian
# session). GC=F's daily CME maintenance halt (~17:00-18:00 ET) lands
# around 23:00-00:00 CAT, well outside the 02:00-07:45 Asian window, so
# it should have usable 15m data through the Asian session.
SYMBOLS = {
    "BTCUSD": ("BTC-USD", "NEW_YORK"),
    "NDX":    ("NQ=F", "NEW_YORK"),
    "GER40":  ("^GDAXI", "ASIAN"),
    "XAUUSD": ("GC=F", "ASIAN"),
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

# ==============================================================================
# SESSION FILTERING (CAT TIME: 02:00 - 07:45 ASIAN | 15:30 - 21:45 NEW YORK)
# ==============================================================================
def to_cat(ts: pd.Timestamp) -> pd.Timestamp:
    """
    Convert a pandas Timestamp (tz-aware in whatever timezone yfinance
    returned it in, or tz-naive) into Africa/Lusaka time. yfinance does not
    consistently return the same source timezone across tickers/exchanges,
    so we can't assume UTC — tz_convert handles it correctly either way.
    """
    if ts.tzinfo is None:
        ts = ts.tz_localize('UTC')
    return ts.tz_convert(ZAMBIA_TZ)


def is_time_in_session(cat_dt, session_type):
    """
    Checks whether a given Africa/Lusaka datetime falls within a
    designated market session.
      - ASIAN:    02:00 to 07:45 CAT (120 to 465 minutes)
      - NEW_YORK: 15:30 to 21:45 CAT (930 to 1305 minutes)
    """
    time_min = cat_dt.hour * 60 + cat_dt.minute

    if session_type == "ASIAN":
        return 120 <= time_min <= 465
    elif session_type == "NEW_YORK":
        return 930 <= time_min <= 1305
    return False


def is_bar_in_session(bar_timestamp, session_type):
    """
    Session check anchored to the CANDLE's own close time, not to the
    wall-clock time the script happens to execute. This is what makes the
    filter immune to GitHub Actions scheduling delays/jitter.
    """
    return is_time_in_session(to_cat(bar_timestamp), session_type)

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


def find_recent_flip(df, lookback=FLIP_LOOKBACK_BARS):
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

    tf_interval = "15m"
    tf_period = "5d"

    run_started_cat = datetime.now(ZAMBIA_TZ)
    print(f"\n===== SCAN START — {run_started_cat.strftime('%Y-%m-%d %H:%M:%S %Z')} =====")

    for name, (ticker, session_type) in SYMBOLS.items():
        print(f"\n--- {name} ({ticker}, session={session_type}) ---")
        try:
            df_lower = yf.download(tickers=ticker, period=tf_period, interval=tf_interval, progress=False)
            df_1h = yf.download(tickers=ticker, period="10d", interval="1h", progress=False)
        except Exception as e:
            print(f"[{name}] Download error: {e}")
            continue

        if df_lower.empty or len(df_lower) < 50 or df_1h.empty:
            print(f"[{name}] SKIPPED — insufficient data "
                  f"(15m bars: {len(df_lower)}, 1h bars: {len(df_1h)})")
            continue

        if isinstance(df_lower.columns, pd.MultiIndex):
            df_lower.columns = df_lower.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        df = calculate_indicators(df_lower, df_1h)

        latest_bar_time = df.index[-1]
        latest_bar_cat = to_cat(latest_bar_time)
        print(f"[{name}] {len(df)} bars loaded | latest bar: {latest_bar_time} "
              f"(raw) -> {latest_bar_cat.strftime('%Y-%m-%d %H:%M %Z')} (CAT) | "
              f"in_session_now={is_time_in_session(latest_bar_cat, session_type)}")

        latest_bar = df.iloc[-1]
        close_p = float(latest_bar['Close'])
        high_p  = float(latest_bar['High'])
        low_p   = float(latest_bar['Low'])

        curr_st = df['ST_Trend'].iloc[-1]
        prev_st = df['ST_Trend'].iloc[-2]

        buy_flip  = (prev_st == -1) and (curr_st == 1)
        sell_flip = (prev_st == 1)  and (curr_st == -1)

        # ----------------------------------------------------------------------
        # 1. EVALUATE ACTIVE TRADES (always runs, regardless of session —
        #    you never want to miss closing/managing a live trade)
        # ----------------------------------------------------------------------
        if name in state and name != "_meta":
            trade = state[name]
            direction = trade['direction']
            entry = trade['entry']
            sl    = trade['sl']
            tp1   = trade['tp1']
            tp2   = trade['tp2']
            print(f"[{name}] Active {direction} trade found — entry={entry:.2f} sl={sl:.2f} "
                  f"tp1={tp1:.2f} tp2={tp2:.2f} tp1_hit={trade['tp1_hit']}")

            if (direction == "BUY" and sell_flip) or (direction == "SELL" and buy_flip):
                send_notification(
                    f"🔄 TRADE CLOSED ON REVERSE SIGNAL — {name}",
                    f"Trend flipped to opposite side. Active `{direction}` trade closed at `{close_p:.2f}`. This is the way.",
                    color_code=1752220
                )
                del state[name]
                save_state(state)

            elif direction == "BUY":
                if not trade['tp1_hit'] and high_p >= tp1:
                    trade['tp1_hit'] = True
                    trade['sl_moved_to_be'] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name} (15m)",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                elif trade['tp1_hit'] and high_p >= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} (15m)",
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
                        f"🎯 TP1 HIT — {name} (15m)",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                elif trade['tp1_hit'] and low_p <= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} (15m)",
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
        # 2. LOOK FOR AN UNPROCESSED FLIP AND GENERATE A NEW SIGNAL
        #    (session + probability filters are now evaluated against the
        #    FLIP BAR itself, not "now" — see find_recent_flip / is_bar_in_session)
        # ----------------------------------------------------------------------
        if name in state:
            # Already have an active trade on this symbol — nothing to open.
            print(f"[{name}] Skipping new-signal search — trade already active.")
            continue

        flip_idx, direction, flip_time = find_recent_flip(df, lookback=FLIP_LOOKBACK_BARS)
        if flip_idx is None:
            print(f"[{name}] No Supertrend flip in the last {FLIP_LOOKBACK_BARS} bars.")
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

        # Strict Medium/High Probability filters
        is_htf_aligned = (flip_close > htf_ema) if buy_flip_here else (flip_close < htf_ema)
        is_strong_trend = (adx_val >= 20.0) and (body_ratio >= 0.40)

        print(f"[{name}] Filters — HTF aligned: {is_htf_aligned} "
              f"(close={flip_close:.2f} vs HTF EMA={htf_ema:.2f}) | "
              f"ADX>=20: {adx_val >= 20.0} (ADX={adx_val:.1f}) | "
              f"Body>=0.40: {body_ratio >= 0.40} (body={body_ratio:.2f})")

        if not (is_htf_aligned and is_strong_trend):
            print(f"[{name}] Flip failed probability filters — LOW tier, no alert sent.")
            continue

        print(f"[{name}] Flip PASSED filters — dispatching alert.")

        tier_txt = "HIGH PROBABILITY SETUP ⭐⭐⭐" if adx_val >= 25 else "MEDIUM PROBABILITY SETUP ⭐⭐"

        lookback_start = max(0, flip_idx - 5)
        lookback_bars = df.iloc[lookback_start:flip_idx]
        sl_px = float(lookback_bars['Low'].min()) if buy_flip_here else float(lookback_bars['High'].max())

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
            f"{emoji} *{direction} SIGNAL CONFIRMED on {name} (15m)*\n"
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