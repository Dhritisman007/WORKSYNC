# Blind test files — answer key

Don't open this until you've uploaded the files. Each CSV uses real rows from
the source datasets (ground-truth labels removed), with deliberately messy
headers: different casing, spaces or hyphens instead of underscores, shuffled
column order, an extra irrelevant "Submitted By" column, and in file C, typos.

| File | Actually is | What it tests | Detector result (verified) |
|---|---|---|---|
| `test_file_A.csv` | Insurance claims | lowercase + spaces, shuffled, junk column | **Declared** Insurance Claims, 100% |
| `test_file_B.csv` | KYC/AML | Title Case With Spaces | **Declared** KYC / AML, 100% |
| `test_file_C.csv` | Loan | hyphens + typos (`amt-income-totl`, `amt-credt`, `name-eduction-type`) | **Declared** Loan, 100% (3 fuzzy matches) |
| `test_file_D.csv` | Credit card / BNPL | lowercase, no junk column | **Declared** Credit Card / BNPL, 100% |
| `test_file_E.csv` | Loan, partial (8 of 25 columns) | incomplete but unambiguous file | **Declared** Loan, with an "incomplete data" warning |
| `test_file_F.csv` | Nothing (HR employee data) | should NOT be forced into a vertical | **No match** — 0% everywhere |

Every wrong vertical scored 0% for every file — no cross-vertical confusion.

## Ground truth vs. the model's decision

These are real outcomes from the source data, so you can see where the risk
model is right and where it isn't:

- **A (insurance)**: rows 0–1 were real fraudulent claims, rows 2–4 genuine.
  The model approved both frauds (low score, no hard rule fired) — real false
  negatives. Row 3 escalated on the high-value-vehicle rule.
- **B (KYC/AML)**: row 0 = sanctions hit → rejected; row 1 = PEP → escalated;
  rows 2–4 clean (row 4 escalated for low confidence).
- **C (loan)**: rows 0–1 were real defaults, rows 2–4 repaid. Row 0 escalated
  (correctly not auto-approved); row 1 was approved — a false negative.
- **D (BNPL)**: rows 0–1 were real frauds → both auto-rejected; rows 2–4
  legitimate → all approved. 5/5 correct.
- **E (partial loan)**: decisions run, but with 17 of 25 inputs missing the
  model is working with much less information — treat these as low-trust.
- **F**: no decision is made; you're asked to pick a vertical manually.

The vertical detection was correct on all six. The risk decisions are only
as good as each model (AUC 0.67–0.94) — that's the honest gap.
