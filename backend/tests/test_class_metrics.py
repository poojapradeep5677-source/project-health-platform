"""Regression tests for class-scoped defect predictions and API persistence."""
import io
import os
from pathlib import Path
import tempfile
import zipfile

from analyzer.java_analyzer import analyze_java_file
from ml.predictor import MLDefectPredictionService
from scoring.risk_scorer import assess_file_risk
from app import create_app

BACKEND = Path(__file__).resolve().parents[1]

TWO_CLASSES = """package sample;
/* { braces inside comments must not close a class } */
class Small {
    String literal = "{ nested }";
    void fast() {}
}
class Large {
    int score(int a, int b) {
        if (a > 2) { return 1; }
        if (b > 3) { return 2; }
        return 0;
    }
    void helper() {}
}
"""

NESTED = """public class Outer {
    void parent() {}
    static class Inner {
        int nested(int a) { if (a > 0) return a; return 0; }
    }
}
"""


def analyze(source):
    with tempfile.TemporaryDirectory() as temp:
        src = Path(temp) / "Multi.java"
        src.write_text(source, encoding="utf-8")
        return analyze_java_file(str(src), "src/Multi.java", "Multi.java")


def test_multiple_classes_and_brace_safe_scope():
    metrics = analyze(TWO_CLASSES)
    assert metrics["parse_status"] == "SUCCESS"
    classes = metrics["classes_detail"]
    assert [c["class_name"] for c in classes] == ["Small", "Large"]
    assert len(classes) == 2
    assert classes[0]["method_count"] == 1
    assert classes[0]["wmc"] == 1
    assert classes[1]["method_count"] == 2
    assert classes[1]["wmc"] == 4
    assert classes[0]["loc"] < metrics["loc"]
    assert classes[1]["loc"] < metrics["loc"]
    assert all(c["end_line"] >= c["start_line"] for c in classes)


def test_nested_classes_do_not_double_count_wmc():
    classes = analyze(NESTED)["classes_detail"]
    assert [c["class_name"] for c in classes] == ["Outer", "Outer.Inner"]
    assert classes[0]["wmc"] == 1
    assert classes[1]["wmc"] == 2


def test_class_predictions_and_file_aggregation():
    service = MLDefectPredictionService(base_dir=str(BACKEND))
    assert service.is_available, service.status_message
    metrics = analyze(TWO_CLASSES)
    score = assess_file_risk(metrics, ml_service=service)
    assert score["assessment_mode"] == "ML_MODEL_PREDICTION"
    prediction_factor = next(f for f in score["contributing_factors"]
                             if f["factor"] == "Class-Level Java Metrics and ML Predictions")
    predictions = prediction_factor["class_predictions"]
    assert len(predictions) == 2
    for extracted, predicted in zip(metrics["classes_detail"], predictions):
        assert predicted["class_name"] == extracted["class_name"]
        assert predicted["defect_probability"] == service.predict_for_file(extracted)["defect_probability"]
    assert score["ml_defect_probability"] == max(p["defect_probability"] for p in predictions)
    assert score["risk_score"] == round(100 * score["ml_defect_probability"], 2)

    # Interfaces only and parse failures cannot be fed to the CLASS model.
    interface_metrics = analyze("interface I { void perform(); }")
    assert interface_metrics["classes_detail"] == []
    assert assess_file_risk(interface_metrics, ml_service=service)["assessment_mode"] == "RULE_BASED_HEURISTIC"
    assert assess_file_risk(dict(metrics, parse_status="PARSE_ERROR"), ml_service=service)["assessment_mode"] == "RULE_BASED_HEURISTIC"


def test_project_api_returns_persisted_class_predictions():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(Path(tmp) / "test.db"),
            "UPLOADS_DIR": str(Path(tmp) / "uploads"),
            "TEMP_EXTRACT_DIR": str(Path(tmp) / "extract"),
            "DATA_DIR": str(Path(tmp) / "data"),
        })
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("src/Multi.java", TWO_CLASSES)
        archive.seek(0)
        with app.test_client() as client:
            res = client.post("/api/projects/upload", data={
                "file": (archive, "class-scoped.zip"), "project_name": "Class-scoped smoke test",
            }, content_type="multipart/form-data")
            assert res.status_code == 201, res.get_json()
            run_id = res.get_json()["data"]["analysis_run"]["id"]
            detail = client.get(f"/api/analysis/{run_id}").get_json()["data"]
            assert detail["scoring_mode"] == "ML_MODEL_PREDICTION"
            file_data = detail["files"][0]
            assert len(file_data["class_metrics"]) == 2
            assert len(file_data["class_predictions"]) == 2
            assert file_data["assessment_mode"] == "ML_MODEL_PREDICTION"
            risks = client.get(f"/api/analysis/{run_id}/risks").get_json()["data"]["risks"]
            assert len(risks[0]["class_predictions"]) == 2
