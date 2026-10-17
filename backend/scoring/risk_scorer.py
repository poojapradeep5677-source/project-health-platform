from ml.predictor import MLDefectPredictionService, MLModelIntegrationError


def assess_file_risk(
    file_metric: dict,
    risk_thresholds: dict = None,
    ml_service: MLDefectPredictionService = None,
    prefer_ml: bool = True,
) -> dict:
    """
    Evaluate file-level quality & defect risk.
    Uses a compatible trained scikit-learn model when available and enabled;
    otherwise computes an explainable deterministic rule-based heuristic risk score.

    Note: Static source metrics measure structural complexity and maintainability risk;
    they do not prove the presence or absence of runtime defects.
    """
    risk_thresholds = risk_thresholds or {
        "high_risk_threshold": 65.0,
        "medium_risk_threshold": 35.0,
    }
    high_t = float(risk_thresholds.get("high_risk_threshold", 65.0))
    med_t = float(risk_thresholds.get("medium_risk_threshold", 35.0))

    if file_metric.get("parse_status") != "SUCCESS":
        return {
            "risk_category": "HIGH",
            "risk_score": 75.0,
            "assessment_mode": "RULE_BASED_HEURISTIC",
            "ml_defect_probability": None,
            "ml_prediction_label": None,
            "contributing_factors": [
                {
                    "factor": "AST Parse Failure",
                    "raw_value": file_metric.get("parse_error", "Syntax error"),
                    "normalized_impact": 75.0,
                    "weight": 1.0,
                    "direction": "Syntax errors prevent full static AST verification",
                }
            ],
            "quality_concerns": [
                f"Source file failed Java syntax parsing: {file_metric.get('parse_error', 'Unknown syntax error')}"
            ],
            "explanation": (
                "Assigned HIGH attention priority under Rule-Based Heuristic assessment because the file "
                "contains Java syntax errors that prevented AST metric extraction."
            ),
        }

    loc = file_metric.get("loc", 0)
    cc = file_metric.get("cyclomatic_complexity", 1)
    max_m_cc = file_metric.get("max_method_complexity", 1)
    mi = file_metric.get("maintainability_index")
    mi_val = float(mi) if mi is not None else 70.0
    fan_out = file_metric.get("fan_out", 0)
    max_nesting = file_metric.get("max_nesting_depth", 0)
    smells = file_metric.get("code_smells", [])

    # 1. Complexity Risk Factor (0-100)
    cc_factor = min(
        100.0,
        (max(0, max_m_cc - 1) / 18.0) * 60.0 + (max(0, cc - 2) / 35.0) * 40.0,
    )

    # 2. Maintainability Deficit Factor (0-100, higher when MI is lower)
    mi_deficit_factor = max(0.0, min(100.0, (85.0 - mi_val) * 1.45))

    # 3. Code Smell Severity Factor (0-100)
    high_smells = sum(1 for s in smells if s.get("severity") == "HIGH")
    med_smells = sum(1 for s in smells if s.get("severity") == "MEDIUM")
    low_smells = sum(1 for s in smells if s.get("severity") == "LOW")
    smell_factor = min(100.0, high_smells * 30.0 + med_smells * 16.0 + low_smells * 7.0)

    # 4. Coupling & Size Factor (0-100)
    coupling_size_factor = min(
        100.0,
        (fan_out / 16.0) * 50.0 + (loc / 320.0) * 35.0 + (max_nesting / 6.0) * 15.0,
    )

    rule_risk_score = (
        0.30 * cc_factor
        + 0.25 * mi_deficit_factor
        + 0.25 * smell_factor
        + 0.20 * coupling_size_factor
    )
    rule_risk_score = round(max(0.0, min(100.0, rule_risk_score)), 2)

    assessment_mode = "RULE_BASED_HEURISTIC"
    ml_proba = None
    ml_label = None
    final_risk_score = rule_risk_score
    class_metrics = file_metric.get("classes_detail") or []
    class_predictions = []

    if prefer_ml and ml_service is not None and ml_service.is_available:
        try:
            # The Ant 1.7 model was trained on CLASSES, never entire files.
            # One file can contain multiple classes; use the maximum class risk
            # as a transparent conservative file-level attention indicator.
            is_ant_class_model = ml_service.model_name == "Ant17RandomForestDefectRisk"
            if is_ant_class_model and class_metrics:
                for cls in class_metrics:
                    prediction = ml_service.predict_for_file(cls)
                    class_predictions.append({
                        "class_name": cls["class_name"],
                        "loc": cls["loc"],
                        "wmc": cls["wmc"],
                        "prediction_label": prediction["prediction_label"],
                        "defect_probability": prediction["defect_probability"],
                    })
                highest = max(
                    class_predictions,
                    key=lambda result: (
                        result["defect_probability"]
                        if result["defect_probability"] is not None
                        else float(result["prediction_label"])
                    ),
                )
                ml_label = highest["prediction_label"]
                ml_proba = highest["defect_probability"]
                assessment_mode = "ML_MODEL_PREDICTION"
            elif not is_ant_class_model:
                # Keep compatibility with independently trained FILE-level models.
                ml_res = ml_service.predict_for_file(file_metric)
                ml_label = ml_res["prediction_label"]
                ml_proba = ml_res["defect_probability"]
                assessment_mode = "ML_MODEL_PREDICTION"

            if assessment_mode == "ML_MODEL_PREDICTION":
                if ml_proba is not None:
                    final_risk_score = round(ml_proba * 100.0, 2)
                else:
                    final_risk_score = 80.0 if ml_label == 1 else 20.0
        except MLModelIntegrationError:
            # Never present file-level fallbacks as class-level ML predictions.
            class_predictions = []
            assessment_mode = "RULE_BASED_HEURISTIC"

    if final_risk_score >= high_t:
        risk_category = "HIGH"
    elif final_risk_score >= med_t:
        risk_category = "MEDIUM"
    else:
        risk_category = "LOW"

    contributing_factors = [
        {
            "factor": "Cyclomatic Complexity Exposure",
            "raw_value": f"Total CC={cc}, Max Method CC={max_m_cc}",
            "normalized_impact": round(cc_factor, 1),
            "weight": 0.30,
            "direction": "Higher branching complexity increases test paths and cognitive load",
        },
        {
            "factor": "Maintainability Index Deficit",
            "raw_value": f"MI={mi_val:.1f}/100",
            "normalized_impact": round(mi_deficit_factor, 1),
            "weight": 0.25,
            "direction": "Lower Maintainability Index indicates harder-to-maintain code",
        },
        {
            "factor": "Code Smell Severity",
            "raw_value": f"{len(smells)} smell(s) ({high_smells} High, {med_smells} Medium, {low_smells} Low)",
            "normalized_impact": round(smell_factor, 1),
            "weight": 0.25,
            "direction": "More severe static code smells increase technical debt risk",
        },
        {
            "factor": "Coupling & Structural Scope",
            "raw_value": f"Fan-out={fan_out}, LOC={loc}, Max Nesting={max_nesting}",
            "normalized_impact": round(coupling_size_factor, 1),
            "weight": 0.20,
            "direction": "Higher external coupling and deep nesting increase change ripple effects",
        },
    ]

    if class_metrics:
        # Existing database schema stores structured per-class details within an
        # informational factor; callers can read them via RiskAssessment.to_dict.
        contributing_factors.append({
            "factor": "Class-Level Java Metrics and ML Predictions",
            "raw_value": f"{len(class_metrics)} class(es) extracted",
            "normalized_impact": 0.0,
            "weight": 0.0,
            "direction": "Class LOC and WMC proxies evaluated separately; file risk is the highest class score",
            "class_metrics": class_metrics,
            "class_predictions": class_predictions,
        })

    quality_concerns = [s["message"] for s in smells]
    if not quality_concerns:
        if final_risk_score >= med_t:
            quality_concerns.append(
                f"Moderate cumulative complexity (CC={cc}) and structural size ({loc} LOC) warrant periodic review."
            )
        else:
            quality_concerns.append(
                "No threshold-exceeding static code smells detected; metrics are within healthy project bounds."
            )

    if assessment_mode == "ML_MODEL_PREDICTION":
        prob_text = f"{ml_proba * 100:.1f}%" if ml_proba is not None else f"Class {ml_label}"
        class_context = (
            f" Predictions were computed for {len(class_predictions)} individual Java class(es); "
            "the file is assigned the highest class score (not a calibrated file probability)."
            if class_predictions else ""
        )
        explanation = (
            f"Evaluated via connected scikit-learn model ({ml_service.model_name}) with predicted defect risk {prob_text} "
            f"(Risk Category: {risk_category}).{class_context} Static indicators show CC={cc}, MI={mi_val:.1f}, and {len(smells)} code smell(s). "
            "Note: Predictions estimate relative defect proneness based on structural metrics and do not guarantee bug presence."
        )
    else:
        explanation = (
            f"Preliminary Rule-Based Heuristic Assessment (Score: {final_risk_score:.1f}/100, Category: {risk_category}). "
            f"No external ML model is active; score is deterministically derived from complexity (CC={cc}, max method CC={max_m_cc}), "
            f"maintainability index ({mi_val:.1f}/100), coupling fan-out ({fan_out}), and {len(smells)} detected code smell(s). "
            "Static metrics highlight structural technical debt and maintainability concerns rather than proving runtime bugs."
        )

    return {
        "risk_category": risk_category,
        "risk_score": final_risk_score,
        "assessment_mode": assessment_mode,
        "ml_defect_probability": ml_proba,
        "ml_prediction_label": ml_label,
        "contributing_factors": contributing_factors,
        "quality_concerns": quality_concerns,
        "explanation": explanation,
    }
