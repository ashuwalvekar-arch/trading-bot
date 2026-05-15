import MetaTrader5 as mt5
import pandas as pd
import ta
from datetime import datetime

# =====================================================
#   GOLD STRATEGY v3.0 — PRECISION SNIPER SYSTEM
#   Upgrades vs v2:
#     ✦ H1 Higher-Timeframe Bias Filter
#     ✦ Session Filter (London 08-12 UTC / NY 13-17 UTC)
#     ✦ Smarter RSI zone (entering momentum, not chasing)
#     ✦ Engulfing / Pin-Bar candle confirmation
#     ✦ Wider ATR SL (2.0x) to survive Gold noise
#     ✦ Trailing SL kicks in at 1.5R to protect wins
#     ✦ Higher MACD bar acceleration requirement
#     ✦ EMA slope check (not just alignment)
# =====================================================

SYMBOL        = "GOLD.i#"
TIMEFRAME_M5  = mt5.TIMEFRAME_M5
TIMEFRAME_H1  = mt5.TIMEFRAME_H1
BARS          = 5000
H1_BARS       = 1000
START_BALANCE = 1000
LOOKBACK      = 220
FUTURE_BARS   = 30           # up from 20 — give trades room to breathe
MIN_CONFLUENCE = 7           # out of 9 refined conditions (quality > quantity)
ATR_SL_MULT   = 2.0          # WIDENED: Gold is noisy on M5 — 1.5x was too tight
ATR_TP_MULT   = 4.0          # 1:2 RR minimum; 4/2 = 2.0 RR
TRAIL_TRIGGER = 1.5          # move SL to break-even after 1.5R profit
MIN_ADX       = 22           # slightly relaxed — catch early trend
MIN_ATR       = 0.4          # Gold ATR floor in points

# =====================================================
#   LONDON + NEW YORK SESSION HOURS (UTC)
#   Avoids Asian session chop and illiquid spread
# =====================================================
LONDON_OPEN  = 7    # 07:00 UTC
LONDON_CLOSE = 12   # 12:00 UTC
NY_OPEN      = 13   # 13:00 UTC
NY_CLOSE     = 17   # 17:00 UTC

def in_active_session(dt):
    h = dt.hour
    return (LONDON_OPEN <= h < LONDON_CLOSE) or (NY_OPEN <= h < NY_CLOSE)

# =====================================================
#   MT5  CONNECT
# =====================================================
if not mt5.initialize():
    raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

# =====================================================
#   FETCH M5 DATA
# =====================================================
rates_m5 = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME_M5, 0, BARS)
if rates_m5 is None or len(rates_m5) == 0:
    raise RuntimeError("No M5 data received from MT5")

df = pd.DataFrame(rates_m5)
df['time'] = pd.to_datetime(df['time'], unit='s')
print(f"  Loaded {len(df)} M5 candles for {SYMBOL}")

# =====================================================
#   FETCH H1 DATA  (higher timeframe bias)
# =====================================================
rates_h1 = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME_H1, 0, H1_BARS)
if rates_h1 is None or len(rates_h1) == 0:
    raise RuntimeError("No H1 data received from MT5")

h1 = pd.DataFrame(rates_h1)
h1['time'] = pd.to_datetime(h1['time'], unit='s')

# H1 Trend indicators
h1['ema50_h1']  = ta.trend.ema_indicator(h1['close'], window=50)
h1['ema200_h1'] = ta.trend.ema_indicator(h1['close'], window=200)
h1['rsi_h1']    = ta.momentum.rsi(h1['close'], window=14)
h1_adx = ta.trend.ADXIndicator(h1['high'], h1['low'], h1['close'], window=14)
h1['adx_h1']    = h1_adx.adx()
h1['adx_pos_h1']= h1_adx.adx_pos()
h1['adx_neg_h1']= h1_adx.adx_neg()
h1.dropna(inplace=True)

# H1 bias: set floor_time for H1 candle lookup
h1.set_index('time', inplace=True)

def get_h1_bias(m5_time):
    """Return 'BUY', 'SELL', or 'NEUTRAL' based on H1 context."""
    # Floor to H1 boundary
    h1_ts = m5_time.floor('h')
    if h1_ts not in h1.index:
        # Try the previous hour
        h1_ts = h1_ts - pd.Timedelta(hours=1)
    if h1_ts not in h1.index:
        return 'NEUTRAL'
    row = h1.loc[h1_ts]
    bull = (row['ema50_h1'] > row['ema200_h1']) and (row['rsi_h1'] > 50)
    bear = (row['ema50_h1'] < row['ema200_h1']) and (row['rsi_h1'] < 50)
    if bull:
        return 'BUY'
    elif bear:
        return 'SELL'
    return 'NEUTRAL'

# =====================================================
#   M5 INDICATORS
# =====================================================
df['ema20']  = ta.trend.ema_indicator(df['close'], window=20)
df['ema50']  = ta.trend.ema_indicator(df['close'], window=50)
df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)

# EMA slope (change over 3 bars) — confirms direction, not just alignment
df['ema20_slope'] = df['ema20'].diff(3)
df['ema50_slope'] = df['ema50'].diff(3)

df['rsi'] = ta.momentum.rsi(df['close'], window=14)

stoch = ta.momentum.StochasticOscillator(
            df['high'], df['low'], df['close'],
            window=14, smooth_window=3)
df['stoch_k'] = stoch.stoch()
df['stoch_d'] = stoch.stoch_signal()

macd_ind      = ta.trend.MACD(df['close'], window_slow=26,
                               window_fast=12, window_sign=9)
df['macd']      = macd_ind.macd()
df['macd_sig']  = macd_ind.macd_signal()
df['macd_hist'] = macd_ind.macd_diff()

adx_ind     = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
df['adx']     = adx_ind.adx()
df['adx_pos'] = adx_ind.adx_pos()
df['adx_neg'] = adx_ind.adx_neg()

bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
df['bb_upper'] = bb.bollinger_hband()
df['bb_lower'] = bb.bollinger_lband()
df['bb_mid']   = bb.bollinger_mavg()
df['bb_width'] = df['bb_upper'] - df['bb_lower']   # volatility squeeze gauge

df['atr'] = ta.volatility.AverageTrueRange(
                df['high'], df['low'], df['close'], window=14
            ).average_true_range()

df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()

# Candle metrics
df['body']     = abs(df['close'] - df['open'])
df['candle_range'] = df['high'] - df['low']
df['body_pct'] = df['body'] / df['candle_range'].replace(0, 1)

# Engulfing detection (prev candle body vs current)
df['prev_body']  = df['body'].shift(1)
df['prev_open']  = df['open'].shift(1)
df['prev_close'] = df['close'].shift(1)

df.dropna(inplace=True)
df.reset_index(drop=True, inplace=True)

# =====================================================
#   CANDLE PATTERN HELPERS
# =====================================================
def is_bull_engulfing(row, prev):
    """Current bullish candle body engulfs previous bearish body."""
    prev_bear = prev['close'] < prev['open']
    curr_bull = row['close'] > row['open']
    engulfs   = (row['close'] > prev['open']) and (row['open'] < prev['close'])
    return prev_bear and curr_bull and engulfs

def is_bear_engulfing(row, prev):
    """Current bearish candle body engulfs previous bullish body."""
    prev_bull = prev['close'] > prev['open']
    curr_bear = row['close'] < row['open']
    engulfs   = (row['close'] < prev['open']) and (row['open'] > prev['close'])
    return prev_bull and curr_bear and engulfs

def is_pin_bar_bull(row):
    """Bullish pin bar: long lower wick, small body near top."""
    lower_wick = row['open'] - row['low'] if row['close'] > row['open'] else row['close'] - row['low']
    return lower_wick > (row['candle_range'] * 0.55) and row['body_pct'] < 0.35

def is_pin_bar_bear(row):
    """Bearish pin bar: long upper wick, small body near bottom."""
    upper_wick = row['high'] - row['open'] if row['close'] < row['open'] else row['high'] - row['close']
    return upper_wick > (row['candle_range'] * 0.55) and row['body_pct'] < 0.35

# =====================================================
#   BACKTEST VARIABLES
# =====================================================
balance      = START_BALANCE
wins         = 0
losses       = 0
break_evens  = 0
no_result    = 0
total_trades = 0
trade_log    = []

# =====================================================
#   MAIN BACKTEST LOOP
# =====================================================
for i in range(LOOKBACK, len(df) - FUTURE_BARS):

    row  = df.iloc[i]
    prev = df.iloc[i - 1]

    # ── Pre-checks ──────────────────────────────
    atr = row['atr']
    if atr < MIN_ATR:
        continue

    # ── Session filter ──────────────────────────
    if not in_active_session(row['time']):
        continue

    # ── H1 bias ─────────────────────────────────
    h1_bias = get_h1_bias(row['time'])
    if h1_bias == 'NEUTRAL':
        continue   # no clear HTF direction — skip

    entry = row['close']

    # ── Candle patterns ──────────────────────────
    bull_engulf = is_bull_engulfing(row, prev)
    bear_engulf = is_bear_engulfing(row, prev)
    pin_bull    = is_pin_bar_bull(row)
    pin_bear    = is_pin_bar_bear(row)
    bull_pattern = bull_engulf or pin_bull
    bear_pattern = bear_engulf or pin_bear

    # ── BB squeeze filter (avoid ranging, compressed markets) ──
    bb_expanding = row['bb_width'] > df['bb_width'].iloc[max(0,i-10):i].mean()

    # ─────────────────────────────────────────────
    #  CONFLUENCE CONDITIONS  (9 refined layers)
    # ─────────────────────────────────────────────

    # ── BUY conditions ──────────────────────────
    buy = [
        # L1  H1 trend bias is bullish (HTF alignment)
        h1_bias == 'BUY',

        # L2  EMA alignment + SLOPES pointing up
        (row['ema20'] > row['ema50'] > row['ema200'])
        and (row['ema20_slope'] > 0) and (row['ema50_slope'] > 0),

        # L3  RSI in momentum-building zone (not chasing, not overbought)
        #     Changed from 55-78 → 45-65 for earlier, cleaner entries
        45 < row['rsi'] < 65,

        # L4  Stochastic: K crosses above D from oversold / mid zone
        (row['stoch_k'] > row['stoch_d'])
        and (prev['stoch_k'] <= prev['stoch_d'])   # fresh cross this bar
        and (row['stoch_k'] < 75),                 # not overbought

        # L5  MACD: histogram positive AND accelerating (2 consecutive bars)
        (row['macd_hist'] > 0)
        and (row['macd_hist'] > prev['macd_hist'])
        and (prev['macd_hist'] > df.iloc[i-2]['macd_hist']),

        # L6  ADX strong trend + +DI dominance
        (row['adx'] > MIN_ADX) and (row['adx_pos'] > row['adx_neg']),

        # L7  Price above BB mid AND Bollinger bands are expanding (trend)
        (row['close'] > row['bb_mid']) and bb_expanding,

        # L8  Candle pattern: engulfing or pin bar confirmation
        bull_pattern,

        # L9  Price pulled back to within 1xATR of EMA20 (not overextended)
        abs(row['close'] - row['ema20']) < atr * 1.0,
    ]

    # ── SELL conditions ─────────────────────────
    sell = [
        # L1  H1 trend bias is bearish
        h1_bias == 'SELL',

        # L2  EMA alignment + SLOPES pointing down
        (row['ema20'] < row['ema50'] < row['ema200'])
        and (row['ema20_slope'] < 0) and (row['ema50_slope'] < 0),

        # L3  RSI in bearish momentum zone
        35 < row['rsi'] < 55,

        # L4  Stochastic: K crosses below D from overbought / mid zone
        (row['stoch_k'] < row['stoch_d'])
        and (prev['stoch_k'] >= prev['stoch_d'])   # fresh cross this bar
        and (row['stoch_k'] > 25),                 # not oversold

        # L5  MACD: histogram negative AND deepening (2 consecutive bars)
        (row['macd_hist'] < 0)
        and (row['macd_hist'] < prev['macd_hist'])
        and (prev['macd_hist'] < df.iloc[i-2]['macd_hist']),

        # L6  ADX strong trend + -DI dominance
        (row['adx'] > MIN_ADX) and (row['adx_neg'] > row['adx_pos']),

        # L7  Price below BB mid AND bands expanding
        (row['close'] < row['bb_mid']) and bb_expanding,

        # L8  Candle pattern: engulfing or pin bar confirmation
        bear_pattern,

        # L9  Price near EMA20 (not overextended on the downside)
        abs(row['close'] - row['ema20']) < atr * 1.0,
    ]

    buy_score  = sum(buy)
    sell_score = sum(sell)

    signal = None
    if buy_score >= MIN_CONFLUENCE:
        signal = "BUY"
        sl = entry - (atr * ATR_SL_MULT)
        tp = entry + (atr * ATR_TP_MULT)
    elif sell_score >= MIN_CONFLUENCE:
        signal = "SELL"
        sl = entry + (atr * ATR_SL_MULT)
        tp = entry - (atr * ATR_TP_MULT)

    if signal is None:
        continue

    total_trades += 1
    future   = df.iloc[i + 1 : i + FUTURE_BARS + 1]
    result   = None
    sl_risk  = atr * ATR_SL_MULT
    tp_gain  = atr * ATR_TP_MULT
    trail_level = atr * TRAIL_TRIGGER   # 1.5R profit triggers BE move
    current_sl  = sl                    # mutable SL for trailing

    # ─────────────────────────────────────────────
    #  TRADE RESOLUTION  (with trailing SL)
    # ─────────────────────────────────────────────
    if signal == "BUY":
        trail_activated = False
        for _, candle in future.iterrows():
            # Check if trailing SL should activate
            if not trail_activated and candle['high'] >= entry + trail_level:
                current_sl = entry          # move SL to break-even
                trail_activated = True

            if candle['low'] <= current_sl:
                if trail_activated:
                    result  = "BE"          # break-even exit
                    break_evens += 1
                else:
                    result   = "LOSS"
                    balance -= sl_risk
                    losses  += 1
                break
            if candle['high'] >= tp:
                result   = "WIN"
                balance += tp_gain
                wins    += 1
                break

    elif signal == "SELL":
        trail_activated = False
        for _, candle in future.iterrows():
            if not trail_activated and candle['low'] <= entry - trail_level:
                current_sl = entry
                trail_activated = True

            if candle['high'] >= current_sl:
                if trail_activated:
                    result  = "BE"
                    break_evens += 1
                else:
                    result   = "LOSS"
                    balance -= sl_risk
                    losses  += 1
                break
            if candle['low'] <= tp:
                result   = "WIN"
                balance += tp_gain
                wins    += 1
                break

    if result is None:
        no_result += 1

    trade_log.append({
        "time"       : str(row['time']),
        "signal"     : signal,
        "entry"      : round(entry, 2),
        "sl"         : round(sl, 2),
        "tp"         : round(tp, 2),
        "atr"        : round(atr, 2),
        "adx"        : round(row['adx'], 1),
        "rsi"        : round(row['rsi'], 1),
        "h1_bias"    : h1_bias,
        "confluence" : buy_score if signal == "BUY" else sell_score,
        "result"     : result if result else "OPEN",
    })

# =====================================================
#   RESULTS
# =====================================================
settled      = wins + losses          # BE trades are free — not counted as loss
win_rate     = (wins / settled * 100) if settled > 0 else 0
gross_win    = wins   * ATR_TP_MULT
gross_loss   = losses * ATR_SL_MULT
profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
net_pnl      = round(balance - START_BALANCE, 2)

print()
print("=" * 58)
print("        GOLD STRATEGY v3.0 — BACKTEST RESULTS")
print("=" * 58)
print(f"  Symbol          : {SYMBOL}")
print(f"  Timeframe       : M5  (H1 bias filter)")
print(f"  Total Signals   : {total_trades}")
print(f"  Settled Trades  : {settled}  (open: {no_result})")
print(f"  Wins            : {wins}")
print(f"  Losses          : {losses}")
print(f"  Break-Evens     : {break_evens}  (trail SL — no loss taken)")
print(f"  Win Rate        : {round(win_rate, 2)}%")
print(f"  Profit Factor   : {round(profit_factor, 2)}")
print(f"  Risk / Reward   : 1 : {ATR_TP_MULT / ATR_SL_MULT:.1f}")
print(f"  Starting Balance: ${START_BALANCE}")
print(f"  Final Balance   : ${round(balance, 2)}")
print(f"  Net P&L         : ${net_pnl}")
print("=" * 58)
print()
print("  CONFLUENCE LAYERS (v3.0 — 9 Precision Conditions):")
print("  ──────────────────────────────────────────────────")
print("  L1  H1 Higher-TF Bias     (EMA50/200 + RSI on H1)")
print("  L2  Triple EMA + Slope    (20/50/200 + slope > 0)")
print("  L3  RSI Entry Zone        (45-65 BUY / 35-55 SELL)")
print("  L4  Stochastic FRESH Cross(K/D cross this bar only)")
print("  L5  MACD Histogram x2     (accelerating 2 bars)")
print("  L6  ADX Trend Gate        (>22, DI dominance)")
print("  L7  BB Position + Expand  (mid bias + expanding)")
print("  L8  Candle Pattern        (engulfing or pin bar)")
print("  L9  EMA20 Proximity       (pullback entry, <1xATR)")
print()
print(f"  Min confluence required : {MIN_CONFLUENCE}/9")
print(f"  ATR SL multiplier       : {ATR_SL_MULT}x  (widened for Gold noise)")
print(f"  ATR TP multiplier       : {ATR_TP_MULT}x")
print(f"  Trail SL trigger        : {TRAIL_TRIGGER}R  (moves to break-even)")
print(f"  Session filter          : London 07-12 UTC / NY 13-17 UTC")
print("=" * 58)

# =====================================================
#   EXPORT TRADE LOG
# =====================================================
if trade_log:
    log_df = pd.DataFrame(trade_log)
    log_df.to_csv("trade_log_v3.csv", index=False)
    print()
    print("  Trade log saved → trade_log_v3.csv")
    print()
