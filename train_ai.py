import MetaTrader5 as mt5
import pandas as pd
import ta
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# =====================================================
# MT5
# =====================================================

SYMBOL = "GOLD.i#"

mt5.initialize()

# =====================================================
# GET DATA
# =====================================================

rates = mt5.copy_rates_from_pos(
    SYMBOL,
    mt5.TIMEFRAME_M5,
    0,
    10000
)

df = pd.DataFrame(rates)

# =====================================================
# FEATURES
# =====================================================

df['ema20'] = ta.trend.ema_indicator(
    df['close'],
    window=20
)

df['ema50'] = ta.trend.ema_indicator(
    df['close'],
    window=50
)

df['rsi'] = ta.momentum.rsi(
    df['close'],
    window=14
)

df['returns'] = (
    df['close'].pct_change()
)

df['target'] = (
    df['close'].shift(-1)
    >
    df['close']
).astype(int)

df = df.dropna()

# =====================================================
# DATASET
# =====================================================

X = df[[
    'ema20',
    'ema50',
    'rsi',
    'returns',
    'tick_volume'
]]

y = df['target']

# =====================================================
# TRAIN TEST
# =====================================================

X_train, X_test, y_train, y_test = train_test_split(

    X,

    y,

    test_size=0.2,

    shuffle=False
)

# =====================================================
# MODEL
# =====================================================

model = RandomForestClassifier(

    n_estimators=200,

    max_depth=10,

    random_state=42
)

model.fit(
    X_train,
    y_train
)

# =====================================================
# EVALUATION
# =====================================================

predictions = model.predict(
    X_test
)

accuracy = accuracy_score(
    y_test,
    predictions
)

print()

print("="*50)

print("AI MODEL TRAINED")

print("="*50)

print()

print(
    f"Accuracy: {round(accuracy*100,2)}%"
)

print()

print("="*50)

# =====================================================
# SAVE MODEL
# =====================================================

joblib.dump(
    model,
    "ai_model.pkl"
)

print()

print("MODEL SAVED:")
print("ai_model.pkl")

print()