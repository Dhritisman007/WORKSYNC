"""Trains the insurance claims vertical's fraud risk model on the Kaggle
Vehicle Insurance Claim Fraud Detection dataset
(shivamb/vehicle-claim-fraud-detection). Same shape as the other three
verticals' trainers: LightGBM (primary, isotonic-calibrated) + XGBoost
(comparison baseline only).

Run with: python -m worksync.verticals.insurance.model.train
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
from sklearn.compose import ColumnTransformer
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from worksync.verticals.insurance.adapter import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    engineer_features,
)

SEED = 42
DATA_PATH = Path("worksync/data/raw/insurance/fraud_oracle.csv")
ARTIFACT_DIR = Path("worksync/verticals/insurance/model/artifacts")
REPORT_PATH = Path("worksync/docs/insurance_model_report.md")
MODEL_VERSION = "insurance-lgbm-0.1.0"
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
    if probability <= low - 0.15 or probability >= high + 0.15:
        return "high"
    if probability <= low or probability >= high:
        return "medium"
    return "low"


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"loading {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    y = df["FraudFound_P"].astype(int).to_numpy()
    print(f"{len(df)} rows, positive rate={y.mean():.4f}")

    print("engineering features ...")
    X = build_feature_matrix(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=SEED
    )
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
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=15,
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
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
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
            "confusion_matrix_at_0.5": cm,
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
        "# Insurance claims vertical — model report",
        "",
        "Generated by `worksync/verticals/insurance/model/train.py` against",
        "the Kaggle Vehicle Insurance Claim Fraud Detection dataset",
        "(`shivamb/vehicle-claim-fraud-detection`). Numbers below are from an",
        "actual run, not estimated.",
        "",
        f"- Dataset: {n_rows} claims, positive (fraud) rate {positive_rate:.4f}.",
        f"- Split: stratified {n_train} train / {n_test} test (80/20), seed 42.",
        "- Primary model: LightGBM, isotonic-calibrated (prefit on a held-out",
        "  slice of the training split). XGBoost is a comparison baseline only.",
        "- Several source columns are pre-binned strings (e.g. \"2 to 4\" past",
        "  claims); each bucket is also mapped to a numeric midpoint so",
        "  `rules.yaml` can threshold on them (see `adapter.py`'s `_*_MIDPOINT`",
        "  dicts) — the model sees both the raw bucket (as a category) and",
        "  the midpoint (as a number).",
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
            "|  | pred: legitimate | pred: fraud |",
            "|---|---|---|",
            f"| actual: legitimate | {cm[0][0]} | {cm[0][1]} |",
            f"| actual: fraud | {cm[1][0]} | {cm[1][1]} |",
            "",
        ]

    lines += [
        "## Notes",
        "",
        "- 0.5 is a reporting threshold for this table only; the Manager",
        "  Agent's real bands come from",
        "  `verticals/insurance/manager_config.yaml`.",
        "- `PolicyNumber` and `RepNumber` are identifiers, not features — not",
        "  used in the model or the rules.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
