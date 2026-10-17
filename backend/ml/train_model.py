"""Train a reproducible research-baseline classifier on Apache Ant 1.7 class metrics.

IMPORTANT: Ant 1.7 WMC is only a proxy for this application's file-level
cyclomatic_complexity. Its reported test metrics do NOT validate performance
on new projects or imply calibrated real-world defect probabilities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, balanced_accuracy_score,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BASE = Path(__file__).resolve().parent
DEFAULT_DATA = BASE / "data" / "ant-1.7-model-features.csv"
DEFAULT_OUTPUT = BASE / "models"
FEATURE_NAMES = ["loc", "cyclomatic_complexity"]
COLUMN_MAPPING = {"loc": "loc", "wmc": "cyclomatic_complexity"}


def load_dataset(path: Path):
    df = pd.read_csv(path)
    expected = set(COLUMN_MAPPING) | {"bug"}
    if not expected.issubset(df.columns):
        raise ValueError(f"Missing required columns: {sorted(expected - set(df.columns))}")
    X = df[list(COLUMN_MAPPING)].rename(columns=COLUMN_MAPPING).apply(pd.to_numeric, errors="raise")
    y = (pd.to_numeric(df["bug"], errors="raise") > 0).astype(int)
    if not np.isfinite(X.to_numpy()).all() or len(X) != 745 or int(y.sum()) != 166:
        raise ValueError("Unexpected Ant 1.7 records, defective count, or nonfinite feature values")
    return X[FEATURE_NAMES], y


def evaluate(y, model, X):
    p = model.predict_proba(X)[:, 1]
    pred = model.predict(X)
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "average_precision": round(float(average_precision_score(y, p)), 4),
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    X, y = load_dataset(args.dataset)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    search = GridSearchCV(
        RandomForestClassifier(random_state=42, n_jobs=1, class_weight="balanced_subsample"),
        {"n_estimators": [200], "max_depth": [4, 8, None], "min_samples_leaf": [2, 5, 10]},
        scoring="average_precision",
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
        n_jobs=1, refit=True,
    )
    search.fit(X_train, y_train)
    rf = search.best_estimator_
    logistic = make_pipeline(
        StandardScaler(),
        LogisticRegression(random_state=42, max_iter=1000, class_weight="balanced"),
    )
    logistic.fit(X_train, y_train)
    baseline_p = np.full(len(y_test), float(y_train.mean()))
    baseline_pred = np.zeros(len(y_test), dtype=int)
    results = {
        "majority_class_baseline": {
            "accuracy": round(float(accuracy_score(y_test, baseline_pred)), 4),
            "precision": 0.0, "recall": 0.0, "f1": 0.0, "roc_auc": 0.5,
            "confusion_matrix": confusion_matrix(y_test, baseline_pred, labels=[0, 1]).tolist(),
        },
        "random_forest": evaluate(y_test, rf, X_test),
        "logistic_regression": evaluate(y_test, logistic, X_test),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": rf, "feature_names": FEATURE_NAMES,
        "model_name": "Ant17RandomForestDefectRisk", "version": "0.7.0",
    }
    joblib.dump(artifact, args.output / "defect_predictor.joblib", compress=3)
    metadata = {
        "model_name": artifact["model_name"], "version": artifact["version"],
        "feature_names": FEATURE_NAMES,
        "training_columns_mapped_to_analyzer": COLUMN_MAPPING,
        "dataset_name": "PROMISE/Jureczko Apache Ant 1.7",
        "source_url": "https://zenodo.org/records/268440",
        "training_data_mirror": "https://github.com/pravaliManchala/SDP/blob/main/ant-1.7.csv",
        "training_csv_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "total_rows": len(y), "defective_rows": int(y.sum()),
        "training_rows": len(y_train), "test_rows": len(y_test),
        "split": "80/20 stratified, random_state=42",
        "selection": "Random Forest 5-fold cross-validated average precision on train split",
        "best_params": search.best_params_,
        "cv_average_precision": round(float(search.best_score_), 4),
        "sklearn_version": sklearn.__version__,
        "evaluation": results,
        "limitations": [
            "Dataset samples are Java classes, app predictions are Java files.",
            "WMC is not identical to file-level aggregate cyclomatic complexity.",
            "LOC counting conventions may differ.",
            "Not evaluated on independent projects; model scores are not calibrated.",
        ],
    }
    (args.output / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (args.output / "evaluation_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    pd.DataFrame([{"model": name, **{k: v for k, v in score.items() if k != "confusion_matrix"}}
                  for name, score in results.items()]).to_csv(args.output / "evaluation_results.csv", index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import ConfusionMatrixDisplay
        fig, ax = plt.subplots(figsize=(5, 4))
        ConfusionMatrixDisplay.from_predictions(
            y_test, rf.predict(X_test), labels=[0, 1],
            display_labels=["Clean", "Defective"], colorbar=False, ax=ax,
        )
        ax.set_title("Ant 1.7 Random Forest: held-out test")
        fig.tight_layout()
        fig.savefig(args.output / "confusion_matrix.png", dpi=160)
        plt.close(fig)
    except ImportError:
        pass
    print(json.dumps({"best_params": search.best_params_, "scores": results}, indent=2))


if __name__ == "__main__":
    main()
