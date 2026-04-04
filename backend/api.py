from __future__ import annotations

import base64
import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import shap
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from xgboost import XGBClassifier

from decision_utils import decide_prediction
from feature_extraction import FEATURE_COLUMNS, extract_url_features
from model_utils import load_threshold

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE_DIR / "models" / "model.json"
LOGGER = logging.getLogger("phishguard.api")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(title="PhishGuard AI API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    url: str = Field(..., min_length=3, description="URL to evaluate")


class ExplanationItem(BaseModel):
    feature: str
    contribution: float


class PredictResponse(BaseModel):
    prediction: str
    probability: float
    raw_model_probability: float
    confidence: float
    risk_score: int
    decision_reason: str | None = None
    explanation: list[ExplanationItem]
    shap_values: dict[str, float]
    shap_plot_base64: str


def get_model_version() -> int:
    return MODEL_PATH.stat().st_mtime_ns


@lru_cache(maxsize=1)
def load_model(model_version: int | None = None) -> XGBClassifier:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. Run `python train.py` first."
        )
    model = XGBClassifier()
    model.load_model(str(MODEL_PATH))
    return model


@lru_cache(maxsize=1)
def load_explainer(model_version: int | None = None) -> shap.TreeExplainer:
    return shap.TreeExplainer(load_model(model_version))


def _single_shap_values(explainer: shap.TreeExplainer, X: pd.DataFrame):
    values = explainer.shap_values(X)
    if hasattr(values, "ndim") and values.ndim == 2:
        return values[0]
    return values


def _make_bar_plot(shap_map: dict[str, float]) -> str:
    series = pd.Series(shap_map).sort_values(key=lambda s: s.abs(), ascending=False).head(10)
    series = series.sort_values()

    fig_height = max(4.8, 0.52 * len(series) + 1.6)
    fig, ax = plt.subplots(figsize=(9.5, fig_height))

    colors = ["#ff5f7a" if v > 0 else "#2ec27e" for v in series.values]
    labels = [name.replace("_", " ").title() for name in series.index]
    ax.barh(labels, series.values, color=colors, height=0.62)
    ax.axvline(0, color="#94a3b8", linewidth=1)
    ax.set_title("Top SHAP Feature Contributions", fontsize=18, pad=16)
    ax.set_xlabel("Contribution", fontsize=12)
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=11)
    ax.tick_params(axis="x", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f8fafc")
    plt.subplots_adjust(left=0.34, right=0.96, top=0.86, bottom=0.15)

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest) -> PredictResponse:
    LOGGER.info("Received prediction request")
    try:
        features = extract_url_features(payload.url)
        X = pd.DataFrame([features], columns=FEATURE_COLUMNS)

        model_version = get_model_version()
        model = load_model(model_version)
        explainer = load_explainer(model_version)
        threshold = load_threshold(str(MODEL_PATH))

        probability = float(model.predict_proba(X)[0, 1])
        prediction, final_probability, confidence, risk_score, decision_reason = decide_prediction(
            payload.url,
            probability,
            threshold,
            features,
        )

        single_shap = _single_shap_values(explainer, X)
        shap_map = {name: float(value) for name, value in zip(FEATURE_COLUMNS, single_shap)}
        ranked = sorted(shap_map.items(), key=lambda item: abs(item[1]), reverse=True)[:5]
        explanation = [
            ExplanationItem(feature=name, contribution=value) for name, value in ranked
        ]

        return PredictResponse(
            prediction=prediction,
            probability=final_probability,
            raw_model_probability=probability,
            confidence=float(confidence),
            risk_score=risk_score,
            decision_reason=decision_reason,
            explanation=explanation,
            shap_values=shap_map,
            shap_plot_base64=_make_bar_plot(shap_map),
        )
    except FileNotFoundError as exc:
        LOGGER.exception("Model missing")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        LOGGER.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}") from exc
