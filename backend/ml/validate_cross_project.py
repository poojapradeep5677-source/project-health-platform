"""Evaluate the frozen Ant 1.7 defect classifier on DIFFERENT Java projects.

No training or hyperparameter tuning is performed on external samples.
This assesses transfer between Jureczko CK-metric datasets, not runtime
file-level reliability or the exact metrics produced by our AST extractor.
"""
from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
)

ROOT = Path(__file__).resolve().parent
TEST_PROJECTS = ["ivy-2.0.csv", "jedit-4.2.csv"]


def main():
    trained = joblib.load(ROOT / "models/defect_predictor.joblib")
    features = trained["feature_names"]
    model = trained["model"]
    rows = []
    for filename in TEST_PROJECTS:
        df = pd.read_csv(ROOT / "data" / filename)
        expected = {"loc", "wmc", "bug"}
        if not expected.issubset(set(df.columns)):
            raise ValueError(f"{filename} missing expected columns")
        X = df[["loc", "wmc"]].rename(columns={"wmc": "cyclomatic_complexity"})[features]
        y = (df["bug"] > 0).astype(int)
        p = model.predict_proba(X)[:, 1]
        pred = model.predict(X)
        rows.append({
            "dataset": filename,
            "classes": len(y),
            "defective_classes": int(y.sum()),
            "accuracy": round(float(accuracy_score(y, pred)), 4),
            "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
            "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
        })
    directory = ROOT / "models"
    (directory / "cross_project_validation.json").write_text(
        json.dumps({
            "training_dataset": "ant-1.7.csv",
            "training_features": ["loc", "wmc"],
            "datasets": rows,
            "limitation": "External CK-feature transfer only. App's class LOC/WMC proxies may not match training tool definitions.",
        }, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame([{k: v for k, v in row.items() if k != "confusion_matrix"}
                  for row in rows]).to_csv(directory / "cross_project_validation.csv", index=False)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
