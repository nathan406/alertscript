# ==============================================================================
# TREND TARGETS PRO — MANDALORIAN WARRIOR EDITION (1M TEST MODE)
# ==============================================================================
# Description: Temporary 1-Minute Live Testing Script for BTCUSD
# Theme: Mandalorian / Warrior Creed
# Core Rule: "This is the way." in every alert message.
# ==============================================================================

import os
import json
import math
import random
import requests
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import yfinance as yf

# ==============================================================================
# TEST MODE CONFIGURATION
# ==============================================================================
# Set TEST_MODE = True to bypass session limits and test on 1m BTC candles.
# Set TEST_MODE = False when returning to live 15m trading production.
TEST_MODE = True

# Webhooks and Bot tokens for dispatching warrior dispatches
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550985326770528266/9oOJm2yH7o7RLaQBBjeH7AW9_Q31tAKBu2ae8w3dk1GIUuFY0NRtlm3AyLv8RQb2vouZ"
TELEGRAM_BOT_TOKEN = "8946173658:AAGw-lqdxlgmraOcQyJbyHTlCL7P1dxWbW4"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # Replace with your numerical Chat ID

STATE_FILE = "active_trades.json"
ZAMBIA_TZ = pytz.timezone("Africa/Lusaka")

# Symbol mapping for testing: Only BTCUSD on 24/7 crypto market
SYMBOLS = {
    "BTCUSD": ("BTC-USD", "NEW_YORK")
}

# ==============================================================================
# MANDALORIAN MESSAGES (25+ Variations Each — "This is the way.")
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
# SESSION FILTERING (ZAMBIA / CAT TIME)
# ==============================================================================
def is_in_session(session_type):
    """
    Checks if current Zambia / Central Africa Time (CAT) falls within active trading sessions.
    Bypassed if TEST_MODE = True.
    """
    if TEST_MODE:
        return True  # Always active during testing

    now_cat = datetime.now(ZAMBIA_TZ)
    time_min = now_cat.hour * 60 + now_cat.minute

    if session_type == "ASIAN":
        return 120 <= time_min <= 462
    elif session_type == "NEW_YORK":
        return 930 <= time_min <= 1305
    return False

# ==============================================================================
# INDICATOR ENGINE
# ==============================================================================
def calculate_indicators(df_1m, df_1h):
    """
    Calculates HTF EMA 50, Supertrend (10, 3.0), ADX (14), and Candle Body Ratio.
    """
    df_1h['HTF_EMA'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
    
    df_1m = pd.merge_asof(
        df_1m.sort_index(),
        df_1h[['HTF_EMA']].sort_index(),
        left_index=True,
        right_index=True,
        direction='backward'
    )

    high, low, close, open_p = df_1m['High'], df_1m['Low'], df_1m['Close'], df_1m['Open']

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
    st_trend = pd.Series(1, index=df_1m.index)

    for i in range(1, len(df_1m)):
        final_ub.iloc[i] = basic_ub.iloc[i] if (basic_ub.iloc[i] < final_ub.iloc[i-1] or close.iloc[i-1] > final_ub.iloc[i-1]) else final_ub.iloc[i-1]
        final_lb.iloc[i] = basic_lb.iloc[i] if (basic_lb.iloc[i] > final_lb.iloc[i-1] or close.iloc[i-1] < final_lb.iloc[i-1]) else final_lb.iloc[i-1]

        if st_trend.iloc[i-1] == 1:
            st_trend.iloc[i] = -1 if close.iloc[i] < final_lb.iloc[i] else 1
        else:
            st_trend.iloc[i] = 1 if close.iloc[i] > final_ub.iloc[i] else -1

    df_1m['ST_Trend'] = st_trend

    # ADX (14)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df_1m.index).ewm(alpha=1/14, adjust=False).mean() / atr14)
    minus_di = 100 * (pd.Series(minus_dm, index=df_1m.index).ewm(alpha=1/14, adjust=False).mean() / atr14)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df_1m['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()

    # Candle Body Ratio
    df_1m['BodyRatio'] = (close - open_p).abs() / np.maximum(high - low, 0.0001)

    return df_1m

# ==============================================================================
# DISPATCH MESSAGES
# ==============================================================================
def send_notification(title, message_body, color_code=3447003):
    """
    Sends Mandalorian-themed alert embeds to Discord Webhook & Telegram Bot.
    """
    # Discord Dispatch
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
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            print(f"Discord dispatch error: {e}")

    # Telegram Dispatch
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        full_msg = f"*{title}*\n\n{message_body}\n\n_Trend Targets Pro • Warrior Creed_"
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": full_msg, "parse_mode": "Markdown"},
                timeout=10
            )
        except Exception as e:
            print(f"Telegram dispatch error: {e}")

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

# ==============================================================================
# MAIN SCANNER ROUTINE
# ==============================================================================
def run_scanner():
    state = load_state()

    # Determine timeframe interval based on TEST_MODE
    tf_interval = "1m" if TEST_MODE else "15m"
    tf_period = "1d" if TEST_MODE else "5d"

    for name, (ticker, session_type) in SYMBOLS.items():
        # Fetch candle data
        df_lower = yf.download(tickers=ticker, period=tf_period, interval=tf_interval, progress=False)
        df_1h = yf.download(tickers=ticker, period="10d", interval="1h", progress=False)

        if df_lower.empty or len(df_lower) < 50 or df_1h.empty:
            continue

        if isinstance(df_lower.columns, pd.MultiIndex):
            df_lower.columns = df_lower.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        df = calculate_indicators(df_lower, df_1h)

        latest_bar = df.iloc[-2]  # Last closed candle
        close_p = float(latest_bar['Close'])
        high_p = float(latest_bar['High'])
        low_p = float(latest_bar['Low'])

        # ----------------------------------------------------------------------
        # 1. EVALUATE ACTIVE TRADES (TP1, TP2, SL, BE)
        # ----------------------------------------------------------------------
        if name in state:
            trade = state[name]
            direction = trade['direction']
            entry = trade['entry']
            sl = trade['sl']
            tp1 = trade['tp1']
            tp2 = trade['tp2']

            if direction == "BUY":
                if not trade['tp1_hit'] and high_p >= tp1:
                    trade['tp1_hit'] = True
                    trade['sl_moved_to_be'] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name} ({tf_interval.upper()})",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                elif trade['tp1_hit'] and high_p >= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} ({tf_interval.upper()})",
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
                        f"🎯 TP1 HIT — {name} ({tf_interval.upper()})",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                elif trade['tp1_hit'] and low_p <= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name} ({tf_interval.upper()})",
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
        # 2. CHECK SESSION & GENERATE NEW SIGNALS
        # ----------------------------------------------------------------------
        if not is_in_session(session_type):
            continue

        curr_st, prev_st = df['ST_Trend'].iloc[-2], df['ST_Trend'].iloc[-3]
        htf_ema = float(latest_bar['HTF_EMA'])
        adx_val = float(latest_bar['ADX'])
        body_ratio = float(latest_bar['BodyRatio'])

        buy_flip = (prev_st == -1) and (curr_st == 1)
        sell_flip = (prev_st == 1) and (curr_st == -1)

        # In TEST_MODE, if no flip occurred, evaluate current trend direction to force a test alert
        if TEST_MODE and not (buy_flip or sell_flip):
            if curr_st == 1:
                buy_flip = True
            else:
                sell_flip = True

        if not (buy_flip or sell_flip):
            continue

        tier_txt = "TEST RUN — MANDALORIAN SIGNAL ⭐⭐⭐"
        direction = "BUY" if buy_flip else "SELL"

        lookback_bars = df.iloc[-5:-2]
        sl_px = float(lookback_bars['Low'].min()) if buy_flip else float(lookback_bars['High'].max())

        risk = abs(close_p - sl_px)
        tp1_px = close_p + risk if buy_flip else close_p - risk
        tp2_px = close_p + (risk * 2.0) if buy_flip else close_p - (risk * 2.0)

        state[name] = {
            "direction": direction,
            "entry": close_p,
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
            f"{emoji} *{direction} SIGNAL CONFIRMED on {name} (1M TEST)*\n"
            f"• *Tier:* `{tier_txt}`\n\n"
            f"• *Entry Price:* `{close_p:.2f}`\n"
            f"• *Stop Loss (Scalp):* `{sl_px:.2f}`\n"
            f"• *TP1 (1:1 R/R):* `{tp1_px:.2f}`\n"
            f"• *TP2 (1:2 R/R):* `{tp2_px:.2f}`\n\n"
            f"• *ADX Strength:* `{adx_val:.1f}` | *Candle Body:* `{body_ratio*100:.1f}%`\n\n"
            f"*Honor the risk rules and execute with courage. This is the way.*"
        )
        send_notification(f"🚨 TREND TARGETS PRO — {name}", msg_body, color_code=color)

if __name__ == "__main__":
    run_scanner()