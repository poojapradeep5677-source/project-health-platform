import json
import os
from datetime import datetime, timezone
from database import db
from database.models import (
    Project,
    AnalysisRun,
    FileMetric,
    RiskAssessment,
    Recommendation,
)
from database.repository import SettingsRepository
from analyzer.archive_handler import (
    validate_and_extract_zip,
    cleanup_extracted_dir,
    ArchiveValidationError,
)
from analyzer.java_analyzer import analyze_java_file
from scoring.risk_scorer import assess_file_risk
from scoring.health_scorer import compute_project_health_score
from recommendations.prioritizer import generate_refactoring_priorities
from ml.predictor import MLDefectPredictionService


def execute_project_analysis(
    project: Project,
    zip_path: str,
    version_label: str = None,
    archive_filename: str = None,
    base_dir: str = None,
    temp_extract_root: str = None,
) -> AnalysisRun:
    """
    Execute the complete Java static-analysis, risk assessment, health scoring,
    and refactoring prioritization pipeline for a project archive, persisting all
    records atomically in the database.
    """
    upload_limits = SettingsRepository.get_setting_value("upload_limits")
    analysis_thresholds = SettingsRepository.get_setting_value("analysis_thresholds")
    health_weights = SettingsRepository.get_setting_value("health_score_weights")
    priority_weights = SettingsRepository.get_setting_value("priority_weights")
    risk_thresholds = SettingsRepository.get_setting_value("risk_thresholds")
    ml_config = SettingsRepository.get_setting_value("ml_configuration")

    extract_dir = None
    try:
        extract_dir, java_files = validate_and_extract_zip(
            zip_path=zip_path,
            max_upload_size_mb=float(upload_limits.get("max_upload_size_mb", 25.0)),
            max_extracted_files=int(upload_limits.get("max_extracted_files", 2000)),
            max_extracted_size_mb=float(upload_limits.get("max_extracted_size_mb", 100.0)),
            base_temp_dir=temp_extract_root,
        )

        # Initialize ML service to check availability
        ml_service = MLDefectPredictionService(
            base_dir=base_dir or os.getcwd(),
            model_rel_path=ml_config.get("model_path"),
            metadata_rel_path=ml_config.get("metadata_path"),
        )
        prefer_ml = bool(ml_config.get("prefer_ml_when_available", True))

        # 1. Extract metrics for each Java source file
        extracted_metrics = []
        parse_errors = []
        smell_counts_by_type = {}

        for idx, jf in enumerate(java_files):
            fm_dict = analyze_java_file(
                abs_path=jf["abs_path"],
                rel_path=jf["rel_path"],
                file_name=jf["file_name"],
                thresholds=analysis_thresholds,
            )
            fm_dict["_index"] = idx
            extracted_metrics.append(fm_dict)

            if fm_dict["parse_status"] != "SUCCESS":
                parse_errors.append(
                    {
                        "file_path": jf["rel_path"],
                        "file_name": jf["file_name"],
                        "error": fm_dict["parse_error"],
                    }
                )
            else:
                for smell in fm_dict.get("code_smells", []):
                    s_type = smell["type"]
                    if s_type not in smell_counts_by_type:
                        smell_counts_by_type[s_type] = {
                            "type": s_type,
                            "label": smell["label"],
                            "severity": smell["severity"],
                            "count": 0,
                        }
                    smell_counts_by_type[s_type]["count"] += 1

        # 2. Assess file-level risk
        risk_results = []
        for fm_dict in extracted_metrics:
            r_dict = assess_file_risk(
                file_metric=fm_dict,
                risk_thresholds=risk_thresholds,
                ml_service=ml_service,
                prefer_ml=prefer_ml,
            )
            risk_results.append(r_dict)

        # 3. Compute overall Project Health Score
        health_result = compute_project_health_score(
            file_metrics=extracted_metrics,
            risk_assessments=risk_results,
            weights=health_weights,
        )

        # 4. Generate Refactoring Priorities & Recommendations
        priority_results = generate_refactoring_priorities(
            file_metrics=extracted_metrics,
            risk_assessments=risk_results,
            priority_weights=priority_weights,
            thresholds=analysis_thresholds,
        )
        priority_by_index = {p["file_index"]: p for p in priority_results}

        # 5. Calculate run-level aggregates
        total_files = len(extracted_metrics)
        parsed_list = [f for f in extracted_metrics if f["parse_status"] == "SUCCESS"]
        parsed_count = len(parsed_list)
        failed_count = total_files - parsed_count

        total_lines = sum(f["total_lines"] for f in extracted_metrics)
        total_loc = sum(f["loc"] for f in extracted_metrics)
        total_comments = sum(f["comment_lines"] for f in extracted_metrics)
        total_blanks = sum(f["blank_lines"] for f in extracted_metrics)
        avg_comment_ratio = (
            sum(f["comment_ratio"] for f in extracted_metrics) / total_files
            if total_files > 0
            else 0.0
        )

        total_classes = sum(f["class_count"] + f["interface_count"] for f in parsed_list)
        total_methods = sum(f["method_count"] for f in parsed_list)
        total_cc = sum(f["cyclomatic_complexity"] for f in parsed_list)
        avg_cc = total_cc / parsed_count if parsed_count > 0 else 0.0
        max_cc = max((f["cyclomatic_complexity"] for f in parsed_list), default=0)

        mi_vals = [
            f["maintainability_index"]
            for f in parsed_list
            if f["maintainability_index"] is not None
        ]
        avg_mi = sum(mi_vals) / len(mi_vals) if mi_vals else 0.0
        avg_coupling = (
            sum(f["coupling_score"] for f in parsed_list) / parsed_count
            if parsed_count > 0
            else 0.0
        )
        total_smells = sum(f["code_smell_count"] for f in parsed_list)

        high_risk_c = sum(1 for r in risk_results if r["risk_category"] == "HIGH")
        med_risk_c = sum(1 for r in risk_results if r["risk_category"] == "MEDIUM")
        low_risk_c = sum(1 for r in risk_results if r["risk_category"] == "LOW")

        existing_runs_count = AnalysisRun.query.filter_by(project_id=project.id).count()
        next_run_num = existing_runs_count + 1
        # Some files (interfaces, failed parses, unsupported declarations) may
        # require rule-based fallback even when a model is installed.
        active_mode = (
            "ML_MODEL_PREDICTION"
            if any(r["assessment_mode"] == "ML_MODEL_PREDICTION" for r in risk_results)
            else "RULE_BASED_HEURISTIC"
        )

        run = AnalysisRun(
            project_id=project.id,
            run_number=next_run_num,
            version_label=version_label or f"Run #{next_run_num}",
            archive_filename=archive_filename or project.archive_filename,
            status="COMPLETED",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            total_files=total_files,
            parsed_files=parsed_count,
            failed_files=failed_count,
            total_lines=total_lines,
            total_loc=total_loc,
            total_comment_lines=total_comments,
            total_blank_lines=total_blanks,
            avg_comment_ratio=round(avg_comment_ratio, 2),
            total_classes=total_classes,
            total_methods=total_methods,
            total_complexity=total_cc,
            avg_complexity=round(avg_cc, 2),
            max_complexity=max_cc,
            avg_maintainability=round(avg_mi, 2),
            avg_coupling=round(avg_coupling, 2),
            total_code_smells=total_smells,
            high_risk_count=high_risk_c,
            medium_risk_count=med_risk_c,
            low_risk_count=low_risk_c,
            health_score=health_result["health_score"],
            health_grade=health_result["health_grade"],
            health_breakdown_json=json.dumps(health_result),
            scoring_mode=active_mode,
            ml_model_used=ml_service.model_name if active_mode == "ML_MODEL_PREDICTION" else None,
            parse_errors_json=json.dumps(parse_errors),
            code_smell_summary_json=json.dumps(list(smell_counts_by_type.values())),
            summary_notes=(
                f"Analyzed {total_files} Java file(s) ({parsed_count} parsed, {failed_count} syntax failures). "
                f"Overall Health Score: {health_result['health_score']}/100 (Grade {health_result['health_grade']})."
            ),
        )
        db.session.add(run)
        db.session.flush()  # Obtain run.id

        for idx, (fm_dict, r_dict) in enumerate(zip(extracted_metrics, risk_results)):
            p_dict = priority_by_index[idx]
            fm_model = FileMetric(
                analysis_run_id=run.id,
                file_name=fm_dict["file_name"],
                file_path=fm_dict["file_path"],
                package_name=fm_dict["package_name"],
                parse_status=fm_dict["parse_status"],
                parse_error=fm_dict["parse_error"],
                total_lines=fm_dict["total_lines"],
                loc=fm_dict["loc"],
                comment_lines=fm_dict["comment_lines"],
                blank_lines=fm_dict["blank_lines"],
                comment_ratio=fm_dict["comment_ratio"],
                class_count=fm_dict["class_count"],
                interface_count=fm_dict["interface_count"],
                method_count=fm_dict["method_count"],
                field_count=fm_dict["field_count"],
                cyclomatic_complexity=fm_dict["cyclomatic_complexity"],
                avg_method_complexity=fm_dict["avg_method_complexity"],
                max_method_complexity=fm_dict["max_method_complexity"],
                max_nesting_depth=fm_dict["max_nesting_depth"],
                import_count=fm_dict["import_count"],
                fan_out=fm_dict["fan_out"],
                coupling_score=fm_dict["coupling_score"],
                long_method_count=fm_dict["long_method_count"],
                max_method_loc=fm_dict["max_method_loc"],
                max_parameters=fm_dict["max_parameters"],
                maintainability_index=fm_dict["maintainability_index"],
                halstead_volume=fm_dict["halstead_volume"],
                code_smell_count=fm_dict["code_smell_count"],
                code_smells_json=json.dumps(fm_dict["code_smells"]),
                methods_detail_json=json.dumps(fm_dict["methods_detail"]),
            )
            db.session.add(fm_model)
            db.session.flush()  # Obtain fm_model.id

            risk_model = RiskAssessment(
                analysis_run_id=run.id,
                file_metric_id=fm_model.id,
                risk_category=r_dict["risk_category"],
                risk_score=r_dict["risk_score"],
                assessment_mode=r_dict["assessment_mode"],
                ml_defect_probability=r_dict["ml_defect_probability"],
                ml_prediction_label=r_dict["ml_prediction_label"],
                contributing_factors_json=json.dumps(r_dict["contributing_factors"]),
                quality_concerns_json=json.dumps(r_dict["quality_concerns"]),
                explanation=r_dict["explanation"],
            )
            db.session.add(risk_model)

            rec_model = Recommendation(
                analysis_run_id=run.id,
                file_metric_id=fm_model.id,
                priority_rank=p_dict["priority_rank"],
                priority_score=p_dict["priority_score"],
                priority_level=p_dict["priority_level"],
                priority_breakdown_json=json.dumps(p_dict["priority_breakdown"]),
                primary_reasons_json=json.dumps(p_dict["primary_reasons"]),
                suggested_actions_json=json.dumps(p_dict["suggested_actions"]),
                estimated_effort=p_dict["estimated_effort"],
                effort_explanation=p_dict["effort_explanation"],
            )
            db.session.add(rec_model)

        project.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return run

    except Exception:
        db.session.rollback()
        raise
    finally:
        if extract_dir:
            cleanup_extracted_dir(extract_dir)
