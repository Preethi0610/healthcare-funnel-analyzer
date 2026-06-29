# Healthcare Data Pipeline & Patient Funnel Analyzer

> End-to-end data pipeline analyzing 74,582 clinical trials to map patient drop-off across the drug development funnel and predict trial termination risk at enrollment.

![Python](https://img.shields.io/badge/Python-3.10-blue?style=flat&logo=python)
![pandas](https://img.shields.io/badge/pandas-2.3-green?style=flat)
![XGBoost](https://img.shields.io/badge/XGBoost-3.2-orange?style=flat)
![Plotly](https://img.shields.io/badge/Plotly-6.8-purple?style=flat)
![Power BI](https://img.shields.io/badge/PowerBI-Dashboard-yellow?style=flat)
![dbt](https://img.shields.io/badge/dbt-ready-red?style=flat)

---

## What This Project Does

Most clinical trials fail silently — sponsors know a trial terminated, but not *where* patients dropped out or *which signals predicted it*. This project builds a production-style data pipeline that:

1. Ingests 589,449 raw clinical trial records from ClinicalTrials.gov (AACT database)
2. Filters and cleans a cohort of 74,582 Phase 2/3 interventional trials
3. Constructs a 5-stage patient funnel showing exactly where attrition occurs
4. Segments drop-off rates by phase, sponsor type, and enrollment size
5. Trains an XGBoost classifier that predicts trial termination risk at enrollment
6. Surfaces risk scores and funnel insights in an interactive Power BI dashboard

---

## Key Findings

| Finding | Number |
|---|---|
| Trials analyzed (Phase 2/3) | 74,582 |
| Overall termination rate | 15.1% |
| Phase 2 termination rate | 17.6% |
| Phase 3 termination rate | 11.8% |
| Trials that never post results | 56.1% |
| Top withdrawal reason | Withdrawal by Subject (382,301 cases) |
| Model ROC-AUC (XGBoost) | 0.8124 |
| Very High Risk band — actual termination rate | 64.8% |
| Low Risk band — actual termination rate | 4.0% |

**The model creates a 16x separation in termination rate between the lowest and highest risk bands.** Trials flagged as Very High Risk terminate at 64.8% vs 4.0% for Low Risk trials.

---

## Patient Funnel — 5 Stages

```
Stage 1: Registered Phase 2/3 Trials         74,582   (100.0%)
Stage 2: Enrollment Data Recorded             66,495   ( 89.2%)   drop: -8,087
Stage 3: Reached Primary Completion Date      69,249   ( 92.8%)
Stage 4: Completed (Not Terminated)           63,296   ( 84.9%)   drop: -5,953
Stage 5: Results Posted Publicly              32,737   ( 43.9%)   drop: -30,559
```

Only 43.9% of completed Phase 2/3 trials publish their results — a significant public health transparency gap.

---

## Risk Model Performance

| Model | ROC-AUC | F1 (macro) | Avg Precision |
|---|---|---|---|
| Logistic Regression (baseline) | 0.7481 | 0.6008 | 0.3639 |
| Random Forest | 0.7994 | 0.6911 | 0.5105 |
| **XGBoost (best)** | **0.8124** | **0.6859** | **0.5555** |

### Risk Band Validation

| Risk Band | Trial Count | Actual Termination Rate |
|---|---|---|
| Low (0-25%) | 4,849 | 4.0% |
| Medium (25-50%) | 6,407 | 9.3% |
| High (50-75%) | 2,207 | 23.9% |
| Very High (75-100%) | 1,454 | 64.8% |

### Top Risk Factors (XGBoost Feature Importance)

| Feature | Importance | Interpretation |
|---|---|---|
| log_enrollment | 0.2416 | Enrollment size is the strongest predictor |
| is_actual_enrollment | 0.1775 | Whether enrollment was reported as actual vs anticipated |
| has_outcomes_posted | 0.1362 | Trials with posted outcomes are less likely to terminate |
| is_multinational | 0.0771 | Multi-country trials show different risk profiles |
| log_withdrawals | 0.0702 | Higher dropout count signals termination risk |

---

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.10 | Core language |
| pandas 2.3 | Data wrangling and feature engineering |
| numpy | Numerical operations |
| scikit-learn | Model training, evaluation, imputation |
| XGBoost 3.2 | Primary risk classifier |
| plotly 6.8 | Interactive EDA and funnel charts |
| joblib | Model serialization |
| pyarrow | Parquet file format for processed data |
| Power BI | Executive dashboard and stakeholder reporting |
| dbt | Data transformation layer (staging + mart models) |
| SQL | Cohort building and funnel queries |
| Git + GitHub | Version control and portfolio publishing |

---

## Project Structure

```
healthcare-funnel-analyzer/
│
├── src/
│   ├── 01_load_data.py          # Data ingestion, filtering, parquet export
│   ├── 02_funnel_analysis.py    # Funnel construction, segmentation, EDA charts
│   └── 03_ml_model.py           # Feature engineering, model training, risk scores
│
├── sql/
│   └── funnel_query.sql         # Core CTE-based funnel SQL
│
├── dbt/
│   ├── models/staging/          # stg_studies, stg_drop_withdrawals, stg_eligibilities
│   └── models/marts/            # mart_trial_funnel, mart_risk_features
│
├── reports/
│   ├── eda/                     # 6 interactive Plotly charts (HTML)
│   └── shap/                    # ROC curves, feature importance, risk distribution
│
├── dashboard/
│   └── healthcare_funnel.pbix   # Power BI dashboard (3 pages)
│
├── models/
│   ├── risk_classifier_xgb.pkl  # Trained XGBoost model
│   └── imputer.pkl              # Fitted median imputer
│
├── data/                        # GITIGNORED
│   ├── raw/aact/                # Original AACT pipe-delimited flat files
│   └── processed/               # Cleaned parquet files + risk_scores.csv
│
├── requirements.txt
└── README.md
```

---

## How to Run

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/healthcare-funnel-analyzer.git
cd healthcare-funnel-analyzer
```

### 2. Set up environment
```bash
conda activate vad-thesis
pip install -r requirements.txt
```

### 3. Download data
Download the AACT pipe-delimited flat files from:
https://aact.ctti-clinicaltrials.org/pipe_files

Extract all `.txt` files into `data/raw/aact/`

### 4. Run the pipeline
```bash
python src/01_load_data.py        # ~2 min
python src/02_funnel_analysis.py  # ~1 min
python src/03_ml_model.py         # ~3 min
```

### 5. View outputs
- EDA charts: `reports/eda/*.html` — open in any browser
- Model charts: `reports/shap/*.html` — open in any browser
- Risk scores: `data/processed/risk_scores.csv` — import into Power BI

---

## Data Source

**AACT (Aggregate Analysis of ClinicalTrials.gov)**
- Provider: Clinical Trials Transformation Initiative (CTTI)
- Access: https://aact.ctti-clinicaltrials.org/pipe_files
- License: Public domain — free for research and commercial use
- Snapshot used: June 2025 monthly archive
- Raw size: ~1.2 GB compressed, ~5.5 GB unzipped

---

## Limitations

- Enrollment data is self-reported by sponsors — actual vs anticipated figures are not always consistent
- AACT does not track patient-level data — all analysis is at the trial level
- Termination reasons (why_stopped) are missing for 86.7% of trials — this limits root cause analysis
- The funnel Stage 2/3 ordering has a minor data quirk — some trials have primary completion dates without enrollment records, which is a known AACT data quality issue
- Model predicts termination based on features available at enrollment — post-enrollment signals (adverse events, interim analyses) are not included

---

## About

Built by Preethi Amasa as a portfolio project targeting Data Analyst and Data Engineer roles in healthcare and pharma. The project demonstrates end-to-end data pipeline skills including ingestion, transformation, funnel analysis, ML modeling, and BI reporting using real government data.

**LinkedIn:** [your LinkedIn URL]
**Dashboard:** [Power BI published link]