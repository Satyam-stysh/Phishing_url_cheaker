from __future__ import annotations

import base64
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

DEFAULT_RENDER_BACKEND_URL = "https://phishguard-api-xxxx.onrender.com"


def get_backend_url() -> str:
    configured_url = os.getenv("BACKEND_URL", DEFAULT_RENDER_BACKEND_URL).strip()
    is_render = bool(os.getenv("RENDER"))

    # Use the local API during development when no real public backend URL is configured.
    if not configured_url or "xxxx" in configured_url:
        if is_render:
            raise RuntimeError(
                "BACKEND_URL is not configured with the real public Render backend URL."
            )
        configured_url = "http://127.0.0.1:8000"

    configured_url = configured_url.rstrip("/")
    if not configured_url.startswith("http"):
        raise RuntimeError("BACKEND_URL must start with http:// or https://")

    return configured_url


BACKEND_URL = get_backend_url()

st.set_page_config(page_title="PhishGuard AI", page_icon="🔐", layout="wide")

st.markdown(
    """
    <style>
      :root {
        --bg: #081019;
        --bg-deep: #050b13;
        --surface: rgba(12, 21, 35, 0.94);
        --surface-strong: rgba(11, 19, 31, 0.98);
        --surface-soft: rgba(39, 96, 148, 0.16);
        --border: rgba(87, 120, 156, 0.24);
        --line: rgba(108, 149, 182, 0.14);
        --cyan: #66b7ee;
        --cyan-strong: #2e89d9;
        --lime: #86f0b4;
        --text: #edf4fe;
        --muted: #9caabd;
        --danger: #ff8080;
        --success: #58da8c;
        --warning: #f6c56f;
      }
      .stApp {
        background:
          radial-gradient(circle at top right, rgba(29, 97, 139, 0.34), transparent 24%),
          radial-gradient(circle at 82% 72%, rgba(24, 91, 87, 0.22), transparent 28%),
          linear-gradient(180deg, #0a1118 0%, #0b1720 48%, #0a2025 100%);
        color: var(--text);
      }
      .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1210px;
      }
      header[data-testid="stHeader"] {
        display: none;
      }
      div[data-testid="stToolbar"] {
        display: none;
      }
      div[data-testid="stDecoration"] {
        display: none;
      }
      #MainMenu {
        visibility: hidden;
      }
      div[data-testid="stAppViewContainer"] > section > div:first-child {
        padding-top: 0;
      }
      .section-card, .input-card, .metric-card, .hero-panel {
        border: 1px solid var(--border);
        background: linear-gradient(180deg, rgba(11, 18, 31, 0.95), rgba(8, 14, 25, 0.98));
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.22);
        backdrop-filter: blur(10px);
      }
      .scanner-shell {
        margin-bottom: 0.9rem;
      }
      .section-card {
        padding: 1.15rem 1.25rem;
        border-radius: 14px;
        height: 100%;
      }
      .metric-card {
        border-radius: 12px;
        padding: 0.9rem 1rem;
        min-height: 94px;
      }
      .metric-label {
        color: #dbe7f7;
        font-size: 0.85rem;
        letter-spacing: 0.02em;
      }
      .metric-value {
        display: block;
        font-size: 1.15rem;
        line-height: 1.1;
        font-weight: 800;
        margin-top: 0.75rem;
      }
      .metric-helper {
        color: var(--muted);
        font-size: 0.86rem;
        margin-top: 0.35rem;
      }
      .pred-safe { color: var(--success); }
      .pred-phish { color: var(--danger); }
      .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.85rem;
        color: #f4f8ff;
      }
      .section-copy {
        color: var(--muted);
        font-size: 0.92rem;
        margin-top: -0.35rem;
        margin-bottom: 0.95rem;
      }
      .explain-item {
        padding: 0.65rem 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      }
      .explain-item:last-child {
        border-bottom: none;
        padding-bottom: 0;
      }
      .feature-name {
        font-weight: 700;
        color: var(--text);
      }
      .feature-meta {
        color: var(--muted);
        font-size: 0.92rem;
        margin-top: 0.18rem;
      }
      .feature-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        border-radius: 8px;
        padding: 0.12rem 0.4rem;
        background: rgba(44, 137, 217, 0.1);
        border: 1px solid rgba(44, 137, 217, 0.14);
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        font-size: 0.8rem;
        color: #8fe0ae;
      }
      .decision-note {
        border-radius: 8px;
        padding: 0.9rem 1rem;
        background: linear-gradient(90deg, rgba(26, 84, 132, 0.56), rgba(40, 96, 139, 0.52));
        border: 1px solid rgba(78, 148, 210, 0.18);
        margin-top: 0.8rem;
        color: var(--text);
        font-size: 0.92rem;
      }
      .page-shell {
        padding: 0.1rem 0 0;
      }
      .page-intro {
        margin-bottom: 0.35rem;
      }
      .page-kicker {
        color: var(--text);
        font-size: 2.3rem;
        font-weight: 800;
        line-height: 1.02;
        margin: 0;
      }
      .page-lock {
        font-size: 2rem;
        vertical-align: -0.1em;
      }
      .page-title {
        color: var(--muted);
        font-size: 0.74rem;
        font-weight: 500;
        line-height: 1.4;
        margin: 0.7rem 0 0;
      }
      .page-subtitle {
        display: none;
      }
      .input-card {
        border-radius: 12px;
        padding: 0;
        margin-bottom: 0.85rem;
        background: transparent;
        border: none;
      }
      .input-title {
        color: var(--text);
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 0.45rem;
        text-transform: none;
      }
      .input-subtitle {
        display: none;
      }
      .scan-tip {
        color: var(--muted);
        font-size: 0.85rem;
        margin-top: 0.7rem;
      }
      div[data-testid="stTextInput"] label p {
        color: var(--text);
        font-weight: 700;
      }
      div[data-testid="stTextInput"] input {
        min-height: 44px;
        border-radius: 8px;
        border: 1px solid rgba(82, 100, 123, 0.14);
        background: rgba(39, 40, 54, 0.94);
        color: var(--text);
        caret-color: var(--cyan);
        font-size: 0.92rem;
        padding-left: 1rem;
        box-shadow: none;
      }
      div[data-testid="stTextInput"] input::placeholder {
        color: #7f8a98;
        opacity: 1;
      }
      div[data-testid="stTextInput"] input:focus {
        border-color: #b45b5b;
        box-shadow: 0 0 0 1px rgba(180, 91, 91, 0.52);
      }
      div[data-testid="stButton"] button {
        min-height: 40px;
        border-radius: 8px;
        background: rgba(21, 28, 40, 0.88);
        color: #dce7f6;
        border: 2px solid #a65050;
        padding: 0 0.95rem;
        font-weight: 700;
        box-shadow: none;
        white-space: nowrap;
      }
      .scan-button-row {
        max-width: 130px;
        margin-top: 0.5rem;
      }
      div[data-testid="stButton"] button:hover {
        background: rgba(26, 33, 49, 0.95);
        border-color: #c86767;
        color: #ffffff;
      }
      .results-heading {
        color: var(--text);
        font-size: 1.7rem;
        font-weight: 800;
        line-height: 1.1;
        margin: 1.4rem 0 0.9rem;
      }
      .risk-label {
        color: #cfd8e8;
        font-size: 0.92rem;
        margin: 0.1rem 0 0.45rem;
      }
      .raw-copy {
        color: var(--muted);
        font-size: 0.78rem;
        margin-top: 0.65rem;
      }
      div[data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #2c89d9, #44a6ff);
      }
      div[data-testid="stProgress"] > div {
        background: rgba(43, 49, 63, 0.72);
      }
      div[data-testid="stCaptionContainer"] {
        color: var(--muted);
      }
      div[data-testid="stDataFrame"] {
        background: rgba(10, 19, 35, 0.75);
        border: 1px solid var(--border);
        border-radius: 18px;
        overflow: hidden;
      }
      @media (max-width: 900px) {
        .page-kicker {
          font-size: 1.9rem;
        }
        .page-title {
          font-size: 0.72rem;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="page-shell">
      <div class="page-intro">
        <h1 class="page-kicker">PhishGuard AI <span class="page-lock">🔐</span></h1>
        <p class="page-title">Explainable phishing URL detection using XGBoost + SHAP</p>
      </div>
      <div class="scanner-shell">
        <div class="input-card">
          <div class="input-title">Enter URL</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
url = st.text_input(
    "Enter URL",
    placeholder="anonymeidentity.net/remax./remax.htm",
    label_visibility="collapsed",
)
st.markdown('<div class="scan-button-row">', unsafe_allow_html=True)
scan = st.button("Scan Now 🚀", use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)
st.markdown(
    '<div class="scan-tip">Tip: include the full link, including <code>https://</code>, for the most reliable result.</div>',
    unsafe_allow_html=True,
)

if scan:
    if not url.strip():
        st.warning("Please enter a URL first.")
    else:
        with st.spinner("Scanning URL and generating SHAP explanation..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/predict", json={"url": url.strip()}, timeout=30
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
            except requests.RequestException as exc:
                st.error(f"Backend request failed: {exc}")
                payload = {}

        if payload:
            prediction = payload.get("prediction", "unknown")
            probability = float(payload.get("probability", 0.0))
            raw_model_probability = float(payload.get("raw_model_probability", probability))
            confidence = float(payload.get("confidence", 0.0))
            risk_score = int(payload.get("risk_score", 0))
            decision_reason = payload.get("decision_reason")
            top_features = payload.get("explanation", [])

            prediction_text = "Safe" if prediction == "safe" else "Phishing"
            prediction_class = "pred-safe" if prediction == "safe" else "pred-phish"
            risk_tone = "Low risk" if risk_score < 35 else "Elevated risk" if risk_score < 70 else "High risk"

            st.markdown('<div class="results-heading">Scan Result</div>', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            with col1:
                pred_text = "✅ SAFE" if prediction == "safe" else "⚠️ PHISHING"
                st.markdown(
                    f"""
                    <div class="metric-card">
                      <div class="metric-label">Prediction</div>
                      <span class="metric-value {prediction_class}">{pred_text}</span>
                      <div class="metric-helper">{risk_tone}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f"""
                    <div class="metric-card">
                      <div class="metric-label">Confidence</div>
                      <span class="metric-value">{confidence * 100:.2f}%</span>
                      <div class="metric-helper">Final decision certainty</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(
                    f"""
                    <div class="metric-card">
                      <div class="metric-label">Phishing Probability</div>
                      <span class="metric-value">{probability * 100:.2f}%</span>
                      <div class="metric-helper">Raw phishing probability</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown(
                f'<div class="risk-label">Risk Score: {risk_score}/100</div>',
                unsafe_allow_html=True,
            )
            st.progress(
                risk_score,
                text="",
            )
            if decision_reason:
                st.markdown(
                    f'<div class="decision-note">{decision_reason}</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<div class="raw-copy">Raw model score: {raw_model_probability * 100:.2f}%</div>',
                unsafe_allow_html=True,
            )

            explain_col, chart_col = st.columns([1, 1.35], gap="large")
            with explain_col:
                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Explainability</div>', unsafe_allow_html=True)
                st.markdown('<div class="section-copy">Top reasons:</div>', unsafe_allow_html=True)
                if top_features:
                    for item in top_features:
                        label = item["feature"]
                        st.markdown(
                            f"""
                            <div class="explain-item">
                              <div class="feature-meta">• <span class="feature-pill">{label}</span> contribution: {item['contribution']:+.6f}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    table = pd.DataFrame(top_features).rename(
                        columns={"contribution": "shap_contribution"}
                    )
                    st.dataframe(table, width="stretch", hide_index=True)
                else:
                    st.write("No explanation items were returned for this scan.")
                st.markdown("</div>", unsafe_allow_html=True)

            shap_base64 = payload.get("shap_plot_base64")
            with chart_col:
                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Feature Breakdown</div>', unsafe_allow_html=True)
                if shap_base64:
                    st.image(base64.b64decode(shap_base64), width="stretch")
                else:
                    st.write("Chart unavailable for this scan.")
                st.markdown("</div>", unsafe_allow_html=True)
