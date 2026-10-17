"""Full-stack Flask/API smoke using the REAL serialized Ant 1.7 model.

Unlike isolated ML tests, this runs ZIP upload -> AST extraction -> class ML
predictions -> SQLite persistence -> dashboard/analytics/PDF/history.
Tests intentionally avoid altering the developer's database or uploads.
"""
import io
from pathlib import Path
import tempfile
import zipfile

from app import create_app

ROOT = Path(__file__).resolve().parents[1]


def make_project_zip():
    files = {
        "src/shop/Order.java": """package shop;
public class Order {
    private int total;
    public int amount(int items, boolean discount) {
        if (items > 10 && discount) { return items * 9; }
        if (discount) return items * 8;
        return items * 10;
    }
}
class OrderValidator {
    boolean valid(int count) {
        if (count < 0) return false;
        if (count > 100) return false;
        return true;
    }
}
""",
        "src/shop/Basket.java": """package shop;
public class Basket {
    private int size = 0;
    public void add() { size++; }
    public boolean hasItems() { return size > 0; }
    static class Entry { public boolean active() { return true; } }
}
""",
        "src/shop/Catalog.java": """package shop;
import java.util.ArrayList;
public class Catalog {
    private ArrayList<String> products = new ArrayList<String>();
    public int listSize() { return products.size(); }
    public boolean large() { if (products.size() > 30) return true; return false; }
}
""",
        "src/shop/Contract.java": "package shop; public interface Contract { void validate(); }",
        "src/shop/Broken.java": "package shop; public class Broken { void invalid( { }",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, source in files.items():
            zf.writestr(path, source)
    buf.seek(0)
    return buf


def ok(client, path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.get_json(silent=True))
    body = response.get_json()
    assert body["success"], (path, body)
    return body["data"]


def test_full_application_live_ml_analysis_pipeline():
    with tempfile.TemporaryDirectory(prefix="version007_e2e_") as tmp:
        temp = Path(tmp)
        app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{temp / 'analysis.db'}",
            "UPLOADS_DIR": str(temp / "uploads"),
            "TEMP_EXTRACT_DIR": str(temp / "extract"),
            "DATA_DIR": str(temp / "data"),
        })
        with app.test_client() as client:
            health = ok(client, "/api/health")
            assert health["database"] == "connected"
            assert health["ml_status"]["active_assessment_mode"] == "ML_MODEL_PREDICTION"
            assert health["ml_status"]["model_name"] == "Ant17RandomForestDefectRisk"

            upload = client.post("/api/projects/upload", data={
                "file": (make_project_zip(), "order-service.zip"),
                "project_name": "Order Service E2E",
                "version_label": "v1-before",
            }, content_type="multipart/form-data")
            assert upload.status_code == 201, upload.get_json(silent=True)
            result = upload.get_json()["data"]
            pid = result["project"]["id"]
            run = result["analysis_run"]
            rid = run["id"]
            assert run["total_files"] == 5
            assert run["parsed_files"] == 4
            assert run["failed_files"] == 1
            assert run["scoring_mode"] == "ML_MODEL_PREDICTION"
            assert 0 <= run["health_score"] <= 100

            analysis = ok(client, f"/api/analysis/{rid}")
            files = {item["file_name"]: item for item in analysis["files"]}
            assert len(files) == 5
            order = files["Order.java"]
            assert order["parse_status"] == "SUCCESS"
            assert [entry["class_name"] for entry in order["class_metrics"]] == [
                "Order", "OrderValidator",
            ]
            assert len(order["class_predictions"]) == 2
            assert order["assessment_mode"] == "ML_MODEL_PREDICTION"
            probs = [p["defect_probability"] for p in order["class_predictions"]]
            assert all(0 <= p <= 1 for p in probs)
            assert order["ml_defect_probability"] == max(probs)
            assert abs(order["risk_score"] - 100 * max(probs)) < .02

            basket = files["Basket.java"]
            assert [entry["class_name"] for entry in basket["class_metrics"]] == ["Basket", "Basket.Entry"]
            assert len(basket["class_predictions"]) == 2
            assert files["Contract.java"]["assessment_mode"] == "RULE_BASED_HEURISTIC"
            assert files["Broken.java"]["assessment_mode"] == "RULE_BASED_HEURISTIC"
            assert not files["Broken.java"]["class_predictions"]

            project = ok(client, f"/api/projects/{pid}")
            assert project["id"] == pid
            assert len(ok(client, "/api/projects")) == 1
            assert len(project["runs"]) == 1

            dash = ok(client, f"/api/dashboard?project_id={pid}")
            assert dash["has_project"]
            assert dash["has_history"] is False

            metric_stats = ok(client, f"/api/analysis/{rid}/metrics")
            assert "loc" in metric_stats["summary_statistics"]
            corr = ok(client, f"/api/analysis/{rid}/correlations")
            assert "matrix" in corr

            risks = ok(client, f"/api/analysis/{rid}/risks")
            assert len(risks["risks"]) == 5
            r_order = next(x for x in risks["risks"] if x["file_name"] == "Order.java")
            assert len(r_order["class_predictions"]) == 2

            priorities = ok(client, f"/api/analysis/{rid}/priorities")
            assert len(priorities["priorities"]) == 5

            report = client.get(f"/api/analysis/{rid}/report")
            assert report.status_code == 200
            assert report.mimetype == "application/pdf"
            assert report.data.startswith(b"%PDF-")
            assert len(report.data) > 1500

            repeat = client.post(f"/api/projects/{pid}/analyze", json={
                "version_label": "v2-repeat",
            })
            assert repeat.status_code == 201, repeat.get_json(silent=True)
            rid2 = repeat.get_json()["data"]["analysis_run"]["id"]
            assert rid != rid2
            history = ok(client, f"/api/projects/{pid}/history")
            assert history is not None
            comparison = ok(client, f"/api/projects/{pid}/compare?first={rid}&second={rid2}")
            assert "metric_comparisons" in comparison
            dash2 = ok(client, f"/api/dashboard?project_id={pid}")
            assert dash2["has_history"]

            bad_upload = client.post("/api/projects/upload", data={
                "file": (io.BytesIO(b"not a zip"), "invalid.zip"),
                "project_name": "Reject corrupted archive",
            }, content_type="multipart/form-data")
            assert bad_upload.status_code == 400
            assert bad_upload.get_json()["error"]["code"] == "INVALID_ZIP_FORMAT"
