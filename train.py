from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from xgboost import XGBClassifier

from feature_extraction import (
    extract_features_for_series,
    infer_label_column,
    infer_url_column,
    normalize_labels,
)
from trust_layer import looks_like_trusted_institutional_url

LOGGER = logging.getLogger("phishguard.train")
UCI_PHIUSIIL_DATASET_ID = 967


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def resolve_data_path(data_path: str) -> Path:
    path = Path(data_path)
    if path.is_file():
        return path
    if path.is_dir():
        csv_files = sorted(path.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in dataset directory: {path}")
        if len(csv_files) > 1:
            LOGGER.info("Multiple CSV files found in %s; using %s", path, csv_files[0].name)
        return csv_files[0]
    raise FileNotFoundError(f"Dataset path does not exist: {path}")


def load_uci_phiusiil_dataset() -> pd.DataFrame:
    try:
        from ucimlrepo import fetch_ucirepo
    except ImportError as exc:
        raise ImportError(
            "ucimlrepo is required for --data-source uci. Install it with `pip install ucimlrepo`."
        ) from exc

    dataset = fetch_ucirepo(id=UCI_PHIUSIIL_DATASET_ID)
    features = dataset.data.features.copy()
    targets = dataset.data.targets.copy()
    if isinstance(targets, pd.DataFrame):
        target_frame = targets
    else:
        target_frame = pd.DataFrame({"label": targets})
    return pd.concat([features, target_frame], axis=1)


def load_and_prepare(
    data_path: str | None,
    phishing_label: str | int | None = None,
    data_source: str = "csv",
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    if data_source == "uci":
        df = load_uci_phiusiil_dataset()
    else:
        if data_path is None:
            raise ValueError("data_path is required when data_source='csv'")
        resolved_path = resolve_data_path(data_path)
        df = pd.read_csv(resolved_path)

    url_col = infer_url_column(df)
    label_col = infer_label_column(df)

    df = df[[url_col, label_col]].copy()
    df[url_col] = df[url_col].fillna("").astype(str)
    df = df[df[url_col].str.len() > 0]
    df = df.dropna(subset=[label_col])

    X = extract_features_for_series(df[url_col])
    y = pd.Series(normalize_labels(df[label_col], phishing_label=phishing_label), name="label")
    urls = df[url_col].reset_index(drop=True)
    return X, y, urls


def infer_safe_label_value(phishing_label: str | int | None) -> str:
    if phishing_label is None:
        return "0"
    normalized = str(phishing_label).strip().lower()
    if normalized == "0":
        return "1"
    if normalized == "1":
        return "0"
    raise ValueError(
        "augment data without an explicit label column currently requires a binary phishing label of 0 or 1"
    )


def load_augmentation_frame(
    augment_paths: list[str],
    phishing_label: str | int | None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    safe_label_value = infer_safe_label_value(phishing_label)
    for path_str in augment_paths:
        path = resolve_data_path(path_str)
        frame = pd.read_csv(path)
        url_col = infer_url_column(frame)
        if any(candidate in frame.columns for candidate in ["label", "target", "class", "is_phishing", "phishing"]):
            label_col = infer_label_column(frame)
            prepared = frame[[url_col, label_col]].copy()
            prepared.columns = ["url", "label"]
        else:
            prepared = frame[[url_col]].copy()
            prepared.columns = ["url"]
            prepared["label"] = safe_label_value
        prepared["url"] = prepared["url"].fillna("").astype(str)
        prepared = prepared[prepared["url"].str.len() > 0]
        prepared = prepared.dropna(subset=["label"])
        frames.append(prepared)
        LOGGER.info("Loaded augmentation data from %s with %d rows", path, len(prepared))
    if not frames:
        return pd.DataFrame(columns=["url", "label"])
    return pd.concat(frames, ignore_index=True)


def evaluate_trusted_domain_false_positives(
    urls: pd.Series,
    y_true: pd.Series,
    preds: pd.Series,
    features: pd.DataFrame,
) -> dict[str, object]:
    trusted_mask = pd.Series(
        [
            looks_like_trusted_institutional_url(url, feature_row)
            for url, feature_row in zip(urls.tolist(), features.to_dict(orient="records"))
        ],
        index=urls.index,
    )
    trusted_total = int(trusted_mask.sum())
    false_positive_mask = (y_true == 0) & (preds == 1) & trusted_mask
    false_positive_urls = urls[false_positive_mask].head(10).tolist()
    false_positive_total = int(false_positive_mask.sum())
    safe_trusted_total = int(((y_true == 0) & trusted_mask).sum())
    false_positive_rate = 0.0 if safe_trusted_total == 0 else false_positive_total / safe_trusted_total
    return {
        "trusted_total": trusted_total,
        "safe_trusted_total": safe_trusted_total,
        "false_positive_total": false_positive_total,
        "false_positive_rate": false_positive_rate,
        "sample_false_positive_urls": false_positive_urls,
    }


def build_tuned_model(
    random_state: int,
    scale_pos_weight: float,
    search_iterations: int,
) -> RandomizedSearchCV:
    base_model = XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
        n_jobs=-1,
        scale_pos_weight=scale_pos_weight,
    )
    param_distributions = {
        "n_estimators": [200, 300, 500],
        "max_depth": [3, 4, 5, 6],
        "learning_rate": [0.03, 0.05, 0.1],
        "subsample": [0.8, 0.9, 1.0],
        "colsample_bytree": [0.8, 0.9, 1.0],
        "min_child_weight": [1, 2, 4],
        "gamma": [0, 0.1, 0.2],
    }
    return RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_distributions,
        n_iter=search_iterations,
        scoring="recall",
        cv=3,
        n_jobs=-1,
        verbose=0,
        random_state=random_state,
        refit=True,
    )


def build_default_model(random_state: int, scale_pos_weight: float) -> XGBClassifier:
    return XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
        n_jobs=-1,
        scale_pos_weight=scale_pos_weight,
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=2,
        gamma=0.1,
    )


def choose_threshold(y_true: pd.Series, probabilities: pd.Series) -> tuple[float, dict[str, float]]:
    best_threshold = 0.5
    best_metrics = {
        "precision": 0.0,
        "recall": 0.0,
        "f1": -1.0,
    }
    for candidate in [value / 100 for value in range(25, 91)]:
        preds = (probabilities >= candidate).astype(int)
        precision = precision_score(y_true, preds, zero_division=0)
        recall = recall_score(y_true, preds, zero_division=0)
        f1 = f1_score(y_true, preds, zero_division=0)
        score = (f1, precision, recall)
        best_score = (best_metrics["f1"], best_metrics["precision"], best_metrics["recall"])
        if score > best_score:
            best_threshold = candidate
            best_metrics = {
                "precision": float(precision),
                "recall": float(recall),
                "f1": float(f1),
            }
    return best_threshold, best_metrics


def save_model_metadata(
    model_path: str,
    threshold: float,
    data_path: str,
    phishing_label: str | int | None,
) -> Path:
    metadata_path = Path(model_path).with_suffix(".meta.json")
    payload = {
        "threshold": threshold,
        "data_path": data_path,
        "phishing_label": None if phishing_label is None else str(phishing_label),
    }
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return metadata_path


def train(
    data_path: str = "data/urls.csv",
    model_path: str = "models/model.json",
    test_size: float = 0.2,
    random_state: int = 42,
    phishing_label: str | int | None = None,
    search_iterations: int = 4,
    data_source: str = "csv",
    augment_data: list[str] | None = None,
) -> None:
    setup_logging()
    dataset_description = f"UCI dataset id={UCI_PHIUSIIL_DATASET_ID}" if data_source == "uci" else data_path
    LOGGER.info("Loading dataset from %s", dataset_description)
    X, y, urls = load_and_prepare(data_path, phishing_label=phishing_label, data_source=data_source)

    if augment_data:
        augment_frame = load_augmentation_frame(augment_data, phishing_label)
        if not augment_frame.empty:
            augment_X = extract_features_for_series(augment_frame["url"])
            augment_labels = augment_frame["label"].astype(str).str.strip().str.lower()
            safe_label_value = infer_safe_label_value(phishing_label)
            if set(augment_labels.tolist()) == {safe_label_value}:
                augment_y = pd.Series([0] * len(augment_frame), name="label")
            else:
                augment_y = pd.Series(
                    normalize_labels(augment_frame["label"], phishing_label=phishing_label),
                    name="label",
                )
            X = pd.concat([X, augment_X], ignore_index=True)
            y = pd.concat([y, augment_y], ignore_index=True)
            urls = pd.concat([urls, augment_frame["url"].reset_index(drop=True)], ignore_index=True)
            LOGGER.info("Merged %d augmentation rows into training data", len(augment_frame))

    LOGGER.info("Samples: %d | Features: %d", len(X), X.shape[1])
    pos = int(y.sum())
    neg = int(len(y) - pos)
    if pos == 0:
        raise ValueError("Dataset has no positive (phishing) samples.")
    scale_pos_weight = max(neg / pos, 1.0)
    LOGGER.info("Class counts -> positive: %d, negative: %d", pos, neg)
    LOGGER.info("Using scale_pos_weight=%.4f", scale_pos_weight)

    X_train, X_test, y_train, y_test, _, urls_test = train_test_split(
        X, y, urls, test_size=test_size, random_state=random_state, stratify=y
    )

    if search_iterations <= 0:
        LOGGER.info("Running single-model training with fixed hyperparameters...")
        model = build_default_model(
            random_state=random_state,
            scale_pos_weight=scale_pos_weight,
        )
        model.fit(X_train, y_train)
    else:
        search = build_tuned_model(
            random_state=random_state,
            scale_pos_weight=scale_pos_weight,
            search_iterations=search_iterations,
        )
        LOGGER.info("Running hyperparameter tuning...")
        search.fit(X_train, y_train)
        model = search.best_estimator_
        LOGGER.info("Best params: %s", search.best_params_)

    probabilities = pd.Series(model.predict_proba(X_test)[:, 1], index=y_test.index)
    threshold, threshold_metrics = choose_threshold(y_test, probabilities)
    LOGGER.info(
        "Selected threshold %.2f with precision=%.4f recall=%.4f f1=%.4f",
        threshold,
        threshold_metrics["precision"],
        threshold_metrics["recall"],
        threshold_metrics["f1"],
    )

    preds = (probabilities >= threshold).astype(int)
    accuracy = accuracy_score(y_test, preds)
    precision = precision_score(y_test, preds, zero_division=0)
    recall = recall_score(y_test, preds, zero_division=0)
    f1 = f1_score(y_test, preds, zero_division=0)
    matrix = confusion_matrix(y_test, preds)
    per_class_precision, per_class_recall, per_class_f1, _ = precision_recall_fscore_support(
        y_test, preds, labels=[0, 1], zero_division=0
    )
    trusted_eval = evaluate_trusted_domain_false_positives(
        urls=urls_test.reset_index(drop=True),
        y_true=y_test.reset_index(drop=True),
        preds=preds.reset_index(drop=True),
        features=X_test.reset_index(drop=True),
    )

    print("Evaluation Metrics")
    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")
    print("\nConfusion Matrix:")
    print(matrix)
    print("\nPer-Class Metrics:")
    print(
        f"Legitimate (0) -> precision={per_class_precision[0]:.4f} recall={per_class_recall[0]:.4f} f1={per_class_f1[0]:.4f}"
    )
    print(
        f"Phishing   (1) -> precision={per_class_precision[1]:.4f} recall={per_class_recall[1]:.4f} f1={per_class_f1[1]:.4f}"
    )
    print("\nTrusted-Domain False Positive Analysis:")
    print(f"Trusted-domain samples in test set: {trusted_eval['trusted_total']}")
    print(f"Safe trusted-domain samples     : {trusted_eval['safe_trusted_total']}")
    print(f"False positives on trusted URLs : {trusted_eval['false_positive_total']}")
    print(f"Trusted false positive rate     : {trusted_eval['false_positive_rate']:.4f}")
    if trusted_eval["sample_false_positive_urls"]:
        print("Sample trusted-domain false positives:")
        for sample_url in trusted_eval["sample_false_positive_urls"]:
            print(f"- {sample_url}")
    print("\nClassification Report:")
    print(classification_report(y_test, preds, digits=4, zero_division=0))

    out = Path(model_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(out))
    LOGGER.info("Saved model to %s", out)
    metadata_path = save_model_metadata(
        model_path=model_path,
        threshold=threshold,
        data_path=dataset_description,
        phishing_label=phishing_label,
    )
    LOGGER.info("Saved model metadata to %s", metadata_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train phishing URL detector.")
    parser.add_argument("--data", default="data/urls.csv", help="Path to CSV dataset")
    parser.add_argument(
        "--data-source",
        choices=["csv", "uci"],
        default="csv",
        help="Load training data from a local CSV path or fetch PhiUSIIL from the UCI repository",
    )
    parser.add_argument(
        "--model-out",
        default="models/model.json",
        help="Where to save trained model",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--phishing-label",
        default=None,
        help="Raw label value that should be treated as phishing, for example 0 for PhiUSIIL",
    )
    parser.add_argument(
        "--search-iterations",
        type=int,
        default=4,
        help="Number of randomized hyperparameter trials to run",
    )
    parser.add_argument(
        "--augment-data",
        action="append",
        default=[],
        help="Optional CSV file or folder of additional URLs to merge into training. If no label column exists, rows are treated as legitimate URLs.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        data_path=args.data,
        model_path=args.model_out,
        test_size=args.test_size,
        random_state=args.random_state,
        phishing_label=args.phishing_label,
        search_iterations=args.search_iterations,
        data_source=args.data_source,
        augment_data=args.augment_data,
    )
