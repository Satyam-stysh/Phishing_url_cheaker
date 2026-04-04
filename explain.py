from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import shap
from xgboost import XGBClassifier

from feature_extraction import (
    FEATURE_COLUMNS,
    extract_features_for_series,
    extract_url_features,
    infer_url_column,
)


def load_model(model_path: str) -> XGBClassifier:
    model = XGBClassifier()
    model.load_model(model_path)
    return model


def explain_single_url(
    url: str,
    model_path: str = "models/model.json",
    out_plot_path: str = "models/shap_single_bar.png",
) -> None:
    model = load_model(model_path)
    explainer = shap.TreeExplainer(model)
    X_single = pd.DataFrame([extract_url_features(url)], columns=FEATURE_COLUMNS)

    shap_values = explainer.shap_values(X_single)
    single_shap = shap_values[0] if hasattr(shap_values, "ndim") and shap_values.ndim == 2 else shap_values
    pairs = sorted(
        zip(FEATURE_COLUMNS, single_shap),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    )

    print("Top 5 important features for this prediction:")
    for name, value in pairs[:5]:
        print(f"- {name}: SHAP={float(value):.6f}")

    print("\nAll SHAP values:")
    for name, value in zip(FEATURE_COLUMNS, single_shap):
        print(f"{name}: {float(value):.6f}")

    fig, ax = plt.subplots(figsize=(8, 4))
    series = pd.Series({name: float(v) for name, v in zip(FEATURE_COLUMNS, single_shap)})
    series = series.sort_values(key=lambda s: s.abs())
    colors = ["#ef4444" if v > 0 else "#22c55e" for v in series.values]
    ax.barh(series.index, series.values, color=colors)
    ax.set_title("Single URL SHAP Contributions")
    ax.set_xlabel("SHAP Value")
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    plt.tight_layout()
    output = Path(out_plot_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\nSaved SHAP bar plot to: {output}")


def shap_summary_plot(
    data_path: str = "data/urls.csv",
    model_path: str = "models/model.json",
    out_path: str = "models/shap_summary.png",
) -> None:
    df = pd.read_csv(data_path)
    url_col = infer_url_column(df)
    X = extract_features_for_series(df[url_col].fillna("").astype(str))
    model = load_model(model_path)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    plt.figure(figsize=(10, 6))
    shap.summary_plot(shap_values, X, show=False)
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved SHAP summary plot to: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explain phishing prediction with SHAP.")
    parser.add_argument("--url", required=True, help="URL to explain")
    parser.add_argument("--model", default="models/model.json", help="Path to saved model")
    parser.add_argument("--data", default="data/urls.csv", help="Dataset path for SHAP summary")
    parser.add_argument("--summary-out", default="models/shap_summary.png", help="Summary plot path")
    parser.add_argument("--single-out", default="models/shap_single_bar.png", help="Single-url bar path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    explain_single_url(args.url, model_path=args.model, out_plot_path=args.single_out)
    shap_summary_plot(data_path=args.data, model_path=args.model, out_path=args.summary_out)
