import os
import json
import time
from datetime import datetime
import pytz
import pandas as pd
import requests

try:
    from biquote import Biquote
    BIQUOTE_AVAILABLE = True
except Exception as _e:
    BIQUOTE_AVAILABLE = False
    print(f"[CONFIG] biquote not importable: {_e}")

# ------------------------------------------------------------------- CONFIG
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

PRICE_ALERTS_FILE    = "price_alerts.json"
TELEGRAM_OFFSET_FILE = "telegram_offset.json"
ZAMBIA_TZ            = pytz.timezone("Africa/Lusaka")

# ------------------------------------------------------------------- UTILS
def to_cat(ts):
    if ts.tzinfo is None: ts = ts.tz_localize("UTC")
    return ts.tz_convert(ZAMBIA_TZ)

def load_offset():
    if os.path.exists(TELEGRAM_OFFSET_FILE):
        try:
            with open(TELEGRAM_OFFSET_FILE) as f: return json.load(f).get("offset", 0)
        except Exception: return 0
    return 0

def save_offset(offset):
    with open(TELEGRAM_OFFSET_FILE, "w") as f: json.dump({"offset": offset}, f)

def load_price_alerts():
    if os.path.exists(PRICE_ALERTS_FILE):
        try:
            with open(PRICE_ALERTS_FILE) as f: return json.load(f)
        except Exception: return {}
    return {}

def save_price_alerts(a):
    with open(PRICE_ALERTS_FILE, "w") as f: json.dump(a, f, indent=2)

# ------------------------------------------------------------- DATA FETCHING
def fetch_biquote_series(symbol, interval_str, limit=100):
    if not BIQUOTE_AVAILABLE: raise RuntimeError("biquote not installed")
    bq = Biquote()
    method = getattr(bq, "ohlc", None)
    attempts = [
        lambda: method(symbol=symbol, interval=interval_str, limit=limit),
        lambda: method(symbol=symbol, interval=interval_str),
        lambda: method(symbol, interval_str, limit),
        lambda: method(symbol=symbol, interval=interval_str, limit=limit, from_=None),
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

def drop_unclosed_candles(df):
    if df.empty: return df
    idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    bar_len = pd.Timedelta(minutes=5)
    cutoff = pd.Timestamp(datetime.now(pytz.UTC)) - pd.Timedelta(seconds=5)
    closed = (idx + bar_len) <= cutoff
    return df[closed]

# ------------------------------------------------------------- TELEGRAM & ALERTS
def send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID): return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception: pass

def send_notification(title, body):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": f"**{title}**\n{body}"}, timeout=5)
        except Exception: pass
    send_telegram(f"*{title}*\n\n{body}")

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
        
        # 6-MINUTE HARD LOCK: Prevents GitHub Actions from re-reading old messages
        msg_time = msg.get("date", 0)
        if (time.time() - msg_time) > 360:
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
            else: send_telegram("❌ Usage: `/alert SYMBOL PRICE`")
                
        elif text.startswith("/remove"):
            parts = text.split()
            if len(parts) >= 2:
                symbol = parts[1].upper()
                if symbol in alerts:
                    del alerts[symbol]
                    updated = True
                    send_telegram(f"🗑 Alert Removed for *{symbol}*")
                else: send_telegram(f"ℹ️ No active alert for *{symbol}*")
                    
        elif text.startswith("/alerts"):
            if alerts:
                lines = ["*Active Price Alerts:*"]
                for s, a in alerts.items(): lines.append(f"• *{s}*: `{a['price']}`")
                send_telegram("\n".join(lines))
            else: send_telegram("ℹ️ No active price alerts.")
                
        elif text.startswith("/price"):
            parts = text.split()
            if len(parts) >= 2:
                symbol = parts[1].upper()
                try:
                    df = fetch_biquote_series(symbol, "1m", limit=2)
                    if not df.empty:
                        send_telegram(f"📊 *{symbol}* current price: `{df.iloc[-1]['Close']:.5f}`")
                    else: send_telegram(f"❌ Could not fetch price for {symbol}")
                except Exception as e: send_telegram(f"❌ Error: {e}")
            else: send_telegram("❌ Usage: `/price SYMBOL`")
                
        elif text.startswith("/help"):
            help_text = ("*Commands:*\n"
                         "`/alert SYMBOL PRICE` - Set alert\n"
                         "`/remove SYMBOL` - Remove alert\n"
                         "`/alerts` - List active alerts\n"
                         "`/price SYMBOL` - Check MT5 price\n"
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
            df = fetch_biquote_series(symbol, "5m", limit=50)
            df = drop_unclosed_candles(df)
            if df.empty: continue

            hit_bar = None
            for idx, row in df.iloc[-20:].iterrows():
                bar_close_time = idx + pd.Timedelta(minutes=5)
                if bar_close_time > created_at:
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
        except Exception as e: print(f"[PRICE ALERT] Error {symbol}: {e}")

    if updated: save_price_alerts(alerts)

# ------------------------------------------------------------- MAIN
def main():
    print(f"===== SCAN START — {datetime.now(ZAMBIA_TZ).strftime('%H:%M:%S')} =====")
    poll_telegram_commands()
    check_price_alerts()

if __name__ == "__main__":
    main()