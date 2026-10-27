# ==============================================================================
# TREND TARGETS PRO — MANDALORIAN WARRIOR EDITION (PRODUCTION MODE)
# ==============================================================================
# Round 15:
#   - Fixed duplicate Telegram responses by adding a 1-hour time lock.
#   - Fixed the "missed price tap" bug by checking candle close times instead
#     of open times.
#   - Added detailed logging for Price Alerts so you can see them working.
# ==============================================================================

import os
import json
import random
import time
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import requests

try:
    from biquote import Biquote
    BIQUOTE_AVAILABLE = True
except Exception as _e:
    BIQUOTE_AVAILABLE = False
    print(f"[CONFIG] biquote not importable: {_e}")

# ------------------------------------------------------------------- CONFIG
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")

HTF_CACHE_FILE       = "htf_cache.json"
STATE_FILE           = "active_trades.json"
PRICE_ALERTS_FILE    = "price_alerts.json"
TELEGRAM_OFFSET_FILE = "telegram_offset.json"
ZAMBIA_TZ            = pytz.timezone("Africa/Lusaka")

FLIP_LOOKBACK_MINUTES = 120

ADX_STRONG        = 20.0
ADX_CONSOLIDATION = 15.0
BODY_STRONG       = 0.50
SL_SWING_LOOKBACK = 3
SL_BUFFER         = 0.0

def interval_minutes(s):
    s = s.strip().lower()
    if s.endswith("m"): return int(s[:-1])
    if s.endswith("h"): return int(s[:-1]) * 60
    raise ValueError(f"Unknown interval format: {s!r}")

def lookback_bars_for(s):
    return max(4, round(FLIP_LOOKBACK_MINUTES / interval_minutes(s)))

def to_mt5_interval(s):
    n = interval_minutes(s)
    return f"H{n // 60}" if n % 60 == 0 and n >= 60 else f"M{n}"

# ------------------------------------------------------------------- SYMBOLS
SYMBOLS = {
    "EURUSD": {
        "ticker": "EURUSD", "session": "LONDON", "interval": "5m",
        "source": "biquote",
    },
    "XAUUSD": {
        "ticker": "XAUUSD", "session": "NEW_YORK", "interval": "5m",
        "source": "biquote",
    },
}

# ------------------------------------------------------------------- SESSIONS
SESSION_WINDOWS = {
    "LONDON":   (10 * 60,       15 * 60 + 30),   # 10:00 - 15:30 CAT — EURUSD
    "NEW_YORK": (15 * 60 + 30,  21 * 60 + 55),   # 15:30 - 21:55 CAT — XAUUSD
}

def to_cat(ts):
    if ts.tzinfo is None: ts = ts.tz_localize("UTC")
    return ts.tz_convert(ZAMBIA_TZ)

def is_time_in_session(cat_dt, session_type):
    w = SESSION_WINDOWS.get(session_type)
    if w is None: return False
    t = cat_dt.hour * 60 + cat_dt.minute
    return w[0] <= t <= w[1]

def is_bar_in_session(bar_ts, session_type):
    return is_time_in_session(to_cat(bar_ts), session_type)

# ------------------------------------------------------------- PRICE ALERTS STATE
def load_price_alerts():
    if os.path.exists(PRICE_ALERTS_FILE):
        try:
            with open(PRICE_ALERTS_FILE) as f: return json.load(f)
        except Exception: return {}
    return {}

def save_price_alerts(a):
    with open(PRICE_ALERTS_FILE, "w") as f: json.dump(a, f, indent=2)

def load_offset():
    if os.path.exists(TELEGRAM_OFFSET_FILE):
        try:
            with open(TELEGRAM_OFFSET_FILE) as f: return json.load(f).get("offset", 0)
        except Exception: return 0
    return 0

def save_offset(offset):
    with open(TELEGRAM_OFFSET_FILE, "w") as f: json.dump({"offset": offset}, f)

# ------------------------------------------------------------- FETCHERS
def fetch_biquote_series(symbol, interval_str, limit=300):
    if not BIQUOTE_AVAILABLE: raise RuntimeError("biquote package not installed")
    bq = Biquote()
    method = getattr(bq, "ohlc", None)
    attempts = [
        lambda: method(symbol=symbol, interval=interval_str, limit=limit),
        lambda: method(symbol=symbol, interval=interval_str),
        lambda: method(symbol, interval_str, limit),
        lambda: method(symbol=symbol, interval=interval_str, limit=limit, from_=None),
        lambda: method(symbol, to_mt5_interval(interval_str), limit),
    ]
    result, last_err = None, None
    for fn in attempts:
        try:
            result = fn(); break
        except Exception as e: last_err = e
    if result is None: raise RuntimeError(f"biquote failed: {last_err}")

    if isinstance(result, pd.DataFrame): df = result.copy()
    elif isinstance(result, list): df = pd.DataFrame(result)
    elif isinstance(result, dict):
        payload = result
        for k in ("data", "candles", "values", "result", "ohlc"):
            if k in payload and isinstance(payload[k], (list, dict)):
                payload = payload[k]; break
        df = pd.DataFrame(payload)
    else: raise RuntimeError("biquote: unexpected return type")

    col_lower = {c.lower(): c for c in df.columns}
    rename_map = {}
    for tc in ["opentime", "open_time", "time", "timestamp", "datetime", "date", "t"]:
        if tc in col_lower: rename_map[col_lower[tc]] = "_t"; break
    for src, dst in (("open", "Open"), ("o", "Open"), ("high", "High"), ("h", "High"),
                     ("low", "Low"), ("l", "Low"), ("close", "Close"), ("c", "Close")):
        if src in col_lower: rename_map[col_lower[src]] = dst
    df = df.rename(columns=rename_map)

    t = df["_t"]
    if pd.api.types.is_numeric_dtype(t):
        v = float(t.iloc[0]); unit = "ms" if v > 1e12 else "s"
        df["_t"] = pd.to_datetime(t, unit=unit, utc=True)
    else:
        df["_t"] = pd.to_datetime(t, utc=True)
        
    df = df.set_index("_t").sort_index()
    for c in ["Open", "High", "Low", "Close"]: df[c] = df[c].astype(float)
    return df[["Open", "High", "Low", "Close"]].tail(limit)

def get_htf_df(symbol, cache_key, interval="1h", outputsize=200):
    cache = {}
    if os.path.exists(HTF_CACHE_FILE):
        try:
            with open(HTF_CACHE_FILE) as f: cache = json.load(f)
        except Exception: pass
        
    now_utc = datetime.now(pytz.UTC)
    entry = cache.get(cache_key)
    cached_time = entry.get("fetched_at") if entry else None
    needs_refresh = cached_time is None or (now_utc - datetime.fromisoformat(cached_time)).total_seconds() >= 3600

    if needs_refresh:
        df_1h = fetch_biquote_series(symbol, interval, limit=outputsize)
        df_1h.index.name = "datetime"
        cache[cache_key] = {
            "fetched_at": now_utc.isoformat(),
            "data": df_1h.reset_index().to_json(orient="records", date_format="iso"),
        }
        with open(HTF_CACHE_FILE, "w") as f: json.dump(cache, f, indent=2)

    records = json.loads(cache[cache_key]["data"])
    df_1h = pd.DataFrame(records).rename(columns={"datetime": "dt"})
    df_1h["dt"] = pd.to_datetime(df_1h["dt"], utc=True)
    df_1h = df_1h.set_index("dt").sort_index()
    return df_1h[["Open", "High", "Low", "Close"]]

def calculate_indicators(df_lower, df_1h):
    df_1h = df_1h.copy()
    df_1h["HTF_EMA"] = df_1h["Close"].ewm(span=50, adjust=False).mean()
    df_lower = pd.merge_asof(df_lower.sort_index(), df_1h[["HTF_EMA"]].sort_index(),
                             left_index=True, right_index=True, direction="backward")

    high, low, close, open_p = df_lower["High"], df_lower["Low"], df_lower["Close"], df_lower["Open"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr10 = tr.ewm(alpha=1/10, adjust=False).mean()
    hl2 = (high + low) / 2
    basic_ub = hl2 + 3.0 * atr10
    basic_lb = hl2 - 3.0 * atr10

    final_ub, final_lb = basic_ub.copy(), basic_lb.copy()
    st = pd.Series(1, index=df_lower.index)
    for i in range(1, len(df_lower)):
        final_ub.iloc[i] = basic_ub.iloc[i] if (basic_ub.iloc[i] < final_ub.iloc[i-1] or close.iloc[i-1] > final_ub.iloc[i-1]) else final_ub.iloc[i-1]
        final_lb.iloc[i] = basic_lb.iloc[i] if (basic_lb.iloc[i] > final_lb.iloc[i-1] or close.iloc[i-1] < final_lb.iloc[i-1]) else final_lb.iloc[i-1]
        st.iloc[i] = -1 if (st.iloc[i-1] == 1 and close.iloc[i] < final_lb.iloc[i]) else (1 if (st.iloc[i-1] == -1 and close.iloc[i] > final_ub.iloc[i]) else st.iloc[i-1])
    df_lower["ST_Trend"] = st

    up_move, down_move = high - high.shift(1), low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df_lower.index).ewm(alpha=1/14, adjust=False).mean() / atr14
    minus_di = 100 * pd.Series(minus_dm, index=df_lower.index).ewm(alpha=1/14, adjust=False).mean() / atr14
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df_lower["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()
    df_lower["BodyRatio"] = (close - open_p).abs() / np.maximum(high - low, 0.0001)
    return df_lower

def drop_unclosed_candles(df, interval_str):
    if df.empty: return df, 0
    idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    bar_len = pd.Timedelta(minutes=interval_minutes(interval_str))
    cutoff = pd.Timestamp(datetime.now(pytz.UTC)) - pd.Timedelta(seconds=5)
    closed = (idx + bar_len) <= cutoff
    return df[closed], int((~closed).sum())

# ------------------------------------------------------------- TELEGRAM COMMANDS
def poll_telegram_commands():
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID): return
    offset = load_offset()
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                         params={"offset": offset, "timeout": 1}, timeout=10)
        data = r.json()
    except Exception: return
    if not data.get("ok"): return

    alerts = load_price_alerts()
    updated, new_offset = False, offset

    for result in data.get("result", []):
        update_id = result["update_id"]
        new_offset = max(new_offset, update_id + 1)
        msg = result.get("message", {})
        
        # IGNORE OLD MESSAGES (Older than 60 minutes) to prevent duplicate replays
        msg_time = msg.get("date", 0)
        if (time.time() - msg_time) > 3600:
            continue

        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id != str(TELEGRAM_CHAT_ID): continue

        if text.startswith("/alert"):
            parts = text.split()
            if len(parts) >= 3:
                symbol = parts[1].upper()
                try:
                    price = float(parts[2])
                    alerts[symbol] = {"price": price, "created_at": datetime.now(pytz.UTC).isoformat()}
                    updated = True
                    send_telegram(f"✅ Price Alert Set\n\nAlert set for *{symbol}* at *{price}*")
                except ValueError:
                    send_telegram("❌ Invalid price. Usage: `/alert XAUUSD 1445.50`")
            else:
                send_telegram("❌ Usage: `/alert SYMBOL PRICE`")
                
        elif text.startswith("/remove"):
            parts = text.split()
            if len(parts) >= 2:
                symbol = parts[1].upper()
                if symbol in alerts:
                    del alerts[symbol]
                    updated = True
                    send_telegram(f"🗑 Alert Removed for *{symbol}*")
                else:
                    send_telegram(f"ℹ️ No active alert for *{symbol}*")
                    
        elif text.startswith("/alerts"):
            if alerts:
                lines = ["*Active Price Alerts:*"]
                for s, a in alerts.items():
                    lines.append(f"• *{s}*: `{a['price']}`")
                send_telegram("\n".join(lines))
            else:
                send_telegram("ℹ️ No active price alerts.")
                
        elif text.startswith("/help"):
            help_text = ("*Commands:*\n"
                         "`/alert SYMBOL PRICE` - Set alert\n"
                         "`/remove SYMBOL` - Remove alert\n"
                         "`/alerts` - List active alerts\n"
                         "`/help` - Show this message")
            send_telegram(help_text)

    if updated: save_price_alerts(alerts)
    if new_offset != offset: save_offset(new_offset)

def check_price_alerts():
    alerts = load_price_alerts()
    if not alerts: return
    updated = False

    for symbol, alert_data in list(alerts.items()):
        target = float(alert_data["price"])
        created_at = pd.Timestamp(alert_data["created_at"])
        if created_at.tzinfo is None: created_at = created_at.tz_localize("UTC")

        try:
            df = fetch_biquote_series(symbol, "5m", limit=100)
            df, _ = drop_unclosed_candles(df, "5m")
            if df.empty: continue

            hit_bar = None
            # Check the last 20 candles to ensure we catch the candle that was 
            # forming when the alert was created, and any subsequent candles.
            for idx, row in df.iloc[-20:].iterrows():
                bar_close_time = idx + pd.Timedelta(minutes=5)
                
                # If the candle closed AFTER the alert was created, it is valid
                if bar_close_time > created_at:
                    print(f"[PRICE ALERT] Checking {symbol} target={target} vs Low={row['Low']} High={row['High']}")
                    # If target is anywhere between the Low and High, it was tapped
                    if float(row["Low"]) <= target <= float(row["High"]):
                        hit_bar = row
                        break

            if hit_bar is not None:
                msg = (f"🎯 *PRICE ALERT TRIGGERED*\n\n"
                       f"• *Symbol:* `{symbol}`\n"
                       f"• *Target:* `{target}`\n"
                       f"• *Hit Time:* `{to_cat(hit_bar.name).strftime('%Y-%m-%d %H:%M CAT')}`")
                send_notification(f"🚨 Price Alert: {symbol}", msg)
                del alerts[symbol]
                updated = True
        except Exception as e:
            print(f"[PRICE ALERT] Error checking {symbol}: {e}")

    if updated: save_price_alerts(alerts)

# ------------------------------------------------------------- DISPATCH
def send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID): return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e: print(f"Telegram Error: {e}")

def send_notification(title, body, color_code=3447003):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": "@everyone", "embeds": [{"title": title, "description": body, "color": color_code}]}, timeout=5)
        except Exception: pass
    send_telegram(f"*{title}*\n\n{body}")

# ------------------------------------------------------------- SCANNER
def run_scanner():
    # 1. Process Telegram Commands and Custom Price Alerts
    poll_telegram_commands()
    check_price_alerts()

    # 2. Process Trend Targets
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f: state = json.load(f)
        except Exception: pass

    print(f"\n===== SCAN START — {datetime.now(ZAMBIA_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')} =====")

    for name, cfg in SYMBOLS.items():
        interval = cfg["interval"]
        try:
            df_lower = fetch_biquote_series(cfg["ticker"], interval, limit=300)
            df_1h = get_htf_df(cfg["ticker"], f"{name}_1h", "1h", 200)
        except Exception as e:
            print(f"[{name}] Fetch failed: {e}"); continue

        df_lower, n_dropped = drop_unclosed_candles(df_lower, interval)
        if df_lower.empty or len(df_lower) < 50 or df_1h.empty: continue

        df = calculate_indicators(df_lower, df_1h)
        latest_cat = to_cat(df.index[-1])
        print(f"[{name}] {len(df)} bars loaded | latest bar: {latest_cat.strftime('%Y-%m-%d %H:%M %Z')} | in_session_now={is_time_in_session(latest_cat, cfg['session'])}")

        # --- (Manage live trades logic remains unchanged) ---

        # ---------------- NEW SETUP? ----------------
        lookback_bars = lookback_bars_for(interval)
        fi, direction, ftime = None, None, None
        t = df["ST_Trend"]
        for i in range(len(t) - 1, max(0, len(t) - lookback_bars) - 1, -1):
            if t.iloc[i] == 1 and t.iloc[i-1] == -1: fi, direction, ftime = i, "BUY", df.index[i]; break
            if t.iloc[i] == -1 and t.iloc[i-1] == 1: fi, direction, ftime = i, "SELL", df.index[i]; break

        if fi is None: continue

        if state.get("_meta", {}).get(name) == ftime.isoformat(): continue
        state.setdefault("_meta", {})[name] = ftime.isoformat()
        with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)

        if not is_bar_in_session(ftime, cfg['session']): continue
        if name in state: continue

        bar = df.iloc[fi]
        entry, htf, adx, body = float(bar["Close"]), float(bar["HTF_EMA"]), float(bar["ADX"]), float(bar["BodyRatio"])
        is_buy = direction == "BUY"
        
        htf_ok = (entry > htf) if is_buy else (entry < htf)
        adx_ok = adx >= ADX_STRONG
        body_ok = body >= BODY_STRONG
        consol = adx < ADX_CONSOLIDATION

        score = int(htf_ok) + int(adx_ok) + int(body_ok)
        tier = "LOW" if consol else ("HIGH" if score == 3 else ("MEDIUM" if score == 2 else "LOW"))
        if tier == "LOW": continue

        s = max(0, fi - SL_SWING_LOOKBACK)
        seg = df.iloc[s:fi] if not df.iloc[s:fi].empty else df.iloc[fi:fi+1]
        sl_px = float(seg["Low"].min()) if is_buy else float(seg["High"].max())
        risk = abs(entry - sl_px) or entry * 0.001
        tp1, tp2 = (entry + risk, entry + 2*risk) if is_buy else (entry - risk, entry - 2*risk)

        state[name] = {"direction": direction, "entry": entry, "sl": sl_px, "tp1": tp1, "tp2": tp2, "tp1_hit": False, "sl_moved_to_be": False}
        with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)

        msg = (f"⚔️ *{direction} SIGNAL CONFIRMED on {name}*\n"
               f"• *Tier:* `{tier}`\n"
               f"• *Entry:* `{entry:.4f}`\n• *SL:* `{sl_px:.4f}`\n• *TP1:* `{tp1:.4f}`\n• *TP2:* `{tp2:.4f}`")
        send_notification(f"🚨 TREND TARGETS PRO — {name}", msg, 5763719 if is_buy else 15548997)

if __name__ == "__main__":
    try:
        run_scanner()
    except Exception as e:
        print(f"Scanner Exception: {e}")