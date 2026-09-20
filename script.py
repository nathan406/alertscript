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
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550985326770528266/9oOJm2yH7o7RLaQBBjeH7AW9_Q31tAKBu2ae8w3dk1GIUuFY0NRtlm3AyLv8RQb2vouZ"
TELEGRAM_BOT_TOKEN = "8946173658:AAGw-lqdxlgmraOcQyJbyHTlCL7P1dxWbW4"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # Replace with your chat ID

STATE_FILE = "active_trades.json"
ZAMBIA_TZ = pytz.timezone("Africa/Lusaka")

# Symbol mapping: Name -> (Yahoo Ticker, Session Type)
SYMBOLS = {
    "XAUUSD": ("GC=F", "ASIAN"),      # TVC / Futures Gold equivalent
    "USTEC":  ("NQ=F", "NEW_YORK"),   # IC Markets Nasdaq equivalent
    "GER40":  ("^GDAXI", "NEW_YORK"), # Forex.com DAX equivalent
    "BTCUSD": ("BTC-USD", "NEW_YORK") # Bitstamp BTC equivalent
}

# ==============================================================================
# DYNAMIC MESSAGES (25+ Variations Each)
# ==============================================================================
TP1_MESSAGES = [
    "A PIP A DAY KEEPS POVERTY AWAY! 🎯 TP1 smashed! Lock in partials and move SL to BREAK EVEN!",
    "TP1 secured! 💰 Risk removed from the table. Move that Stop Loss to Entry now!",
    "BAM! TP1 hit like a freight train! 🚀 Move SL to Break Even and let the rest run!",
    "Pure institutional precision! 🎯 TP1 achieved. SL adjusted to Break Even. Free trade activated!",
    "ZedSauce FA rules followed to the letter! TP1 banked. Protect the account — SL to BE!",
    "Money in the bag! 💼 TP1 hit. Move your stop loss to break even immediately!",
    "Executing like a sniper! 🎯 TP1 hit. SL to BE. We ride risk-free now!",
    "Target 1 reached! 🚀 Partial profits banked. Move SL to break even!",
    "The 15M chart delivers! 🎯 TP1 hit. SL shifted to entry level!",
    "Easy work! TP1 hit cleanly. 💰 Move SL to Break Even and sit back!",
    "Chart read like a book! 📖 TP1 secured. Adjust SL to Break Even!",
    "Zero emotion, pure execution! 🎯 TP1 hit. SL to BE time!",
    "TP1 tagged! 🎯 Half the risk off, all the confidence intact. SL to Break Even!",
    "Pips collected! 💵 TP1 reached. Shift SL to Break Even!",
    "Green on the screen! 🟢 TP1 hit. SL moved to Break Even — zero risk mode!",
    "Flawless execution! 🎯 TP1 bagged. Move SL to entry price!",
    "Market respects the setup! 🎯 TP1 hit. Move SL to Break Even!",
    "Pockets heavier! 💰 TP1 hit. Move SL to BE and protect your gain!",
    "Boom! TP1 smashed. 🚀 Shift SL to Break Even right now!",
    "Precision entry = Easy TP1! 🎯 Shift SL to Break Even and stay disciplined!",
    "TP1 collected with zero stress! ☕ SL to Break Even!",
    "Rules obeyed, pips secured! 🎯 TP1 reached. SL moved to BE!",
    "Target 1 crushed! 💥 SL to Break Even. Let runner go to TP2!",
    "Structure delivered! 🎯 TP1 hit. Lock in BE status!",
    "Another clean hit! 🎯 TP1 in the books. Move SL to Break Even!"
]

TP2_MESSAGES = [
    "FULL TP2 SMASHED! 🚀🔥 1:2 R/R completely liquidated! 'A PIP A DAY KEEPS POVERTY AWAY!'",
    "JACKPOT! 💰 TP2 hit! Full target reached with absolute perfection!",
    "MAXIMUM REWARD UNLOCKED! 🎯 TP2 crushed! Time to count the profits!",
    "VICTORY! 🏆 Full TP2 hit! Absolute masterclass from Trend Targets Pro!",
    "BOOM! 💥 TP2 hit like a clockwork! Bank the full profit and celebrate!",
    "Target 2 DESTROYED! 🚀 Pure institutional price action delivered!",
    "1:2 Risk/Reward completed! 💰 Full TP2 bagged! Great trading team!",
    "TP2 SMASHED! 🚀 Leave no pips behind! What a magnificent trade!",
    "CHEERS TO THE PIP COLLECTORS! 🥂 TP2 hit in full!",
    "Full expansion complete! 📈 TP2 hit. Close position and enjoy the weekend energy!",
    "Clean sweep! 🧹 TP2 hit! That is how we trade at ZedSauce Forex Academy!",
    "TP2 Obliterated! 💥 Maximum pips extracted from the market!",
    "TP2 reached! 🚀 Trend Targets Pro does it again. Flawless setup!",
    "FULL WIN! 🏆 1:2 R/R secured! High/Medium probability setups never lie!",
    "BOOM SHAKALAKA! 💰 TP2 hit! Take the money and run!",
    "Absolute perfection! 🎯 TP2 reached. Pure algorithmic execution!",
    "Pips galore! 💵 TP2 hit in full. Capital grown like a champ!",
    "TP2 Tagged and Bagged! 💼 Maximum reward achieved!",
    "Full Target hit! 🎯 Zero drawdown, pure expansion to TP2!",
    "WE COOKED! 👨‍🍳 TP2 hit in full! Excellent rule adherence!",
    "TP2 complete! 🚀 Stand up and applaud this trade execution!",
    "1:2 R/R delivered on a silver platter! 🥈 TP2 hit!",
    "Account growing, rules holding! 📈 TP2 fully hit!",
    "TP2 Cleared! 🎯 Another successful campaign on the 15M timeframe!",
    "Pips delivered to the vault! 🏦 TP2 completely hit!"
]

SL_HIT_MESSAGES = [
    "Stop Loss hit! 🛑 Part of the game — risk was strictly managed at scalp levels. On to the next!",
    "SL taken out! 🛡️ Remember: A loss is just the cost of doing business. Rules were followed!",
    "SL hit! 📉 No worries at all — disciplined risk management keeps us alive for the big wins!",
    "Stop Loss triggered! 🛑 We accept the small loss gracefully and wait for the next High/Medium setup.",
    "SL hit! 🥊 Took the punch, kept the discipline. The edge wins over 100 trades!",
    "Stop Loss hit! 🛑 Zero emotion. Process over outcome every single time!",
    "SL hit! 📉 Managed loss = Healthy trading. Capital protected for the next signal!",
    "Stop Loss taken! 🛑 The market gave a slight twist, but our risk was small and controlled.",
    "SL triggered! 🛡️ We respect the Stop Loss like true professionals. Next setup loading!",
    "SL hit! 🛑 A small setback for a major comeback. Stay disciplined!",
    "Stop Loss hit! 📉 Rule #1: Protect capital. Small loss accepted, moving forward!",
    "SL triggered! 🛑 No revenge trading! We wait patiently for the next valid window.",
    "SL hit! 🛡️ Proper position sizing means this is just a scratch. Next signal awaits!",
    "Stop Loss taken out! 🛑 Standard cost of probability trading. Head up!",
    "SL hit! 📉 Risk was capped, rules were honored. Proud of the discipline!",
    "SL hit! 🛑 The indicator did its job, the market did its move. We execute and move on!",
    "Stop Loss triggered! 🛡️ Defended the account. On to the next trading session!",
    "SL hit! 🛑 Professional traders take losses with a smile. We follow the plan!",
    "SL taken! 📉 1 loss won't break us when 1:2 R/R wins build us. Next!",
    "Stop Loss hit! 🛑 Kept it tight in Scalp Mode. Minimal damage, maximum discipline!",
    "SL hit! 🛡️ Dust off, reset, and wait for the next high-probability setup!",
    "SL triggered! 🛑 Part of the process. We applaud following the risk plan!",
    "Stop Loss hit! 📉 Protect the equity curve — on to the next opportunity!",
    "SL hit! 🛑 Strict risk parameters worked as intended. We stay composed!",
    "SL taken! 🛡️ Capital preserved, mind clear. Ready for the next run!"
]

BE_HIT_MESSAGES = [
    "Break-Even hit! 🛡️ Zero loss, capital completely safe! We took a free shot at the market!",
    "SL at BE triggered! 🤝 No money lost, rules followed 100%. That's professional trading!",
    "Break-Even exit! 🛡️ TP1 was hit, partials banked, and the rest exited at $0 cost!",
    "BE hit! ⚖️ Trade closed flat on runner. Profit already locked in from TP1!",
    "Break-Even triggered! 🛡️ Rules respected, zero draw on equity. On to the next!",
    "BE hit! 🛡️ Protected our capital like an institution. Outstanding discipline!",
    "Break-Even closed! 🤝 A free trade that protected our bottom line!",
    "BE triggered! 🛡️ Partials in pocket + Zero loss on entry = Winning behavior!",
    "Break-Even exit! ⚖️ Market turned back, but our defense was impenetrable!",
    "BE hit! 🛡️ Capital intact, mindset strong. Exactly how we manage trades!",
    "Break-Even triggered! 🛡️ Zero drawdown on the account balance!",
    "BE exit! 🤝 Followed the prompt, saved the capital. On to the next session!",
    "Break-Even hit! 🛡️ No harm done, risk managed perfectly!",
    "BE triggered! ⚖️ Took profit at TP1 and protected the rest. Solid work!",
    "Break-Even exit! 🛡️ That is why we move SL to BE on TP1! Discipline pays!",
    "BE hit! 🤝 Free market entry completed with net positive outcome!",
    "Break-Even closed! 🛡️ Account balance remains secure and protected!",
    "BE triggered! ⚖️ Textbook risk management execution!",
    "Break-Even exit! 🛡️ The market tried to reverse, but our shield was up!",
    "BE hit! 🤝 Net profit secured from TP1, zero loss on remainder!",
    "Break-Even closed! 🛡️ Masterclass in trade management!",
    "BE triggered! ⚖️ Capital preserved to fight another session!",
    "Break-Even exit! 🛡️ Zero regret, 100% execution precision!",
    "BE hit! 🤝 The rule-following mindset triumphs again!",
    "Break-Even closed! 🛡️ Safe and sound exit. Ready for the next setup!"
]

# ==============================================================================
# SESSION FILTERING (ZAMBIA / CAT TIME)
# ==============================================================================
def is_in_session(session_type):
    now_cat = datetime.now(ZAMBIA_TZ)
    time_min = now_cat.hour * 60 + now_cat.minute

    if session_type == "ASIAN":
        # 02:00 (120 min) to 07:42 (462 min) CAT
        return 120 <= time_min <= 462
    elif session_type == "NEW_YORK":
        # 15:30 (930 min) to 21:45 (1305 min) CAT
        return 930 <= time_min <= 1305
    return False

# ==============================================================================
# INDICATOR ENGINE (EXACT PINE SCRIPT REPLICATION)
# ==============================================================================
def calculate_indicators(df_15m, df_1h):
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
    # Discord
    if DISCORD_WEBHOOK_URL:
        payload = {
            "content": "@everyone",
            "embeds": [{
                "title": title,
                "description": message_body,
                "color": color_code,
                "footer": {"text": "Trend Targets Pro • ZedSauce Forex Academy"}
            }]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            print(f"Discord error: {e}")

    # Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        full_msg = f"*{title}*\n\n{message_body}\n\n_ZedSauce Forex Academy • Zambia_"
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": full_msg, "parse_mode": "Markdown"},
                timeout=10
            )
        except Exception as e:
            print(f"Telegram error: {e}")

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
        # 1. Fetch market data
        df_15m = yf.download(tickers=ticker, period="5d", interval="15m", progress=False)
        df_1h = yf.download(tickers=ticker, period="10d", interval="1h", progress=False)

        if df_15m.empty or len(df_15m) < 200 or df_1h.empty:
            continue

        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = df_15m.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        df = calculate_indicators(df_15m, df_1h)

        latest_bar = df.iloc[-2]  # Last closed bar
        close_p = float(latest_bar['Close'])
        high_p = float(latest_bar['High'])
        low_p = float(latest_bar['Low'])

        # Check Active Trades for Outcome Monitoring (TP1, TP2, SL, BE)
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

        # 2. Check Session Rules for NEW Signal Generation
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

        tier_txt = "HIGH PROBABILITY ⭐⭐⭐" if tier == 3 else "MEDIUM PROBABILITY ⭐⭐"
        direction = "BUY" if buy_flip else "SELL"

        # Scalp Mode SL: Swing Low/High of 3 candles before trigger candle
        lookback_bars = df.iloc[-5:-2]
        sl_px = float(lookback_bars['Low'].min()) if buy_flip else float(lookback_bars['High'].max())

        risk = abs(close_p - sl_px)
        tp1_px = close_p + risk if buy_flip else close_p - risk
        tp2_px = close_p + (risk * 2.0) if buy_flip else close_p - (risk * 2.0)

        # Record New Active Trade
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

        # Send Setup Alert
        emoji = "🟢" if direction == "BUY" else "🔴"
        color = 5763719 if direction == "BUY" else 15548997

        msg_body = (
            f"{emoji} *{direction} Signal Confirmed on {name} (15M)*\n"
            f"• *Tier:* `{tier_txt}`\n\n"
            f"• *Entry Price:* `{close_p:.2f}`\n"
            f"• *Stop Loss (Scalp):* `{sl_px:.2f}`\n"
            f"• *TP1 (1:1 R/R):* `{tp1_px:.2f}`\n"
            f"• *TP2 (1:2 R/R):* `{tp2_px:.2f}`\n\n"
            f"• *ADX Strength:* `{adx_val:.1f}` | *Candle Body:* `{body_ratio*100:.1f}%`"
        )
        send_notification(f"🚨 TREND TARGETS PRO — {name}", msg_body, color_code=color)

if __name__ == "__main__":
    run_scanner()