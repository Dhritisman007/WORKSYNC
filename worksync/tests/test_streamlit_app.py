"""Tests for the demo app's file-upload path (app/streamlit_app.py).

These exercise the parsing/id-filling helpers and the full pipeline against
an uploaded file directly — not through a browser — since the point is that
an uploaded raw CSV/JSON reaches the exact same orchestrator every sample-
dataset case does. Skipped automatically if a vertical's model artifacts
aren't present (same convention as the other vertical test files).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest

from worksync.app.streamlit_app import (
    VERTICALS,
    _ensure_id,
    detect_vertical,
    get_orchestrator,
    parse_uploaded_file,
)

SAMPLES_DIR = Path("worksync/samples")


class _FakeUpload(io.BytesIO):
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def _kyc_artifacts_present() -> bool:
    return Path("worksync/verticals/kyc_aml/model/artifacts/lgbm_calibrated.joblib").exists()


def _loan_artifacts_present() -> bool:
    return Path("worksync/verticals/loan/model/artifacts/lgbm_calibrated.joblib").exists()


def test_parse_uploaded_csv():
    csv_bytes = b"a,b\n1,2\n3,4\n"
    df = parse_uploaded_file(_FakeUpload(csv_bytes, "case.csv"))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_parse_uploaded_json_single_record():
    payload = json.dumps({"a": 1, "b": 2}).encode()
    df = parse_uploaded_file(_FakeUpload(payload, "case.json"))
    assert len(df) == 1
    assert df.iloc[0]["a"] == 1


def test_parse_uploaded_json_list_of_records():
    payload = json.dumps([{"a": 1}, {"a": 2}]).encode()
    df = parse_uploaded_file(_FakeUpload(payload, "cases.json"))
    assert len(df) == 2


def test_ensure_id_fills_missing_id_for_series():
    row = pd.Series({"amount": 100})
    filled = _ensure_id(row, "SK_ID_CURR", 7)
    assert filled["SK_ID_CURR"] == "upload-7"


def test_ensure_id_fills_missing_id_for_dict():
    row = {"amount": 100}
    filled = _ensure_id(row, "applicant_id", 3)
    assert filled["applicant_id"] == "upload-3"


def test_ensure_id_leaves_existing_id_alone():
    row = pd.Series({"SK_ID_CURR": 555})
    filled = _ensure_id(row, "SK_ID_CURR", 7)
    assert filled["SK_ID_CURR"] == 555


def test_ensure_id_noop_when_no_id_col():
    row = {"amount": 100}
    assert _ensure_id(row, None, 0) is row


@pytest.mark.skipif(not _kyc_artifacts_present(), reason="kyc_aml model artifacts not present")
def test_uploaded_kyc_json_with_sanctions_match_is_rejected():
    payload = json.dumps(
        {
            "age_years": 29,
            "country_of_residence": "IN",
            "id_type": "passport",
            "document_quality_score": 0.91,
            "address_match_score": 0.95,
            "selfie_liveness_score": 0.9,
            "device_risk_score": 0.05,
            "application_velocity_24h": 1,
            "pep_match": False,
            "sanctions_match": True,
            "adverse_media_hit": False,
        }
    ).encode()
    df = parse_uploaded_file(_FakeUpload(payload, "case.json"))

    spec = VERTICALS["kyc_aml"]()
    orchestrator, _ = get_orchestrator("kyc_aml")
    row = _ensure_id(df.iloc[0], spec.id_col, 0)
    case = spec.row_to_case(row, 0)

    assert case.entity_id == "upload-0"
    result = orchestrator.run_case_with_detail(case)
    assert result.decision.outcome.value == "reject"
    assert "KYC-SANCTIONS-001" in result.decision.hard_flags


@pytest.mark.skipif(not _loan_artifacts_present(), reason="loan model artifacts not present")
def test_uploaded_loan_csv_with_multiple_rows_runs_each_through_the_pipeline():
    csv_bytes = (
        b"NAME_CONTRACT_TYPE,CODE_GENDER,FLAG_OWN_CAR,FLAG_OWN_REALTY,AMT_INCOME_TOTAL,"
        b"AMT_CREDIT,AMT_ANNUITY,DAYS_BIRTH,DAYS_EMPLOYED,EXT_SOURCE_1,EXT_SOURCE_2,EXT_SOURCE_3\n"
        b"Cash loans,F,N,Y,120000,300000,15000,-9000,-1200,0.6,0.7,0.65\n"
        b"Cash loans,M,Y,N,45000,900000,60000,-8000,365243,0.1,0.15,0.2\n"
    )
    df = parse_uploaded_file(_FakeUpload(csv_bytes, "cases.csv"))
    assert len(df) == 2

    spec = VERTICALS["loan"]()
    orchestrator, _ = get_orchestrator("loan")
    outcomes = []
    for i in range(len(df)):
        row = _ensure_id(df.iloc[i], spec.id_col, i)
        case = spec.row_to_case(row, i)
        assert case.case_id == f"loan-upload-{i}"
        result = orchestrator.run_case_with_detail(case)
        outcomes.append(result.decision.outcome.value)

    assert all(o in {"approve", "reject", "escalate"} for o in outcomes)


def test_detect_vertical_recognizes_loan_sample():
    df = pd.read_csv(SAMPLES_DIR / "loan_sample.csv")
    matches = detect_vertical(list(df.columns))
    assert matches[0].key == "loan"
    assert matches[0].coverage > 0.9
    assert all(m.coverage == 0 for m in matches[1:])


def test_detect_vertical_recognizes_bnpl_sample():
    df = pd.read_csv(SAMPLES_DIR / "bnpl_sample.csv")
    matches = detect_vertical(list(df.columns))
    assert matches[0].key == "bnpl"
    assert matches[0].coverage == 1.0


def test_detect_vertical_recognizes_insurance_sample():
    df = pd.read_csv(SAMPLES_DIR / "insurance_sample.csv")
    matches = detect_vertical(list(df.columns))
    assert matches[0].key == "insurance"
    assert matches[0].coverage == 1.0


def test_detect_vertical_recognizes_kyc_aml_sample():
    with open(SAMPLES_DIR / "kyc_aml_sample.json") as f:
        records = json.load(f)
    matches = detect_vertical(list(records[0].keys()))
    assert matches[0].key == "kyc_aml"
    assert matches[0].coverage > 0.9


def test_detect_vertical_returns_zero_coverage_for_unrelated_columns():
    matches = detect_vertical(["foo", "bar", "baz"])
    assert all(m.coverage == 0 for m in matches)
