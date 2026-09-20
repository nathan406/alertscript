# ==============================================================================
# TREND TARGETS PRO — MANDALORIAN WARRIOR EDITION
# ==============================================================================
# Description: 15-Minute Market Scanner & Automated Trade Manager
# Theme: Mandalorian / Warrior Creed — Honorable, Brave, Encouraging
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
# CONFIGURATION & CREDENTIALS
# ==============================================================================
# Webhooks and Bot tokens for dispatching warrior dispatches
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550985326770528266/9oOJm2yH7o7RLaQBBjeH7AW9_Q31tAKBu2ae8w3dk1GIUuFY0NRtlm3AyLv8RQb2vouZ"
TELEGRAM_BOT_TOKEN = "8946173658:AAGw-lqdxlgmraOcQyJbyHTlCL7P1dxWbW4"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # Replace with your numerical Chat ID

STATE_FILE = "active_trades.json"
ZAMBIA_TZ = pytz.timezone("Africa/Lusaka")

# Symbol mapping: Name -> (Yahoo Ticker, Session Type)
SYMBOLS = {
    "XAUUSD": ("GC=F", "ASIAN"),      # Gold Futures (Asian Session)
    "USTEC":  ("NQ=F", "NEW_YORK"),   # Nasdaq Futures (New York Session)
    "GER40":  ("^GDAXI", "NEW_YORK"), # DAX Index (New York Session)
    "BTCUSD": ("BTC-USD", "NEW_YORK") # Bitcoin (New York Session)
}

# ==============================================================================
# MANDALORIAN MESSAGES (25+ Variations Each — "This is the way.")
# ==============================================================================

# ------------------------------------------------------------------------------
# TP1 HIT: Partials banked, move Stop Loss to Entry (Break Even)
# ------------------------------------------------------------------------------
TP1_MESSAGES = [
    "Target 1 vanquished! 🎯 Partials stored in the foundry and armor reinforced at Break Even. This is the way.",
    "First blow struck with precision! ⚔️ TP1 claimed, risk eliminated. Move SL to Break Even. This is the way.",
    "The clan claims its first bounty! 💰 TP1 hit, SL moved to entry. We fight risk-free now. This is the way.",
    "BAM! TP1 struck like a Mandalorian spear! 🚀 Move SL to Break Even and let the rest run. This is the way.",
    "Beskar-grade execution! 🎯 TP1 achieved. SL adjusted to Break Even. Free trade activated. This is the way.",
    "Rule of the Creed followed to the letter! TP1 banked. Protect the treasury — SL to BE! This is the way.",
    "Bounty partially collected! 💼 TP1 hit. Shift your stop loss to break even immediately! This is the way.",
    "Executing like a true warrior! 🎯 TP1 hit. SL to BE. We march forward without fear! This is the way.",
    "Target 1 reached on the battleground! 🚀 Partial spoils secured. Move SL to break even! This is the way.",
    "The 15M chart yields to our strength! 🎯 TP1 hit. SL shifted to entry level! This is the way.",
    "Flawless combat maneuver! TP1 hit cleanly. 💰 Move SL to Break Even and hold your ground! This is the way.",
    "The strategy read the market like an ancient script! 📜 TP1 secured. Adjust SL to Break Even! This is the way.",
    "Zero emotion, pure warrior discipline! 🎯 TP1 hit. Move SL to Break Even now! This is the way.",
    "TP1 tagged! 🎯 Half the risk off the table, total confidence intact. SL to Break Even! This is the way.",
    "Spoils collected! 💵 TP1 reached. Shift SL to Break Even and prepare for full victory! This is the way.",
    "Green shines on our armor! 🟢 TP1 hit. SL moved to Break Even — zero risk mode engaged! This is the way.",
    "A noble strike! 🎯 TP1 bagged. Move SL to entry price and stay vigilant! This is the way.",
    "The market respects the warrior's code! 🎯 TP1 hit. Move SL to Break Even! This is the way.",
    "Treasury growing heavier! 💰 TP1 hit. Move SL to BE and defend your gain! This is the way.",
    "BOOM! TP1 smashed with power! 🚀 Shift SL to Break Even right now! This is the way.",
    "Precision entry equals victory! 🎯 Shift SL to Break Even and remain relentless! This is the way.",
    "TP1 collected with complete composure! 🛡️ SL to Break Even! This is the way.",
    "Code obeyed, spoils secured! 🎯 TP1 reached. SL moved to BE! This is the way.",
    "Target 1 crushed in the heat of battle! 💥 SL to Break Even. Let the runner pursue TP2! This is the way.",
    "Market structure delivered our rightful prize! 🎯 TP1 hit. Lock in BE status! This is the way.",
    "Another honorable victory! 🎯 TP1 in the books. Move SL to Break Even! This is the way."
]

# ------------------------------------------------------------------------------
# TP2 HIT: Full target hit (1:2 Risk/Reward) — Total Victory
# ------------------------------------------------------------------------------
TP2_MESSAGES = [
    "FULL CONQUEST ACHIEVED! 🚀🔥 1:2 R/R completely liquidated! Maximum bounty claimed! This is the way.",
    "VICTORY IN THE ARENA! 💰 TP2 hit! Full target reached with absolute warrior perfection! This is the way.",
    "MAXIMUM REWARD UNLOCKED! 🎯 TP2 crushed! Time to count the spoils of war! This is the way.",
    "TRIUMPH FOR THE CLAN! 🏆 Full TP2 hit! Absolute masterclass from the Creed! This is the way.",
    "BOOM! 💥 TP2 hit like clockwork! Bank the full bounty and celebrate! This is the way.",
    "Target 2 DESTROYED! 🚀 Pure institutional force delivered! This is the way.",
    "1:2 Risk/Reward conquered! 💰 Full TP2 bagged! Stand tall, warriors! This is the way.",
    "TP2 SMASHED! 🚀 Leave no pips behind! What a magnificent campaign! This is the way.",
    "HAIL THE BOUNTY HUNTERS! 🥂 TP2 hit in full! Glory to the disciplined! This is the way.",
    "Full market expansion complete! 📈 TP2 hit. Close position and honor the win! This is the way.",
    "Clean sweep of the battlefield! 🧹 TP2 hit! That is how we conquer the markets! This is the way.",
    "TP2 Obliterated! 💥 Maximum spoils extracted from the market! This is the way.",
    "TP2 reached! 🚀 Trend Targets Pro delivers total victory once again! This is the way.",
    "TOTAL VICTORY! 🏆 1:2 R/R secured! High & Medium probability setups never fail us! This is the way.",
    "GLORY AND REWARD! 💰 TP2 hit! Take the profits and honor the process! This is the way.",
    "Absolute perfection in battle! 🎯 TP2 reached. Pure algorithmic precision! This is the way.",
    "Treasury overflowing! 💵 TP2 hit in full. Capital grown like a true warrior! This is the way.",
    "TP2 Tagged and Bagged! 💼 Maximum reward achieved on the field! This is the way.",
    "Full Target hit! 🎯 Zero hesitation, pure expansion straight to TP2! This is the way.",
    "WE CONQUERED THE CHARTS! 👨‍🍳 TP2 hit in full! Excellent adherence to the code! This is the way.",
    "TP2 complete! 🚀 Stand up and salute this warrior-grade execution! This is the way.",
    "1:2 R/R delivered on a silver shield! 🛡️ TP2 hit! This is the way.",
    "Account balance rising, rules holding firm! 📈 TP2 fully hit! This is the way.",
    "TP2 Cleared! 🎯 Another successful campaign on the 15M timeframe! This is the way.",
    "Bounty delivered directly to the vault! 🏦 TP2 completely hit! This is the way."
]

# ------------------------------------------------------------------------------
# SL HIT: Stop Loss triggered — Honorable, brave, small scratch, zero fear
# ------------------------------------------------------------------------------
SL_HIT_MESSAGES = [
    "A honorable scratch on our Beskar! 🛑 SL hit, but risk was tightly controlled. On to the next battle! This is the way.",
    "SL taken out, but our spirits stand tall! 🛡️ A loss is just the cost of war. The code remains intact! This is the way.",
    "SL hit! 📉 No fear, no hesitation — disciplined risk management keeps us strong for the big wins! This is the way.",
    "Stop Loss triggered! 🛑 We accept the small loss with honor and prepare for the next setup! This is the way.",
    "SL hit! 🥊 Took the blow on our shield, kept our composure. The edge wins over 100 battles! This is the way.",
    "Stop Loss hit! 🛑 Zero emotion, maximum bravery. Process over outcome every single time! This is the way.",
    "SL hit! 📉 A managed loss is a warrior's discipline. Capital protected for the next campaign! This is the way.",
    "Stop Loss taken! 🛑 The market shifted, but our risk was small and controlled like a true warrior! This is the way.",
    "SL triggered! 🛡️ We respect the Stop Loss like true professionals. Next setup loading! This is the way.",
    "SL hit! 🛑 A minor setback for a major comeback. Stay disciplined and brave! This is the way.",
    "Stop Loss hit! 📉 Rule #1 of the Creed: Protect your capital. Small loss accepted, forward march! This is the way.",
    "SL triggered! 🛑 No anger, no revenge trading! We wait patiently for the next valid signal! This is the way.",
    "SL hit! 🛡️ Proper position sizing means this is just a scratch on our armor. Next signal awaits! This is the way.",
    "Stop Loss taken out! 🛑 Standard cost of high-probability trading. Keep your head high! This is the way.",
    "SL hit! 📉 Risk was capped, rules were honored. Be proud of your execution! This is the way.",
    "SL hit! 🛑 The indicator did its job, the market did its move. We regroup and march on! This is the way.",
    "Stop Loss triggered! 🛡️ Defended the treasury bravely. On to the next session! This is the way.",
    "SL hit! 🛑 True warriors take losses with courage and dignity. We follow the plan! This is the way.",
    "SL taken! 📉 One small scratch will not stop us when 1:2 R/R wins build our empire! This is the way.",
    "Stop Loss hit! 🛑 Kept it tight in Scalp Mode. Minimal damage, absolute discipline! This is the way.",
    "SL hit! 🛡️ Dust off your armor, reset your focus, and await the next signal! This is the way.",
    "SL triggered! 🛑 Part of the path to mastery. We honor the discipline of following the risk plan! This is the way.",
    "Stop Loss hit! 📉 Protect the equity curve — on to the next opportunity! This is the way.",
    "SL hit! 🛑 Strict risk parameters defended us as intended. We stay calm and fearless! This is the way.",
    "SL taken! 🛡️ Capital preserved, mind focused. Ready for the next run! This is the way."
]

# ------------------------------------------------------------------------------
# BE HIT: Break-Even triggered — Zero loss, impenetrable defense, honor intact
# ------------------------------------------------------------------------------
BE_HIT_MESSAGES = [
    "Impenetrable defense! 🛡️ Break-Even hit with zero loss, capital completely safe! We took a free strike at the market! This is the way.",
    "SL at BE triggered! 🤝 No blood spilled, rules followed 100%. That is warrior discipline! This is the way.",
    "Break-Even exit! 🛡️ TP1 was hit, partials banked, and the rest exited at $0 cost! This is the way.",
    "BE hit! ⚖️ Trade closed flat on runner. Profit already locked in from TP1! This is the way.",
    "Break-Even triggered! 🛡️ Code respected, zero drawdown on our treasury. On to the next! This is the way.",
    "BE hit! 🛡️ Protected our capital like an impenetrable fortress. Outstanding bravery! This is the way.",
    "Break-Even closed! 🤝 A free engagement that defended our bottom line completely! This is the way.",
    "BE triggered! 🛡️ Partials in pocket + Zero loss on entry = Pure winning behavior! This is the way.",
    "Break-Even exit! ⚖️ The market counter-attacked, but our shield held firm! This is the way.",
    "BE hit! 🛡️ Capital intact, mindset invincible. Exactly how true warriors manage trades! This is the way.",
    "Break-Even triggered! 🛡️ Zero drawdown on the account balance! This is the way.",
    "BE exit! 🤝 Followed the strategy, saved the treasury. On to the next campaign! This is the way.",
    "Break-Even hit! 🛡️ No harm done, risk managed with absolute mastery! This is the way.",
    "BE triggered! ⚖️ Took profit at TP1 and protected the rest. Excellent tactical work! This is the way.",
    "Break-Even exit! 🛡️ That is why we shift SL to BE on TP1! Discipline always pays! This is the way.",
    "BE hit! 🤝 Free market entry completed with a net positive outcome! This is the way.",
    "Break-Even closed! 🛡️ Account balance remains secure and unyielding! This is the way.",
    "BE triggered! ⚖️ Textbook risk management execution under pressure! This is the way.",
    "Break-Even exit! 🛡️ The market tried to reverse, but our defense was unbreakable! This is the way.",
    "BE hit! 🤝 Net profit secured from TP1, zero loss on the remaining position! This is the way.",
    "Break-Even closed! 🛡️ Masterclass in defensive tactical trade management! This is the way.",
    "BE triggered! ⚖️ Treasury preserved to fight another session with full strength! This is the way.",
    "Break-Even exit! 🛡️ Zero regret, 100% execution courage and precision! This is the way.",
    "BE hit! 🤝 The rule-following mindset triumphs over fear once again! This is the way.",
    "Break-Even closed! 🛡️ Safe and honorable exit. Ready for the next high-probability setup! This is the way."
]

# ==============================================================================
# SESSION FILTERING (ZAMBIA / CAT TIME)
# ==============================================================================
def is_in_session(session_type):
    """
    Checks if current Zambia / Central Africa Time (CAT) falls within active trading sessions.
    - ASIAN: 02:00 to 07:42 CAT
    - NEW_YORK: 15:30 to 21:45 CAT
    """
    now_cat = datetime.now(ZAMBIA_TZ)
    time_min = now_cat.hour * 60 + now_cat.minute

    if session_type == "ASIAN":
        return 120 <= time_min <= 462
    elif session_type == "NEW_YORK":
        return 930 <= time_min <= 1305
    return False

# ==============================================================================
# INDICATOR ENGINE (EXACT PINE SCRIPT REPLICATION)
# ==============================================================================
def calculate_indicators(df_15m, df_1h):
    """
    Calculates HTF EMA 50, Supertrend (10, 3.0), ADX (14), and Candle Body Ratio.
    """
    # 1. Higher Timeframe (1H) EMA 50
    df_1h['HTF_EMA'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
    
    # Merge 1H EMA onto 15M candles using forward fill
    df_15m = pd.merge_asof(
        df_15m.sort_index(),
        df_1h[['HTF_EMA']].sort_index(),
        left_index=True,
        right_index=True,
        direction='backward'
    )

    high, low, close, open_p = df_15m['High'], df_15m['Low'], df_15m['Close'], df_15m['Open']

    # 2. Classic Supertrend (10, 3.0)
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
    st_trend = pd.Series(1, index=df_15m.index)

    for i in range(1, len(df_15m)):
        final_ub.iloc[i] = basic_ub.iloc[i] if (basic_ub.iloc[i] < final_ub.iloc[i-1] or close.iloc[i-1] > final_ub.iloc[i-1]) else final_ub.iloc[i-1]
        final_lb.iloc[i] = basic_lb.iloc[i] if (basic_lb.iloc[i] > final_lb.iloc[i-1] or close.iloc[i-1] < final_lb.iloc[i-1]) else final_lb.iloc[i-1]

        if st_trend.iloc[i-1] == 1:
            st_trend.iloc[i] = -1 if close.iloc[i] < final_lb.iloc[i] else 1
        else:
            st_trend.iloc[i] = 1 if close.iloc[i] > final_ub.iloc[i] else -1

    df_15m['ST_Trend'] = st_trend

    # 3. ADX (14)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df_15m.index).ewm(alpha=1/14, adjust=False).mean() / atr14)
    minus_di = 100 * (pd.Series(minus_dm, index=df_15m.index).ewm(alpha=1/14, adjust=False).mean() / atr14)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df_15m['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()

    # 4. Candle Body Ratio
    df_15m['BodyRatio'] = (close - open_p).abs() / np.maximum(high - low, 0.0001)

    return df_15m

# ==============================================================================
# DISPATCH MESSAGES (DISCORD & TELEGRAM)
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

    for name, (ticker, session_type) in SYMBOLS.items():
        # Fetch 15M and 1H market data
        df_15m = yf.download(tickers=ticker, period="5d", interval="15m", progress=False)
        df_1h = yf.download(tickers=ticker, period="10d", interval="1h", progress=False)

        if df_15m.empty or len(df_15m) < 200 or df_1h.empty:
            continue

        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = df_15m.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        df = calculate_indicators(df_15m, df_1h)

        latest_bar = df.iloc[-2]  # Last closed 15M candle
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

            # LONG Active Trade Evaluation
            if direction == "BUY":
                # Check TP1 Hit
                if not trade['tp1_hit'] and high_p >= tp1:
                    trade['tp1_hit'] = True
                    trade['sl_moved_to_be'] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name}",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                # Check TP2 Hit
                elif trade['tp1_hit'] and high_p >= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name}",
                        f"{random.choice(TP2_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP2 (1:2):* `{tp2:.2f}`",
                        color_code=65280
                    )
                    del state[name]
                    save_state(state)
                    continue

                # Check SL / BE Hit
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

            # SHORT Active Trade Evaluation
            elif direction == "SELL":
                # Check TP1 Hit
                if not trade['tp1_hit'] and low_p <= tp1:
                    trade['tp1_hit'] = True
                    trade['sl_moved_to_be'] = True
                    save_state(state)
                    send_notification(
                        f"🎯 TP1 HIT — {name}",
                        f"{random.choice(TP1_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP1:* `{tp1:.2f}`\n• *New SL:* `{entry:.2f} (Break Even)`",
                        color_code=65280
                    )

                # Check TP2 Hit
                elif trade['tp1_hit'] and low_p <= tp2:
                    send_notification(
                        f"🚀 FULL TP2 HIT — {name}",
                        f"{random.choice(TP2_MESSAGES)}\n\n• *Entry:* `{entry:.2f}`\n• *TP2 (1:2):* `{tp2:.2f}`",
                        color_code=65280
                    )
                    del state[name]
                    save_state(state)
                    continue

                # Check SL / BE Hit
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
        # 2. CHECK SESSION & GENERATE NEW WARRIOR SIGNALS
        # ----------------------------------------------------------------------
        if not is_in_session(session_type):
            continue

        curr_st, prev_st = df['ST_Trend'].iloc[-2], df['ST_Trend'].iloc[-3]
        htf_ema = float(latest_bar['HTF_EMA'])
        adx_val = float(latest_bar['ADX'])
        body_ratio = float(latest_bar['BodyRatio'])

        buy_flip = (prev_st == -1) and (curr_st == 1)
        sell_flip = (prev_st == 1) and (curr_st == -1)

        if not (buy_flip or sell_flip):
            continue

        # Probability Scoring Logic
        htf_ok = (close_p > htf_ema) if buy_flip else (close_p < htf_ema)
        adx_ok = adx_val >= 20.0
        body_ok = body_ratio >= 0.50
        consolidating = adx_val < 15.0

        score = (1 if htf_ok else 0) + (1 if adx_ok else 0) + (1 if body_ok else 0)

        # Force LOW (1) if Consolidating
        tier = 1 if consolidating else (3 if score >= 3 else (2 if score == 2 else 1))

        # FILTER: ONLY MEDIUM (2) AND HIGH (3) PROBABILITY SETUPS
        if tier < 2:
            continue

        tier_txt = "HIGH PROBABILITY WARRIOR SETUP ⭐⭐⭐" if tier == 3 else "MEDIUM PROBABILITY WARRIOR SETUP ⭐⭐"
        direction = "BUY" if buy_flip else "SELL"

        # Scalp Mode SL: Swing Low/High of 3 candles preceding the trigger candle
        lookback_bars = df.iloc[-5:-2]
        sl_px = float(lookback_bars['Low'].min()) if buy_flip else float(lookback_bars['High'].max())

        risk = abs(close_p - sl_px)
        tp1_px = close_p + risk if buy_flip else close_p - risk
        tp2_px = close_p + (risk * 2.0) if buy_flip else close_p - (risk * 2.0)

        # Save New Active Trade to State
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

        # Dispatch Mandalorian Setup Alert
        emoji = "⚔️ 🟢" if direction == "BUY" else "⚔️ 🔴"
        color = 5763719 if direction == "BUY" else 15548997

        msg_body = (
            f"{emoji} *{direction} SIGNAL CONFIRMED on {name} (15M)*\n"
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