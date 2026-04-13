# PhishGuard AI: Explainable Phishing URL Detection

Production-style full-stack system:
- ML training pipeline (`train.py`)
- Explainability utilities (`explain.py`)
- FastAPI backend (`backend/api.py`)
- Streamlit frontend (`frontend/app.py`)

## Project Structure

```text
phishguard-ai/
├── data/
│   ├── trusted_domains.txt
│   └── urls.csv
├── models/
│   ├── model.json
│   └── model.meta.json
├── backend/
│   ├── __init__.py
│   └── api.py
├── frontend/
│   └── app.py
├── scripts/
│   └── download_phiusiil.py
├── decision_utils.py
├── explain.py
├── feature_extraction.py
├── model_utils.py
├── predict.py
├── train.py
├── trust_layer.py
├── render.yaml
├── requirements.txt
└── README.md
```

## Features Used

- URL length
- Number of dots
- Number of subdomains
- Presence of `@`
- Presence of `-`
- HTTPS usage
- Presence of IP address in host
- Suspicious keyword count (`login`, `secure`, `verify`, `bank`)

## Training Flow

1. Load CSV dataset (`url` + label column such as `label`, `target`, `is_phishing`)
2. Handle missing values and invalid rows
3. Extract URL features
4. Split train/test (80/20)
5. Train XGBoost with:
   - class imbalance support (`scale_pos_weight`)
   - randomized hyperparameter tuning
6. Evaluate:
   - Accuracy
   - Precision
   - Recall
   - F1-score
7. Save model to `models/model.json`

## API Contract

- `POST /predict`
- Request:

```json
{
  "url": "https://example.com"
}
```

- Response:

```json
{
  "prediction": "phishing",
  "probability": 0.92,
  "confidence": 0.92,
  "risk_score": 92,
  "explanation": [
    {"feature": "num_suspicious_keywords", "contribution": 0.81}
  ],
  "shap_values": {"url_length": 0.14},
  "shap_plot_base64": "..."
}
```

## Install

```bash
pip install -r requirements.txt
```

## Run Instructions

1. Train locally:

```bash
python train.py
```

Train on the Kaggle PhiUSIIL dataset downloaded with `kagglehub`:

```python
import kagglehub

path = kagglehub.dataset_download("kaggleprollc/phishing-url-websites-dataset-phiusiil")
print(path)
```

```bash
python train.py --data /path/from/kagglehub --phishing-label 0
```

This dataset uses `label = 0` for phishing and `label = 1` for legitimate URLs, so `--phishing-label 0` is required.

2. Start backend:

```bash
uvicorn backend.api:app --reload
```

3. Run Streamlit frontend:

```bash
streamlit run frontend/app.py
```

## Deploy On Render

This repo includes a Render blueprint at [`render.yaml`](/teamspace/studios/this_studio/render.yaml) that creates:
- `phishguard-api` as a FastAPI web service
- `phishguard-frontend` as a Streamlit web service

How to deploy:

1. Push this project to GitHub.
2. In Render, choose `New +` -> `Blueprint`.
3. Connect the GitHub repo that contains this project.
4. Render will detect `render.yaml` and propose both services.
5. Approve the blueprint and deploy.

The frontend automatically connects to the backend over Render's private network using the `BACKEND_HOSTPORT` environment variable defined in the blueprint. For local development, the frontend falls back to `http://127.0.0.1:8000` unless you set `BACKEND_URL` yourself.

## SHAP Utilities

Generate prediction explanation + plots from CLI:

```bash
python explain.py --url "https://example.com/login"
```

Outputs:
- `models/shap_single_bar.png`
- `models/shap_summary.png`

## Notes

- For best performance, use a real phishing dataset with enough samples and balanced representation.
- Accuracy can approach high levels only with richer datasets and careful feature engineering; results on toy datasets will be lower.
