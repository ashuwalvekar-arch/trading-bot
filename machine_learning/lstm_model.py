"""
LSTM price direction classifier scaffold.
Train with: python -m machine_learning.train
"""
from __future__ import annotations
from pathlib import Path
import numpy as np

try:
    import torch
    import torch.nn as nn

    class LSTMTrader(nn.Module):
        def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.3):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size, hidden_size, num_layers,
                batch_first=True, dropout=dropout
            )
            self.fc = nn.Sequential(
                nn.Linear(hidden_size, 64),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(64, 3),   # 0=SELL, 1=WAIT, 2=BUY
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


def load_model(path: str, input_size: int) -> "LSTMTrader | None":
    if not TORCH_AVAILABLE:
        return None
    model = LSTMTrader(input_size)
    model.load_state_dict(torch.load(path, map_location="cpu"))
    model.eval()
    return model


def predict(model: "LSTMTrader", sequence: np.ndarray) -> int:
    """Returns 0 (SELL), 1 (WAIT), 2 (BUY)."""
    if model is None:
        return 1
    t = torch.tensor(sequence).unsqueeze(0)
    with torch.no_grad():
        logits = model(t)
    return int(logits.argmax(dim=1).item())
