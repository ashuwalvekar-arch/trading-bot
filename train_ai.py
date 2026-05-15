import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# =========================================================
# CONFIG
# =========================================================

MODEL_PATH = Path("ai_model.pkl")
SCORE_PATH = Path("model_score.txt")
DATA_PATH = Path("market_data.csv")

# =========================================================
# LOAD DATA
# =========================================================

if not DATA_PATH.exists():
    print("market_data.csv not found")
    exit()

df = pd.read_csv(DATA_PATH)

required_columns = [
    "ema20",
    "ema50",
    "rsi",
    "returns",
    "tick_volume",
    "target"
]

for col in required_columns:
    if col not in df.columns:
        print(f"Missing column: {col}")
        exit()

# =========================================================
# FEATURES
# =========================================================

X = df[
    [
        "ema20",
        "ema50",
        "rsi",
        "returns",
        "tick_volume"
    ]
]

y = df["target"]

# =========================================================
# TRAIN TEST SPLIT
# =========================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    shuffle=False
)

# =========================================================
# TRAIN MODEL
# =========================================================

print("Training AI model...")

model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    random_state=42,
)

model.fit(X_train, y_train)

# =========================================================
# EVALUATE MODEL
# =========================================================

predictions = model.predict(X_test)

accuracy = accuracy_score(y_test, predictions)

print(f"New Model Accuracy: {accuracy:.4f}")

# =========================================================
# LOAD OLD SCORE
# =========================================================

old_score = 0.0

if SCORE_PATH.exists():
    try:
        old_score = float(SCORE_PATH.read_text())
    except:
        old_score = 0.0

print(f"Previous Best Accuracy: {old_score:.4f}")

# =========================================================
# SAVE ONLY IF BETTER
# =========================================================

if accuracy > old_score:

    print("New model is BETTER")
    print("Saving AI model...")

    joblib.dump(model, MODEL_PATH)

    SCORE_PATH.write_text(str(accuracy))

    print("AI model updated successfully")

else:

    print("Old model is still better")
    print("Model NOT replaced")