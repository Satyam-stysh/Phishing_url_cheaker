from __future__ import annotations

from pathlib import Path
import pandas as pd
import shap
import streamlit as st
from urllib.parse import urlparse
from xgboost import XGBClassifier

from decision_utils import decide_prediction
from feature_extraction import FEATURE_COLUMNS, extract_url_features
from model_utils import load_threshold

MODEL_PATH = "models/model.json"

st.set_page_config(page_title="PhishGuard AI", page_icon="🔐", layout="wide")


def get_model_version(model_path: str = MODEL_PATH) -> int:
    return Path(model_path).stat().st_mtime_ns


@st.cache_resource
def load_model(model_path: str = MODEL_PATH, model_version: int | None = None) -> XGBClassifier:
    model = XGBClassifier()
    model.load_model(model_path)
    return model


@st.cache_resource
def load_explainer(model_path: str = MODEL_PATH, model_version: int | None = None) -> shap.TreeExplainer:
    return shap.TreeExplainer(load_model(model_path, model_version))


def format_feature_name(name: str) -> str:
    return name.replace("_", " ").title()


def get_hostname(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed.netloc or parsed.path or url.strip()


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

          :root {
            --bg: #0b1220;
            --bg-2: #0d1b24;
            --panel: rgba(18, 25, 41, 0.88);
            --panel-soft: rgba(18, 25, 41, 0.74);
            --border: rgba(102, 126, 234, 0.18);
            --text: #f5f7fb;
            --muted: #98a7bf;
            --blue: #3aa0ff;
            --safe: #28d17c;
            --danger: #ff6b81;
          }

          html, body, [class*="css"] {
            font-family: "Manrope", sans-serif;
          }

          .stApp {
            background:
              radial-gradient(circle at top right, rgba(67, 155, 255, 0.12), transparent 22%),
              linear-gradient(90deg, #0b1220 0%, #10212b 100%);
            color: var(--text);
          }

          .block-container {
            max-width: 1240px;
            padding-top: 1.6rem;
            padding-bottom: 3rem;
          }

          header[data-testid="stHeader"],
          div[data-testid="stToolbar"],
          div[data-testid="stDecoration"],
          #MainMenu,
          footer {
            display: none;
          }

          .title {
            font-size: 2.35rem;
            font-weight: 800;
            color: #f7fbff;
            margin: 0;
          }

          .subtitle {
            color: var(--muted);
            font-size: 0.9rem;
            margin-top: 0.45rem;
            margin-bottom: 1.25rem;
          }

          .section-title {
            color: #f4f7fc;
            font-size: 1.9rem;
            font-weight: 800;
            margin-top: 1.15rem;
            margin-bottom: 0.9rem;
          }

          .card {
            background: linear-gradient(180deg, rgba(16, 24, 38, 0.96), rgba(15, 22, 34, 0.94));
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.95rem 1rem;
            min-height: 86px;
          }

          .card-label {
            color: #d8e1ee;
            font-size: 0.88rem;
            margin-bottom: 0.45rem;
          }

          .card-value {
            font-size: 1rem;
            font-weight: 800;
          }

          .safe {
            color: var(--safe);
          }

          .danger {
            color: var(--danger);
          }

          .reason-box {
            background: rgba(53, 117, 177, 0.38);
            border: 1px solid rgba(77, 156, 234, 0.22);
            border-radius: 8px;
            color: #b8d8ff;
            padding: 0.9rem 1rem;
            margin-top: 0.8rem;
            font-size: 0.92rem;
          }

          .raw-copy {
            color: var(--muted);
            font-size: 0.82rem;
            margin-top: 0.75rem;
          }

          .exp-item {
            margin-bottom: 0.7rem;
            color: #e6edf7;
            font-size: 0.95rem;
          }

          .exp-chip {
            display: inline-block;
            padding: 0.18rem 0.45rem;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.8rem;
            margin-right: 0.4rem;
          }

          .exp-pos {
            color: #6de2a6;
          }

          .exp-neg {
            color: #9fd3ff;
          }

          div[data-testid="stTextInput"] label p {
            color: #eef4fc;
            font-weight: 600;
          }

          div[data-testid="stTextInput"] input {
            min-height: 50px;
            border-radius: 8px;
            background: rgba(39, 37, 53, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.04);
            color: #f4f7fb;
          }

          div[data-testid="stButton"] button {
            min-height: 44px;
            border-radius: 9px;
            background: transparent;
            border: 1px solid rgba(255, 118, 118, 0.5);
            color: #dce9ff;
            font-weight: 700;
            box-shadow: none;
          }

          div[data-testid="stProgress"] > div > div {
            background: linear-gradient(90deg, #2da8ff 0%, #4ca7ff 100%);
          }

          div[data-testid="stDataFrame"] {
            border-radius: 10px;
            overflow: hidden;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_card(label: str, value: str, css_class: str = "") -> None:
    st.markdown(
        f"""
        <div class="card">
          <div class="card-label">{label}</div>
          <div class="card-value {css_class}">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


inject_styles()

if "url_input" not in st.session_state:
    st.session_state.url_input = "anonymidentity.net/remax./remax.htm"

st.markdown('<div class="title">PhishGuard AI 🔐</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Explainable phishing URL detection using XGBoost + SHAP</div>',
    unsafe_allow_html=True,
)

url_input = st.text_input("Enter URL", key="url_input")
scan_clicked = st.button("Scan Now 🚀")

prediction_payload: dict[str, object] | None = st.session_state.get("latest_prediction")

if scan_clicked:
    if not url_input.strip():
        st.warning("Please enter a URL to scan.")
    else:
        with st.spinner("Scanning URL..."):
            model_version = get_model_version(MODEL_PATH)
            model = load_model(MODEL_PATH, model_version)
            explainer = load_explainer(MODEL_PATH, model_version)
            threshold = load_threshold(MODEL_PATH)

            feature_dict = extract_url_features(url_input)
            frame = pd.DataFrame([feature_dict], columns=FEATURE_COLUMNS)
            raw_probability = float(model.predict_proba(frame)[0, 1])
            prediction, final_probability, confidence, _, decision_reason = decide_prediction(
                url_input,
                raw_probability,
                threshold,
                feature_dict,
            )

            shap_values = explainer.shap_values(frame)
            single_shap = (
                shap_values[0]
                if hasattr(shap_values, "ndim") and shap_values.ndim == 2
                else shap_values
            )

        ranked = [(feature, float(value)) for feature, value in zip(FEATURE_COLUMNS, single_shap)]
        ranked.sort(key=lambda item: abs(item[1]), reverse=True)
        risk_score = int(round(final_probability * 100))
        prediction_payload = {
            "url": url_input.strip(),
            "status": prediction,
            "raw_probability": raw_probability,
            "probability": final_probability,
            "confidence": confidence,
            "risk_score": risk_score,
            "decision_reason": decision_reason,
            "features": feature_dict,
            "ranked": ranked,
        }
        st.session_state.latest_prediction = prediction_payload

if prediction_payload is None:
    prediction_payload = {
        "url": "anonymidentity.net/remax./remax.htm",
        "status": "safe",
        "raw_probability": 1.0,
        "probability": 0.35,
        "confidence": 0.70,
        "risk_score": 35,
        "decision_reason": "Model score was overridden because URL-level phishing signals were weak.",
        "features": {
            "has_https": 0,
            "url_length": 31,
            "num_subdomains": 1,
            "has_ip_address": 0,
            "has_at_symbol": 0,
            "has_hyphen": 0,
            "num_suspicious_keywords": 0,
        },
        "ranked": [
            ("uses_https", 9.067516),
            ("path_length", 1.286046),
            ("num_subdomains", 0.986361),
            ("num_slashes", -0.841055),
            ("url_length", 0.300962),
        ],
    }

status = str(prediction_payload["status"])
probability = float(prediction_payload["probability"])
raw_probability = float(prediction_payload["raw_probability"])
confidence = float(prediction_payload["confidence"])
risk_score = int(prediction_payload["risk_score"])
decision_reason = str(prediction_payload["decision_reason"])
ranked_features = list(prediction_payload["ranked"])

st.markdown('<div class="section-title">Scan Result</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3, gap="large")
with col1:
    render_card("Prediction", f"{'SAFE' if status == 'safe' else 'PHISHING'}", "safe" if status == "safe" else "danger")
with col2:
    render_card("Confidence", f"{confidence * 100:.2f}%")
with col3:
    render_card("Phishing Probability", f"{probability * 100:.2f}%")

st.markdown(f"Risk Score: {risk_score}/100")
st.progress(risk_score)
st.markdown(f'<div class="reason-box">{decision_reason}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="raw-copy">Raw model score: {raw_probability * 100:.2f}%</div>', unsafe_allow_html=True)

st.markdown('<div class="section-title">Explainability</div>', unsafe_allow_html=True)
st.markdown("Top reasons:")

for feature, value in ranked_features[:5]:
    st.markdown(
        f"""
        <div class="exp-item">
          • <span class="exp-chip">{feature}</span>
          contribution:
          <strong class="{'exp-pos' if value >= 0 else 'exp-neg'}">{value:.6f}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

explainability_df = pd.DataFrame(
    {
        "feature": [feature for feature, _ in ranked_features[:10]],
        "shap_contribution": [round(value, 6) for _, value in ranked_features[:10]],
    }
)
st.dataframe(explainability_df, use_container_width=True, hide_index=True)
