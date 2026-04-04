from __future__ import annotations

import argparse

import pandas as pd
from xgboost import XGBClassifier

from decision_utils import decide_prediction
from feature_extraction import FEATURE_COLUMNS, extract_url_features
from model_utils import load_threshold


def load_model(model_path: str) -> XGBClassifier:
    model = XGBClassifier()
    model.load_model(model_path)
    return model


def predict_url(url: str, model_path: str = "models/model.json") -> tuple[float, str]:
    model = load_model(model_path)
    threshold = load_threshold(model_path)
    features = extract_url_features(url)
    X = pd.DataFrame([features], columns=FEATURE_COLUMNS)
    proba = float(model.predict_proba(X)[0, 1])
    label, final_probability, _, _, _ = decide_prediction(url, proba, threshold, features)
    return final_probability, label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict phishing probability for URL.")
    parser.add_argument("--url", required=True, help="URL to scan")
    parser.add_argument("--model", default="models/model.json", help="Path to saved model")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    probability, prediction = predict_url(args.url, model_path=args.model)
    print(f"URL: {args.url}")
    print(f"Prediction: {prediction}")
    print(f"Phishing probability: {probability:.4f}")
