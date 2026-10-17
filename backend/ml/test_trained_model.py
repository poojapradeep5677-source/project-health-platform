"""Minimal integration checks for ML model artifact (run after training)."""
from pathlib import Path
import json
from ml.predictor import MLDefectPredictionService
from ml.train_model import load_dataset
from scoring.risk_scorer import assess_file_risk

ROOT = Path(__file__).resolve().parents[1]

def test_dataset():
    X, y = load_dataset(ROOT / "ml/data/ant-1.7-model-features.csv")
    assert X.shape == (745, 2)
    assert int(y.sum()) == 166

def test_ml_model_load_and_inference():
    service = MLDefectPredictionService(base_dir=str(ROOT))
    assert service.is_available, service.status_message
    assert service.get_status()["active_assessment_mode"] == "ML_MODEL_PREDICTION"
    metrics = {
        "parse_status": "SUCCESS", "loc": 270, "cyclomatic_complexity": 17,
        "max_method_complexity": 5, "maintainability_index": 65.,
        "fan_out": 4, "max_nesting_depth": 1, "code_smells": [],
    }
    result = service.predict_for_file(metrics)
    assert result["prediction_label"] in (0, 1)
    assert 0. <= result["defect_probability"] <= 1.
    # Ant 1.7 is a CLASS-trained model: a file without extracted classes
    # must not be silently scored as an equivalent class.
    assert assess_file_risk(metrics, ml_service=service)["assessment_mode"] == "RULE_BASED_HEURISTIC"
    with_class = dict(metrics, classes_detail=[{
        "class_name": "Example", "loc": 270, "wmc": 17,
        "cyclomatic_complexity": 17, "parse_status": "SUCCESS",
    }])
    scored = assess_file_risk(with_class, ml_service=service)
    assert scored["assessment_mode"] == "ML_MODEL_PREDICTION"
    assert scored["risk_score"] == round(result["defect_probability"] * 100, 2)
    assert assess_file_risk(dict(metrics, parse_status="FAILED"), ml_service=service)["assessment_mode"] == "RULE_BASED_HEURISTIC"
    meta = json.loads((ROOT / "ml/models/model_metadata.json").read_text())
    assert meta["feature_names"] == ["loc", "cyclomatic_complexity"]
