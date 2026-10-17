# Apache Ant 1.7 defect prediction — version-007

The project uses the PROMISE/Jureczko Apache Ant 1.7 dataset, comprising **745 Java classes** (166 marked defective). The included `data/ant-1.7-model-features.csv` is a **derived subset** of the dataset, created from a publicly available mirror: https://github.com/pravaliManchala/SDP/blob/main/ant-1.7.csv. The canonical source is https://zenodo.org/records/268440 (`ant-1.7.csv`).

## Train and evaluate
From `backend/`:

```powershell
py -m pip install -r requirements.txt
py -m pip install matplotlib
py ml/train_model.py
py -m pytest ml/test_trained_model.py tests/test_class_metrics.py -q
py ml/validate_cross_project.py
py app.py
```

You can optionally download the complete canonical CSV with `py ml/download_dataset.py`, which checks its checksum, then run `py ml/train_model.py --dataset ml/data/ant-1.7.csv`. The repository's GitHub Actions workflow also trains and commits the model **to version-007 only**.

## Method and outputs
- Inputs: `loc` and `wmc` (mapped to backend `loc` and `cyclomatic_complexity`).
- Target: `bug > 0` (defective class) vs `bug == 0`.
- Split: reproducible stratified 80/20 train/test, 5-fold training-only parameter selection.
- Models: Random Forest primary, Logistic Regression comparison, trivial majority baseline.
- Reports: accuracy, balanced accuracy, precision, recall, F1, ROC-AUC, average precision, confusion matrix.
- Generated: `models/defect_predictor.joblib`, `model_metadata.json`, `evaluation_results.json`, `evaluation_results.csv`, `confusion_matrix.png`.
- Backend loads `models/defect_predictor.joblib` through `MLDefectPredictionService`; predictions now use class-scoped observations rather than raw file metrics.

## Runtime integration: Java classes rather than source files

- `analyzer/class_metrics.py` uses the Java AST and token boundaries to identify individual named classes/enums (including nested types) from every parsed `.java` file.
- For each class it counts approximate code LOC and calculates a **WMC proxy** by summing cyclomatic complexity of that class's direct declared methods and constructors.
- The Ant 1.7 Random Forest runs **once per extracted class**, not once per file. The file-level attention score is the **maximum class risk**; it is NOT a calibrated file defect probability.
- If a file has no class, its AST parsing fails, or the model is unavailable, it uses the existing heuristic assessment instead.
- The file-level project-health analysis and existing database schema remain intact. Structured class metrics/predictions persist within the risk assessment's informational factor, and appear in API `class_metrics` / `class_predictions` fields and the Project Analysis file-details drawer.

## Validation beyond Apache Ant 1.7

`python ml/validate_cross_project.py` evaluates the frozen Ant-trained model on *other labeled projects* without retraining: `ivy-2.0.csv` (352 classes) and `jedit-4.2.csv` (367 classes), from the same public Jureczko mirror. Results are written to `models/cross_project_validation.json` and `models/cross_project_validation.csv`.

The initial external measurements:
| Dataset | Accuracy | Precision | Recall | F1 | ROC-AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ivy 2.0 | 0.8097 | 0.3412 | 0.7250 | 0.4640 | 0.8365 |
| jEdit 4.2 | 0.6403 | 0.2407 | 0.8125 | 0.3714 | 0.8248 |

## Scientific limitations

**Metric consistency is not fully solved.** The Ant/Jureczko WMC and LOC were computed by other tools. Our AST-derived WMC and LOC are approximations, not proven identical. Verify metric definitions on a common Java source before trusting transferability.

**Cross-project shift remains.** External results use consistently computed published CK metrics, not features extracted by *our* analyzer. Precision is low on those datasets, especially jEdit. These are not guarantees about new unseen Java repositories.

**Research prototype only.** Defect-risk values are approximate rankings, not calibrated probabilities or confirmed defects. A fuller production-quality evaluation would use independently labeled modules processed with the *same metric extractor* used in training.
