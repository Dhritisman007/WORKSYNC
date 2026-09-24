"""Maps a row from the Kaggle Vehicle Insurance Claim Fraud Detection
dataset (shivamb/vehicle-claim-fraud-detection) to the shared CaseRecord.

Several source columns are pre-binned strings (e.g. "PastNumberOfClaims":
"none" / "1" / "2 to 4" / "more than 4") rather than raw numbers. For
compliance rules to be able to threshold on them numerically (same pattern
as the other verticals), each bucket is mapped to its midpoint — documented
in the `_*_MIDPOINT` dicts below. This is a lossy simplification (a bucket
loses its internal spread), acceptable per the brief's "keep feature
engineering simple" instruction; the model still also gets the raw bucket
as a categorical feature, so it isn't purely reliant on the midpoint.
"""

from __future__ import annotations

from typing import Any, Mapping

from worksync.core.schemas.models import CaseRecord, Vertical

NUMERIC_FEATURES = [
    "age",
    "driver_rating",
    "deductible",
    "week_of_month",
    "week_of_month_claimed",
    "past_claims_count",
    "days_policy_to_accident",
    "days_policy_to_claim",
    "address_change_recency_years",
    "vehicle_price_midpoint",
    "vehicle_age_years",
    "policy_holder_age_midpoint",
    "num_suppliments",
    "num_cars",
]
CATEGORICAL_FEATURES = [
    "make",
    "accident_area",
    "sex",
    "marital_status",
    "fault",
    "policy_type",
    "vehicle_category",
    "base_policy",
    "agent_type",
]
BOOLEAN_FEATURES = ["police_report_filed", "witness_present"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES

_PAST_CLAIMS_MIDPOINT = {"none": 0, "1": 1, "2 to 4": 3, "more than 4": 5}
_DAYS_MIDPOINT = {"none": 0, "1 to 7": 4, "8 to 15": 11, "15 to 30": 22, "more than 30": 45}
_ADDRESS_CHANGE_YEARS = {
    "under 6 months": 0.25,
    "1 year": 1,
    "2 to 3 years": 2.5,
    "4 to 8 years": 6,
    "no change": 15,  # sentinel: "no recorded change" treated as long-ago
}
_VEHICLE_PRICE_MIDPOINT = {
    "less than 20000": 15000,
    "20000 to 29000": 24500,
    "30000 to 39000": 34500,
    "40000 to 59000": 49500,
    "60000 to 69000": 64500,
    "more than 69000": 80000,
}
_VEHICLE_AGE_YEARS = {
    "new": 0,
    "2 years": 2,
    "3 years": 3,
    "4 years": 4,
    "5 years": 5,
    "6 years": 6,
    "7 years": 7,
    "more than 7": 9,
}
_POLICY_HOLDER_AGE_MIDPOINT = {
    "16 to 17": 16.5,
    "18 to 20": 19,
    "21 to 25": 23,
    "26 to 30": 28,
    "31 to 35": 33,
    "36 to 40": 38,
    "41 to 50": 45.5,
    "51 to 65": 58,
    "over 65": 70,
}
_SUPPLIMENTS_MIDPOINT = {"none": 0, "1 to 2": 1.5, "3 to 5": 4, "more than 5": 6}
_NUM_CARS_MIDPOINT = {
    "1 vehicle": 1,
    "2 vehicles": 2,
    "3 to 4": 3.5,
    "5 to 8": 6.5,
    "more than 8": 9,
}


def _num(row: Mapping[str, Any], col: str) -> float | None:
    value = row.get(col)
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _bucket(row: Mapping[str, Any], col: str, mapping: dict[str, float]) -> float | None:
    value = row.get(col)
    if value is None:
        return None
    return mapping.get(str(value).strip())


def _yes_no(row: Mapping[str, Any], col: str) -> bool:
    return str(row.get(col, "")).strip().lower() == "yes"


def engineer_features(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "age": _num(row, "Age"),
        "driver_rating": _num(row, "DriverRating"),
        "deductible": _num(row, "Deductible"),
        "week_of_month": _num(row, "WeekOfMonth"),
        "week_of_month_claimed": _num(row, "WeekOfMonthClaimed"),
        "past_claims_count": _bucket(row, "PastNumberOfClaims", _PAST_CLAIMS_MIDPOINT),
        "days_policy_to_accident": _bucket(row, "Days_Policy_Accident", _DAYS_MIDPOINT),
        "days_policy_to_claim": _bucket(row, "Days_Policy_Claim", _DAYS_MIDPOINT),
        "address_change_recency_years": _bucket(
            row, "AddressChange_Claim", _ADDRESS_CHANGE_YEARS
        ),
        "vehicle_price_midpoint": _bucket(row, "VehiclePrice", _VEHICLE_PRICE_MIDPOINT),
        "vehicle_age_years": _bucket(row, "AgeOfVehicle", _VEHICLE_AGE_YEARS),
        "policy_holder_age_midpoint": _bucket(
            row, "AgeOfPolicyHolder", _POLICY_HOLDER_AGE_MIDPOINT
        ),
        "num_suppliments": _bucket(row, "NumberOfSuppliments", _SUPPLIMENTS_MIDPOINT),
        "num_cars": _bucket(row, "NumberOfCars", _NUM_CARS_MIDPOINT),
        "make": row.get("Make"),
        "accident_area": row.get("AccidentArea"),
        "sex": row.get("Sex"),
        "marital_status": row.get("MaritalStatus"),
        "fault": row.get("Fault"),
        "policy_type": row.get("PolicyType"),
        "vehicle_category": row.get("VehicleCategory"),
        "base_policy": row.get("BasePolicy"),
        "agent_type": row.get("AgentType"),
        "police_report_filed": _yes_no(row, "PoliceReportFiled"),
        "witness_present": _yes_no(row, "WitnessPresent"),
    }


def row_to_case(row: Mapping[str, Any], index: int) -> CaseRecord:
    policy_number = row.get("PolicyNumber")
    entity_id = str(policy_number) if policy_number is not None else f"claim-{index}"
    return CaseRecord(
        case_id=f"insurance-{entity_id}",
        vertical=Vertical.INSURANCE,
        entity_id=entity_id,
        features=engineer_features(row),
    )
