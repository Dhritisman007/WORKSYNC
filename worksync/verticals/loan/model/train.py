"""Trains the loan vertical's risk model.

LightGBM is the primary model (calibrated with isotonic regression via
cross-validated prefit calibration); XGBoost is trained purely as a
comparison baseline (its numbers go in the report, it is never used for
scoring). Both share the same engineered feature matrix from
`verticals/loan/adapter.py`, and both get a stratified split plus
`scale_pos_weight` for the ~8% positive-class imbalance in this dataset.

Run with: python -m worksync.verticals.loan.model.train
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from worksync.verticals.loan.adapter import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    engineer_features,
)

SEED = 42
DATA_PATH = Path("worksync/data/raw/loan/application_train.csv")
ARTIFACT_DIR = Path("worksync/verticals/loan/model/artifacts")
REPORT_PATH = Path("worksync/docs/loan_model_report.md")
MODEL_VERSION = "loan-lgbm-0.1.0"

# Decision bands: risk probabilities below/above these are "clearly good" /
# "clearly bad" for reporting purposes only — the Manager Agent's own
# grey-band config (manager_config.yaml) is the source of truth at runtime.
REPORT_THRESHOLD = 0.5


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    engineered = df.apply(lambda row: engineer_features(row), axis=1, result_type="expand")
    for col in BOOLEAN_FEATURES:
        engineered[col] = engineered[col].astype(float)
    return engineered[NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES]


def make_preprocessor() -> ColumnTransformer:
    numeric_pipe = Pipeline([("impute", SimpleImputer(strategy="median"))])
    categorical_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipe, NUMERIC_FEATURES + BOOLEAN_FEATURES),
            ("categorical", categorical_pipe, CATEGORICAL_FEATURES),
        ]
    )


def ks_statistic(y_true: np.ndarray, y_score: np.ndarray) -> float:
    fpr, tpr, _ = roc_curve(y_true, y_score)
    return float(np.max(np.abs(tpr - fpr)))


def confidence_band(probability: float, low: float = 0.35, high: float = 0.65) -> str:
    """Confidence is about how far from the grey band the score sits, not
    about the score itself — used by both training-time reporting and the
    RiskModel at inference time."""
    if probability <= low - 0.15 or probability >= high + 0.15:
        return "high"
    if probability <= low or probability >= high:
        return "medium"
    return "low"


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"loading {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    y = df["TARGET"].astype(int).to_numpy()
    print(f"{len(df)} rows, positive rate={y.mean():.4f}")

    print("engineering features ...")
    X = build_feature_matrix(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=SEED
    )
    # Held-out slice of the training split for prefit isotonic calibration,
    # so calibration never sees the final test split.
    X_fit, X_cal, y_fit, y_cal = train_test_split(
        X_train, y_train, test_size=0.2, stratify=y_train, random_state=SEED
    )

    scale_pos_weight = (y_fit == 0).sum() / max((y_fit == 1).sum(), 1)
    print(f"scale_pos_weight={scale_pos_weight:.3f}")

    preprocessor = make_preprocessor()
    Xt_fit = preprocessor.fit_transform(X_fit)
    Xt_cal = preprocessor.transform(X_cal)
    Xt_test = preprocessor.transform(X_test)

    print("training LightGBM (primary) ...")
    lgbm = lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        scale_pos_weight=scale_pos_weight,
        random_state=SEED,
        verbose=-1,
    )
    lgbm.fit(Xt_fit, y_fit)

    print("calibrating LightGBM (prefit isotonic on held-out split) ...")
    calibrated_lgbm = CalibratedClassifierCV(FrozenEstimator(lgbm), method="isotonic")
    calibrated_lgbm.fit(Xt_cal, y_cal)

    lgbm_raw_proba = lgbm.predict_proba(Xt_test)[:, 1]
    lgbm_cal_proba = calibrated_lgbm.predict_proba(Xt_test)[:, 1]

    print("training XGBoost (comparison baseline only) ...")
    xgboost_model = xgb.XGBClassifier(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=5,
        scale_pos_weight=scale_pos_weight,
        eval_metric="auc",
        random_state=SEED,
    )
    xgboost_model.fit(Xt_fit, y_fit)
    xgb_proba = xgboost_model.predict_proba(Xt_test)[:, 1]

    def summarize(name: str, proba: np.ndarray) -> dict:
        preds = (proba >= REPORT_THRESHOLD).astype(int)
        cm = confusion_matrix(y_test, preds).tolist()
        return {
            "model": name,
            "auc": round(float(roc_auc_score(y_test, proba)), 4),
            "ks": round(ks_statistic(y_test, proba), 4),
            "brier": round(float(brier_score_loss(y_test, proba)), 4),
            "confusion_matrix_at_0.5": cm,  # [[tn, fp], [fn, tp]]
        }

    results = [
        summarize("lightgbm_raw", lgbm_raw_proba),
        summarize("lightgbm_calibrated (primary)", lgbm_cal_proba),
        summarize("xgboost_baseline", xgb_proba),
    ]
    for r in results:
        print(r)

    print("saving artifacts ...")
    joblib.dump(preprocessor, ARTIFACT_DIR / "preprocessor.joblib")
    joblib.dump(lgbm, ARTIFACT_DIR / "lgbm_base.joblib")
    joblib.dump(calibrated_lgbm, ARTIFACT_DIR / "lgbm_calibrated.joblib")
    joblib.dump(xgboost_model, ARTIFACT_DIR / "xgboost_baseline.joblib")
    (ARTIFACT_DIR / "metadata.json").write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "seed": SEED,
                "n_train_rows": int(len(X_train)),
                "n_test_rows": int(len(X_test)),
                "positive_rate": round(float(y.mean()), 4),
                "results": results,
            },
            indent=2,
        )
    )

    write_report(results, len(df), float(y.mean()), len(X_train), len(X_test))
    print(f"wrote {REPORT_PATH}")


def write_report(results, n_rows, positive_rate, n_train, n_test) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Loan vertical — model report",
        "",
        "Generated by `worksync/verticals/loan/model/train.py`. Numbers below",
        "are from an actual run against `data/raw/loan/application_train.csv`",
        "— not estimated.",
        "",
        f"- Dataset: Home Credit Default Risk, `application_train.csv`, {n_rows} rows,",
        f"  positive (default) rate {positive_rate:.4f}.",
        f"- Split: stratified {n_train} train / {n_test} test (80/20), seed 42.",
        "- Primary model: LightGBM, isotonic-calibrated (prefit on a held-out",
        "  slice of the training split). XGBoost is a comparison baseline only",
        "  — it is not used for scoring.",
        "",
        "## Metrics (test split)",
        "",
        "| Model | AUC | KS | Brier |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['model']} | {r['auc']} | {r['ks']} | {r['brier']} |")

    lines += ["", "## Confusion matrix at 0.5 threshold", ""]
    for r in results:
        cm = r["confusion_matrix_at_0.5"]
        lines += [
            f"**{r['model']}**",
            "",
            "|  | pred: repay | pred: default |",
            "|---|---|---|",
            f"| actual: repay | {cm[0][0]} | {cm[0][1]} |",
            f"| actual: default | {cm[1][0]} | {cm[1][1]} |",
            "",
        ]

    lines += [
        "## Notes",
        "",
        "- 0.5 is a reporting threshold for this table only — the Manager",
        "  Agent's actual decision bands come from",
        "  `verticals/loan/manager_config.yaml`'s grey-band thresholds, which",
        "  are set lower (see that file) because approve/reject in this",
        "  domain should be conservative and most mid-range cases should",
        "  escalate to a human rather than being auto-decided at a coin-flip",
        "  threshold.",
        "- Calibration was fit on a held-out slice of the training split",
        "  (not the test split), so the test metrics above are calibration-",
        "  agnostic verification, not circular.",
        "- No interaction features, no joins against bureau.csv /",
        "  previous_application.csv / etc. — kept to the brief's \"keep",
        "  feature engineering simple\" instruction. A natural extension.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
