import json
from datetime import datetime, timezone
from database import db


def _class_observations(risk):
    """Read class records from persisted informational factors (no schema migration)."""
    factors = json.loads(risk.contributing_factors_json or "[]") if risk else []
    for factor in factors:
        if factor.get("factor") == "Class-Level Java Metrics and ML Predictions":
            return (factor.get("class_metrics", []), factor.get("class_predictions", []))
    return ([], [])


def utcnow():
    return datetime.now(timezone.utc)


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(64), nullable=False, default="Java")
    archive_filename = db.Column(db.String(255), nullable=False)
    archive_path = db.Column(db.String(512), nullable=True)
    archive_size_bytes = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    analysis_runs = db.relationship(
        "AnalysisRun",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="desc(AnalysisRun.created_at)",
    )

    def to_dict(self, include_latest_run=True):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "language": self.language,
            "archive_filename": self.archive_filename,
            "archive_size_bytes": self.archive_size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "run_count": len(self.analysis_runs) if self.analysis_runs else 0,
        }
        if include_latest_run:
            latest = self.analysis_runs[0] if self.analysis_runs else None
            data["latest_run"] = latest.to_summary_dict() if latest else None
        return data


class AnalysisRun(db.Model):
    __tablename__ = "analysis_runs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_number = db.Column(db.Integer, nullable=False, default=1)
    version_label = db.Column(db.String(128), nullable=True)
    archive_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="COMPLETED")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Aggregate Counts & Metrics
    total_files = db.Column(db.Integer, nullable=False, default=0)
    parsed_files = db.Column(db.Integer, nullable=False, default=0)
    failed_files = db.Column(db.Integer, nullable=False, default=0)
    total_lines = db.Column(db.Integer, nullable=False, default=0)
    total_loc = db.Column(db.Integer, nullable=False, default=0)
    total_comment_lines = db.Column(db.Integer, nullable=False, default=0)
    total_blank_lines = db.Column(db.Integer, nullable=False, default=0)
    avg_comment_ratio = db.Column(db.Float, nullable=False, default=0.0)
    total_classes = db.Column(db.Integer, nullable=False, default=0)
    total_methods = db.Column(db.Integer, nullable=False, default=0)
    total_complexity = db.Column(db.Integer, nullable=False, default=0)
    avg_complexity = db.Column(db.Float, nullable=False, default=0.0)
    max_complexity = db.Column(db.Integer, nullable=False, default=0)
    avg_maintainability = db.Column(db.Float, nullable=False, default=0.0)
    avg_coupling = db.Column(db.Float, nullable=False, default=0.0)
    total_code_smells = db.Column(db.Integer, nullable=False, default=0)

    # Risk distribution
    high_risk_count = db.Column(db.Integer, nullable=False, default=0)
    medium_risk_count = db.Column(db.Integer, nullable=False, default=0)
    low_risk_count = db.Column(db.Integer, nullable=False, default=0)

    # Health Score
    health_score = db.Column(db.Float, nullable=False, default=0.0)
    health_grade = db.Column(db.String(8), nullable=False, default="N/A")
    health_breakdown_json = db.Column(db.Text, nullable=False, default="{}")
    scoring_mode = db.Column(db.String(64), nullable=False, default="RULE_BASED_HEURISTIC")
    ml_model_used = db.Column(db.String(128), nullable=True)
    parse_errors_json = db.Column(db.Text, nullable=False, default="[]")
    code_smell_summary_json = db.Column(db.Text, nullable=False, default="{}")
    summary_notes = db.Column(db.Text, nullable=True)

    project = db.relationship("Project", back_populates="analysis_runs")
    file_metrics = db.relationship(
        "FileMetric", back_populates="analysis_run", cascade="all, delete-orphan"
    )
    risk_assessments = db.relationship(
        "RiskAssessment", back_populates="analysis_run", cascade="all, delete-orphan"
    )
    recommendations = db.relationship(
        "Recommendation",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        order_by="Recommendation.priority_rank",
    )

    def to_summary_dict(self):
        # Compute 4-tier breakdown (Critical >= 75, High 65-74.99, Medium 35-64.99, Low < 35) from actual risk assessments
        risks = self.risk_assessments or []
        if risks:
            crit_c = sum(1 for r in risks if r.risk_score >= 75.0 or (r.risk_category == "HIGH" and r.risk_score >= 72.0))
            high_only_c = max(0, self.high_risk_count - crit_c)
        else:
            crit_c = 0
            high_only_c = self.high_risk_count

        total_f = max(self.total_files, 1)
        success_rate = round((self.parsed_files / self.total_files) * 100.0, 1) if self.total_files > 0 else 0.0

        return {
            "id": self.id,
            "project_id": self.project_id,
            "project_name": self.project.name if self.project else None,
            "language": self.project.language if self.project else "Java",
            "run_number": self.run_number,
            "version_label": self.version_label or f"Run #{self.run_number}",
            "archive_filename": self.archive_filename,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_files": self.total_files,
            "parsed_files": self.parsed_files,
            "failed_files": self.failed_files,
            "analysis_success_rate": success_rate,
            "total_lines": self.total_lines,
            "total_loc": self.total_loc,
            "total_comment_lines": self.total_comment_lines,
            "total_blank_lines": self.total_blank_lines,
            "avg_comment_ratio": round(self.avg_comment_ratio, 2),
            "total_classes": self.total_classes,
            "total_methods": self.total_methods,
            "total_complexity": self.total_complexity,
            "avg_complexity": round(self.avg_complexity, 2),
            "max_complexity": self.max_complexity,
            "avg_maintainability": round(self.avg_maintainability, 2) if self.parsed_files > 0 else None,
            "avg_coupling": round(self.avg_coupling, 2),
            "total_code_smells": self.total_code_smells,
            "critical_risk_count": crit_c,
            "high_risk_count": self.high_risk_count,
            "medium_risk_count": self.medium_risk_count,
            "low_risk_count": self.low_risk_count,
            "risk_tiers": {
                "critical": {
                    "count": crit_c,
                    "percentage": round((crit_c / total_f) * 100.0, 1) if self.total_files > 0 else 0.0,
                },
                "high": {
                    "count": high_only_c,
                    "percentage": round((high_only_c / total_f) * 100.0, 1) if self.total_files > 0 else 0.0,
                },
                "medium": {
                    "count": self.medium_risk_count,
                    "percentage": round((self.medium_risk_count / total_f) * 100.0, 1) if self.total_files > 0 else 0.0,
                },
                "low": {
                    "count": self.low_risk_count,
                    "percentage": round((self.low_risk_count / total_f) * 100.0, 1) if self.total_files > 0 else 0.0,
                },
            },
            "health_score": round(self.health_score, 1),
            "health_grade": self.health_grade,
            "health_breakdown": self._normalized_health_breakdown(),
            "scoring_mode": self.scoring_mode,
            "ml_model_used": self.ml_model_used,
            "parse_errors": json.loads(self.parse_errors_json or "[]"),
            "code_smell_summary": json.loads(self.code_smell_summary_json or "{}"),
            "summary_notes": self.summary_notes,
        }

    def _normalized_health_breakdown(self):
        hb = json.loads(self.health_breakdown_json or "{}")
        comps = hb.get("components")
        if isinstance(comps, dict):
            for _, c in comps.items():
                if isinstance(c, dict):
                    c.setdefault("normalized_score", c.get("subscore", 0.0) or 0.0)
                    c.setdefault("weight", c.get("effective_weight", c.get("configured_weight", 0.0)) or 0.0)
                    c.setdefault("raw_value", c.get("raw_indicator", ""))
                    c.setdefault("weighted_points", c.get("weighted_contribution", 0.0) or 0.0)
        return hb


class FileMetric(db.Model):
    __tablename__ = "file_metrics"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    analysis_run_id = db.Column(
        db.Integer, db.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    package_name = db.Column(db.String(255), nullable=True)
    parse_status = db.Column(db.String(32), nullable=False, default="SUCCESS")
    parse_error = db.Column(db.Text, nullable=True)

    # Size & Documentation Metrics
    total_lines = db.Column(db.Integer, nullable=False, default=0)
    loc = db.Column(db.Integer, nullable=False, default=0)
    comment_lines = db.Column(db.Integer, nullable=False, default=0)
    blank_lines = db.Column(db.Integer, nullable=False, default=0)
    comment_ratio = db.Column(db.Float, nullable=False, default=0.0)

    # Structural Metrics
    class_count = db.Column(db.Integer, nullable=False, default=0)
    interface_count = db.Column(db.Integer, nullable=False, default=0)
    method_count = db.Column(db.Integer, nullable=False, default=0)
    field_count = db.Column(db.Integer, nullable=False, default=0)

    # Complexity & Nesting
    cyclomatic_complexity = db.Column(db.Integer, nullable=False, default=0)
    avg_method_complexity = db.Column(db.Float, nullable=False, default=0.0)
    max_method_complexity = db.Column(db.Integer, nullable=False, default=0)
    max_nesting_depth = db.Column(db.Integer, nullable=False, default=0)

    # Coupling & Method Signature Metrics
    import_count = db.Column(db.Integer, nullable=False, default=0)
    fan_out = db.Column(db.Integer, nullable=False, default=0)
    coupling_score = db.Column(db.Float, nullable=False, default=0.0)
    long_method_count = db.Column(db.Integer, nullable=False, default=0)
    max_method_loc = db.Column(db.Integer, nullable=False, default=0)
    max_parameters = db.Column(db.Integer, nullable=False, default=0)

    # Maintainability & Halstead
    maintainability_index = db.Column(db.Float, nullable=True)
    halstead_volume = db.Column(db.Float, nullable=True)

    # Code Smells & Method Details
    code_smell_count = db.Column(db.Integer, nullable=False, default=0)
    code_smells_json = db.Column(db.Text, nullable=False, default="[]")
    methods_detail_json = db.Column(db.Text, nullable=False, default="[]")

    analysis_run = db.relationship("AnalysisRun", back_populates="file_metrics")
    risk_assessment = db.relationship(
        "RiskAssessment", back_populates="file_metric", uselist=False, cascade="all, delete-orphan"
    )
    recommendation = db.relationship(
        "Recommendation", back_populates="file_metric", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self, include_details=True):
        risk = self.risk_assessment
        rec = self.recommendation
        class_metrics, class_predictions = _class_observations(risk)
        data = {
            "id": self.id,
            "analysis_run_id": self.analysis_run_id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "package_name": self.package_name or "(default package)",
            "parse_status": self.parse_status,
            "parse_error": self.parse_error,
            "total_lines": self.total_lines,
            "loc": self.loc,
            "comment_lines": self.comment_lines,
            "blank_lines": self.blank_lines,
            "comment_ratio": round(self.comment_ratio, 2),
            "class_count": self.class_count,
            "interface_count": self.interface_count,
            "method_count": self.method_count,
            "field_count": self.field_count,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "avg_method_complexity": round(self.avg_method_complexity, 2),
            "max_method_complexity": self.max_method_complexity,
            "max_nesting_depth": self.max_nesting_depth,
            "import_count": self.import_count,
            "fan_out": self.fan_out,
            "coupling_score": round(self.coupling_score, 2),
            "long_method_count": self.long_method_count,
            "max_method_loc": self.max_method_loc,
            "max_parameters": self.max_parameters,
            "maintainability_index": (
                round(self.maintainability_index, 2)
                if self.maintainability_index is not None
                else None
            ),
            "halstead_volume": (
                round(self.halstead_volume, 2) if self.halstead_volume is not None else None
            ),
            "code_smell_count": self.code_smell_count,
            "code_smells": json.loads(self.code_smells_json or "[]"),
            "class_metrics": class_metrics if include_details else [],
            "class_predictions": class_predictions,
            "risk_category": risk.risk_category if risk else "UNKNOWN",
            "risk_score": round(risk.risk_score, 2) if risk else 0.0,
            "assessment_mode": risk.assessment_mode if risk else "RULE_BASED_HEURISTIC",
            "ml_defect_probability": (
                round(risk.ml_defect_probability, 4)
                if (risk and risk.ml_defect_probability is not None)
                else None
            ),
            "priority_rank": rec.priority_rank if rec else None,
            "priority_score": round(rec.priority_score, 2) if rec else None,
            "priority_level": rec.priority_level if rec else None,
            "supported_metrics": {
                "loc": True,
                "cyclomatic_complexity": self.parse_status == "SUCCESS",
                "method_count": self.parse_status == "SUCCESS",
                "comment_ratio": True,
                "coupling_indicators": self.parse_status == "SUCCESS",
                "maintainability_index": self.maintainability_index is not None,
                "code_smells": self.parse_status == "SUCCESS",
                "dynamic_test_coverage": False,
                "runtime_memory_profile": False,
            },
        }
        if include_details:
            raw_methods = json.loads(self.methods_detail_json or "[]")
            for m in raw_methods:
                if isinstance(m, dict):
                    m.setdefault("estimated_loc", m.get("loc", 0))
                    m.setdefault("cyclomatic_complexity", m.get("complexity", 1))
                    m.setdefault("max_nesting_depth", m.get("max_nesting", 0))
            data["methods_detail"] = raw_methods
        return data


class RiskAssessment(db.Model):
    __tablename__ = "risk_assessments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    analysis_run_id = db.Column(
        db.Integer, db.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_metric_id = db.Column(
        db.Integer, db.ForeignKey("file_metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_category = db.Column(db.String(32), nullable=False, default="LOW")
    risk_score = db.Column(db.Float, nullable=False, default=0.0)
    assessment_mode = db.Column(db.String(64), nullable=False, default="RULE_BASED_HEURISTIC")
    ml_defect_probability = db.Column(db.Float, nullable=True)
    ml_prediction_label = db.Column(db.Integer, nullable=True)
    contributing_factors_json = db.Column(db.Text, nullable=False, default="[]")
    quality_concerns_json = db.Column(db.Text, nullable=False, default="[]")
    explanation = db.Column(db.Text, nullable=True)

    analysis_run = db.relationship("AnalysisRun", back_populates="risk_assessments")
    file_metric = db.relationship("FileMetric", back_populates="risk_assessment")

    def to_dict(self):
        fm = self.file_metric
        rec = fm.recommendation if fm else None
        class_metrics, class_predictions = _class_observations(self)
        return {
            "class_metrics": class_metrics,
            "class_predictions": class_predictions,
            "id": self.id,
            "analysis_run_id": self.analysis_run_id,
            "file_metric_id": self.file_metric_id,
            "file_name": fm.file_name if fm else "",
            "file_path": fm.file_path if fm else "",
            "package_name": fm.package_name if fm else "",
            "risk_category": self.risk_category,
            "risk_score": round(self.risk_score, 2),
            "assessment_mode": self.assessment_mode,
            "ml_defect_probability": (
                round(self.ml_defect_probability, 4)
                if self.ml_defect_probability is not None
                else None
            ),
            "ml_prediction_label": self.ml_prediction_label,
            "contributing_factors": json.loads(self.contributing_factors_json or "[]"),
            "quality_concerns": json.loads(self.quality_concerns_json or "[]"),
            "explanation": self.explanation or "",
            "suggested_actions": json.loads(rec.suggested_actions_json or "[]") if rec else [],
            "metrics_snapshot": {
                "loc": fm.loc if fm else 0,
                "cyclomatic_complexity": fm.cyclomatic_complexity if fm else 0,
                "max_method_complexity": fm.max_method_complexity if fm else 0,
                "maintainability_index": (
                    round(fm.maintainability_index, 2)
                    if (fm and fm.maintainability_index is not None)
                    else None
                ),
                "code_smell_count": fm.code_smell_count if fm else 0,
                "fan_out": fm.fan_out if fm else 0,
                "comment_ratio": round(fm.comment_ratio, 2) if fm else 0.0,
            },
        }


class Recommendation(db.Model):
    __tablename__ = "recommendations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    analysis_run_id = db.Column(
        db.Integer, db.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_metric_id = db.Column(
        db.Integer, db.ForeignKey("file_metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority_rank = db.Column(db.Integer, nullable=False, default=1)
    priority_score = db.Column(db.Float, nullable=False, default=0.0)
    priority_level = db.Column(db.String(32), nullable=False, default="LOW")
    priority_breakdown_json = db.Column(db.Text, nullable=False, default="{}")
    primary_reasons_json = db.Column(db.Text, nullable=False, default="[]")
    suggested_actions_json = db.Column(db.Text, nullable=False, default="[]")
    estimated_effort = db.Column(db.String(64), nullable=True)
    effort_explanation = db.Column(db.Text, nullable=True)

    analysis_run = db.relationship("AnalysisRun", back_populates="recommendations")
    file_metric = db.relationship("FileMetric", back_populates="recommendation")

    def to_dict(self):
        fm = self.file_metric
        risk = fm.risk_assessment if fm else None
        return {
            "id": self.id,
            "analysis_run_id": self.analysis_run_id,
            "file_metric_id": self.file_metric_id,
            "file_name": fm.file_name if fm else "",
            "file_path": fm.file_path if fm else "",
            "package_name": fm.package_name if fm else "",
            "priority_rank": self.priority_rank,
            "priority_score": round(self.priority_score, 2),
            "priority_level": self.priority_level,
            "priority_breakdown": json.loads(self.priority_breakdown_json or "{}"),
            "primary_reasons": json.loads(self.primary_reasons_json or "[]"),
            "suggested_actions": json.loads(self.suggested_actions_json or "[]"),
            "estimated_effort": self.estimated_effort,
            "effort_explanation": self.effort_explanation,
            "risk_category": risk.risk_category if risk else "LOW",
            "risk_score": round(risk.risk_score, 2) if risk else 0.0,
            "assessment_mode": risk.assessment_mode if risk else "RULE_BASED_HEURISTIC",
            "supporting_metrics": {
                "loc": fm.loc if fm else 0,
                "method_count": fm.method_count if fm else 0,
                "cyclomatic_complexity": fm.cyclomatic_complexity if fm else 0,
                "max_method_complexity": fm.max_method_complexity if fm else 0,
                "maintainability_index": (
                    round(fm.maintainability_index, 2)
                    if (fm and fm.maintainability_index is not None)
                    else None
                ),
                "code_smell_count": fm.code_smell_count if fm else 0,
                "fan_out": fm.fan_out if fm else 0,
                "comment_ratio": round(fm.comment_ratio, 2) if fm else 0.0,
            },
        }


class ApplicationSetting(db.Model):
    __tablename__ = "application_settings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    value_json = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(64), nullable=False, default="general")
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            "key": self.key,
            "value": json.loads(self.value_json),
            "category": self.category,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
