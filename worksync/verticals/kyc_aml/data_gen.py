"""Generates synthetic KYC/AML onboarding data: applicant identity records
plus PEP (politically exposed person) and sanctions watchlists.

Everything here is fabricated — no real names, no real PEP/sanctions data,
no real identity documents. This exists because the brief calls for
"seeded synthetic identity + PEP/sanctions data" for this vertical (unlike
loan, there's no real public dataset to use). Determinism matters: the same
seed must always produce the same data, so results are reproducible and the
audit trail's `replay()` stays meaningful.

Run with: python -m worksync.verticals.kyc_aml.data_gen
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 4242
N_APPLICANTS = 5000
N_PEP = 150
N_SANCTIONS = 80

OUT_DIR = Path("worksync/data/raw/kyc_aml")

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
    "Ishaan", "Rohan", "Ananya", "Diya", "Saanvi", "Aadhya", "Kiara", "Myra",
    "Priya", "Neha", "Ritu", "Sneha", "Liam", "Noah", "Oliver", "Elijah",
    "Emma", "Ava", "Sophia", "Isabella", "Carlos", "Miguel", "Ahmed", "Fatima",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Reddy", "Patel", "Singh",
    "Khan", "Mehta", "Joshi", "Rao", "Das", "Chatterjee", "Bose", "Kapoor",
    "Smith", "Johnson", "Garcia", "Martinez", "Lee", "Kim", "Chen", "Wang",
]
COUNTRIES = ["IN", "US", "GB", "AE", "SG", "NG", "RU", "CN"]
ID_TYPES = ["passport", "national_id", "drivers_license", "voter_id"]

# Countries with a documented elevated AML risk perception in this synthetic
# world only — not a claim about any real jurisdiction's actual FATF status.
_HIGHER_RISK_COUNTRIES = {"NG", "RU"}


def _make_names(rng: np.random.Generator, n: int) -> list[str]:
    first = rng.choice(FIRST_NAMES, size=n)
    last = rng.choice(LAST_NAMES, size=n)
    return [f"{f} {l}" for f, l in zip(first, last)]


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)

    pep_names = _make_names(rng, N_PEP)
    sanctions_names = _make_names(rng, N_SANCTIONS)
    pep_df = pd.DataFrame({"full_name": pep_names, "role": "PEP (synthetic)"})
    sanctions_df = pd.DataFrame({"full_name": sanctions_names, "list": "SYNTHETIC-SANCTIONS-1"})

    applicant_names = _make_names(rng, N_APPLICANTS)
    # A handful of applicants deliberately reuse a PEP/sanctions name so the
    # screening rules have something real to match against.
    n_pep_hits = int(N_APPLICANTS * 0.02)
    n_sanctions_hits = int(N_APPLICANTS * 0.01)
    for i in rng.choice(N_APPLICANTS, size=n_pep_hits, replace=False):
        applicant_names[i] = rng.choice(pep_names)
    for i in rng.choice(N_APPLICANTS, size=n_sanctions_hits, replace=False):
        applicant_names[i] = rng.choice(sanctions_names)

    ages = rng.integers(18, 75, size=N_APPLICANTS)
    countries = rng.choice(COUNTRIES, size=N_APPLICANTS, p=[0.4, 0.2, 0.1, 0.1, 0.1, 0.04, 0.03, 0.03])
    id_types = rng.choice(ID_TYPES, size=N_APPLICANTS)

    document_quality_score = np.clip(rng.normal(0.75, 0.18, size=N_APPLICANTS), 0, 1)
    address_match_score = np.clip(rng.normal(0.8, 0.15, size=N_APPLICANTS), 0, 1)
    selfie_liveness_score = np.clip(rng.normal(0.85, 0.12, size=N_APPLICANTS), 0, 1)
    device_risk_score = np.clip(rng.beta(2, 6, size=N_APPLICANTS), 0, 1)
    application_velocity_24h = rng.poisson(0.3, size=N_APPLICANTS)

    pep_match = np.array([name in pep_names for name in applicant_names])
    sanctions_match = np.array([name in sanctions_names for name in applicant_names])
    adverse_media_hit = rng.random(N_APPLICANTS) < 0.03

    applicants = pd.DataFrame(
        {
            "applicant_id": [f"A{i:06d}" for i in range(N_APPLICANTS)],
            "full_name": applicant_names,
            "age_years": ages,
            "country_of_residence": countries,
            "id_type": id_types,
            "document_quality_score": document_quality_score.round(4),
            "address_match_score": address_match_score.round(4),
            "selfie_liveness_score": selfie_liveness_score.round(4),
            "device_risk_score": device_risk_score.round(4),
            "application_velocity_24h": application_velocity_24h,
            "pep_match": pep_match,
            "sanctions_match": sanctions_match,
            "adverse_media_hit": adverse_media_hit,
        }
    )

    # Synthetic ground-truth label: "should this onboarding be treated as
    # high risk". Not a real fraud model target — a documented function of
    # the same risk signals, with noise, so the vertical has something to
    # actually train LightGBM/XGBoost against.
    risk_score = (
        0.35 * (1 - document_quality_score)
        + 0.15 * (1 - address_match_score)
        + 0.15 * (1 - selfie_liveness_score)
        + 0.20 * device_risk_score
        + 0.10 * np.clip(application_velocity_24h / 3, 0, 1)
        + 0.25 * sanctions_match.astype(float)
        + 0.15 * pep_match.astype(float)
        + 0.10 * adverse_media_hit.astype(float)
        + 0.10 * np.isin(countries, list(_HIGHER_RISK_COUNTRIES)).astype(float)
    )
    noise = rng.normal(0, 0.08, size=N_APPLICANTS)
    prob_high_risk = 1 / (1 + np.exp(-8 * (risk_score + noise - 0.55)))
    applicants["high_risk_label"] = (rng.random(N_APPLICANTS) < prob_high_risk).astype(int)

    return {"applicants": applicants, "pep_list": pep_df, "sanctions_list": sanctions_df}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = generate()
    for name, df in data.items():
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"wrote {path} ({len(df)} rows)")
    print(f"high_risk_label positive rate: {data['applicants']['high_risk_label'].mean():.4f}")


if __name__ == "__main__":
    main()
