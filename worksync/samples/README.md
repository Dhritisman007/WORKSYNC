# Sample upload files

One file per vertical, each with 3 rows chosen to hit a different outcome —
upload them in the Streamlit app ("Upload a file" in the sidebar) to
confirm the pipeline is actually working end to end, not just browsing the
pre-loaded dataset.

Verified by running each file directly through the orchestrator (see
`CHANGELOG.md`'s "sample verification" note) — these are the actual
results, not predictions:

## `loan_sample.csv`

| Row | What's different | Outcome |
|---|---|---|
| 0 | High income, strong external scores, low debt ratio | **approve** |
| 1 | Annuity is 70% of income (debt-to-income over the 0.6 hard threshold) | **reject** (`LOAN-DTI-001`) |
| 2 | Missing credit-bureau score and occupation — can't assess creditworthiness | **escalate** (`LOAN-KYC-001`) |

## `kyc_aml_sample.json`

| Row | What's different | Outcome |
|---|---|---|
| 0 | Clean identity, good scores, no watchlist hits | **approve** |
| 1 | Name matches the (synthetic) PEP list | **escalate** (`KYC-PEP-001`) |
| 2 | Name matches the (synthetic) sanctions list | **reject** (`KYC-SANCTIONS-001`) |

## `bnpl_sample.csv`

| Row | What's different | Outcome |
|---|---|---|
| 0 | Small, ordinary transaction amount | **approve** |
| 1 | Amount above 2,000 (soft review threshold) | **approve**, flagged (`BNPL-AMOUNT-002`) |
| 2 | Amount above 10,000 (hard threshold) | **escalate** (`BNPL-AMOUNT-001`) |

## `insurance_sample.csv`

| Row | What's different | Outcome |
|---|---|---|
| 0 | Long-standing policy, evidence on file, no past claims | **approve** |
| 1 | Accident within 7 days of the policy starting, no police report/witness | **escalate** (`INS-TIMING-001`) |
| 2 | Vehicle price in the highest bracket (more than 69,000) | **escalate** (`INS-HIGHVALUE-001`) |

## Using them

1. Run the app: `streamlit run worksync/app/streamlit_app.py`
2. Pick the matching vertical in the sidebar.
3. Switch "Case source" to **Upload a file**.
4. Upload the corresponding file here.
5. For a CSV with multiple rows, use "Row in uploaded file" to step through
   row 0/1/2 and watch the decision change.
