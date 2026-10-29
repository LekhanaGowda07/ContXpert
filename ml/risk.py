"""AI academic-risk model: Gradient Boosting classifier -> probability that a student ends up
detained / failing, from attendance, CIE performance and fee-dues features.

IMPORTANT: until you have real historical outcomes, the model is trained on SYNTHETIC data that encodes
common-sense relationships. To use real data, build a CSV with the FEATURES columns + `at_risk` (0/1) from
past batches and call `train_from_csv("history.csv")`."""
import csv
import threading

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

FEATURES = ["avg_att", "min_att", "n_short", "avg_cie_pct", "fee_due_ratio"]
_model = None
_lock = threading.Lock()


def _synthetic(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    base = np.clip(rng.normal(80, 11, (n, 1)), 40, 100)
    subj = np.clip(base + rng.normal(0, 7, (n, 5)), 20, 100)
    avg_att, min_att = subj.mean(1), subj.min(1)
    n_short = (subj < 75).sum(1)
    cie = np.clip(rng.normal(0.62, 0.17, n) + 0.25 * (avg_att - 75) / 100, 0, 1)
    fee = np.where(rng.random(n) < 0.6, 0.0, rng.uniform(0, 0.6, n))
    logit = 0.12 * (75 - min_att) + 0.35 * n_short + 6 * (0.5 - cie) + 2.0 * fee - 1.0
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return np.column_stack([avg_att, min_att, n_short, cie, fee]), y


def _fit(X, y):
    return GradientBoostingClassifier(n_estimators=150, max_depth=3, random_state=0).fit(X, y)


def train_from_csv(path):
    global _model
    X, y = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            X.append([float(r[c]) for c in FEATURES])
            y.append(int(r["at_risk"]))
    with _lock:
        _model = _fit(np.array(X), np.array(y))


def get_model():
    global _model
    with _lock:
        if _model is None:
            _model = _fit(*_synthetic())
    return _model


def predict(feat):
    """feat: dict with FEATURES keys -> (probability 0..1, level)."""
    p = float(get_model().predict_proba([[feat[c] for c in FEATURES]])[0][1])
    level = "LOW" if p < 0.30 else "MEDIUM" if p < 0.60 else "HIGH"
    return p, level
