Healthcare Data Pipeline & Patient Funnel Analyzer


An end-to-end data project that ingests 589,449 real clinical trial records, builds a 5-stage patient funnel for 74,582 Phase 2/3 trials, and trains a risk classifier that separates high-termination-risk trials from low-risk ones with a 16x difference in actual outcome.



Show Image
Show Image
Show Image
Show Image
Show Image
Show Image


1. Objective

Roughly 90% of drugs that enter clinical trials never reach the market, and a large share of that loss happens not from the drug failing scientifically but from the trial itself breaking down -- patients dropping out, enrollment stalling, sponsors pulling funding. Most organizations only find out a trial is in trouble after it has already been terminated.

The objective of this project was to build a complete, reproducible data pipeline -- from raw government data to a predictive model to a stakeholder-facing dashboard -- that identifies where in the trial lifecycle patients are lost and which trial characteristics predict termination risk early enough to act on it.

This was built specifically to demonstrate the overlapping skill set required for Data Analyst and Data Engineer roles in healthcare: SQL, Python, a real ETL pipeline, statistical/ML modeling, and BI reporting, all applied to one coherent real-world problem rather than disconnected exercises.


2. Questions This Project Tries to Answer


At which stage of the clinical trial lifecycle do trials/patients drop out the most?
Does the trial phase (Phase 2 vs Phase 3) predict termination risk?
Does the type of sponsor (industry, NIH, academic, individual investigator) predict termination risk?
What are the most common reasons trials report for patient withdrawal?
Can a model trained only on information available at enrollment predict which trials are at high risk of terminating, before that information is obvious?
How much real separation does that model create between a "safe" trial and a "risky" one?
What share of completed trials ever publish their results publicly, and does that vary by phase?



3. Data Source

AACT (Aggregate Analysis of ClinicalTrials.gov) -- a public, structured database maintained by the Clinical Trials Transformation Initiative (a Duke University / FDA partnership). AACT reformats the U.S. government's raw ClinicalTrials.gov registry into clean relational tables covering the full lifecycle of every U.S. clinical trial: registration, sponsorship, eligibility, enrollment, adverse events, withdrawals, outcomes, and results.


Source: https://aact.ctti-clinicaltrials.org
Format used: pipe-delimited flat files (monthly snapshot) and a live PostgreSQL connection for verification
Raw size: ~589,449 total studies across 9 tables before filtering


This is real government data, not a synthetic or pre-cleaned Kaggle dataset -- every number in this project traces back to an actual registered clinical trial.


4. Process -- What Was Actually Built, Phase by Phase

Phase 1 -- Data Ingestion (01_load_data.py)

Loaded 9 raw AACT tables (studies, sponsors, eligibilities, drop_withdrawals, outcomes, conditions, facilities, reported_events, interventions), selecting only the columns needed to answer the project's questions. Two large tables (facilities -- 3.4M rows, reported_events -- 11.7M rows) were aggregated immediately on load rather than held in full, to keep the pipeline runnable on a local machine.

The cohort was filtered to: study_type = INTERVENTIONAL, phase IN (PHASE2, PHASE2/PHASE3, PHASE3), overall_status IN (COMPLETED, TERMINATED).

Output: 9 cleaned, cohort-filtered parquet files in /data/processed/.

Phase 2 -- Funnel Analysis & EDA (02_funnel_analysis.py)

Built features (trial duration, results-posted flag, lead sponsor type, site count, withdrawal totals, primary outcome counts), then constructed a 5-stage funnel where each stage is a genuine subset of the one before it:

Stage 1: Registered (Phase 2/3)
Stage 2: Enrollment Data Recorded
Stage 3: Reached Primary Completion Date
Stage 4: Completed (Not Terminated)
Stage 5: Results Posted Publicly

Segmented termination rate by phase and by sponsor type, identified the top 15 reported withdrawal reasons, and generated 6 interactive Plotly charts.

Output: master_funnel.parquet (the feature table everything downstream builds on) + 6 HTML charts in /reports/eda/.

Phase 3 -- ML Risk Classifier (03_ml_model.py)

Engineered 11 model features (log-transformed enrollment, log-transformed withdrawals, sponsor encoding, phase, site count, duration, etc.), then trained and compared three models with scale_pos_weight/class_weight='balanced' to handle the ~85/15 class imbalance:

ModelROC-AUCF1 (macro)Avg PrecisionLogistic Regression (baseline)0.74810.60080.3639Random Forest0.79940.69110.5105XGBoost (selected)0.81240.68590.5555

Output: trained model (risk_classifier_xgb.pkl), 3 evaluation charts, and risk_scores.csv/.parquet -- risk scores for all 74,582 trials, used downstream by Excel, Tableau, and SQL.

Phase 4 -- SQL (sql/funnel_query.sql + run_funnel_query.py)

Wrote a 12-CTE PostgreSQL query that independently reconstructs the cohort filter, funnel stages, phase/sponsor segmentation, withdrawal-reason aggregation, and a high-risk-trial scoring logic -- entirely in SQL, separate from the pandas pipeline.

This was not just written and left untested -- it was executed against AACT's live PostgreSQL database (aact-db.ctti-clinicaltrials.org) using run_funnel_query.py, which reads the actual .sql file, runs all 6 of its possible outputs, and saves verified CSV output plus a full text log.

Output: reports/sql_output/sql_verification_output.txt and 6 verified CSVs in data/processed/sql_verified/.

Phase 5 -- Excel Reporting (healthcare_funnel_report.xlsx)

Built manually in Excel (not auto-generated) to demonstrate genuine Excel/Power Query proficiency: imported risk_scores.csv via Power Query, built 3 pivot tables (Phase Analysis, Sponsor Analysis, Risk Band Analysis) with calculated termination-rate columns, embedded bar charts, and a cover summary sheet.

Phase 6 -- Tableau Dashboard

Built an interactive Tableau Public dashboard with 4 linked views -- a risk-band funnel, termination rate by phase, termination rate by sponsor type, and a risk-score distribution histogram -- connected via dashboard filter actions so that clicking any bar filters all other charts simultaneously. Published as a Tableau Story with guided narrative captions.


5. Tools Used

ToolWhere it was usedPython (pandas, numpy)Data ingestion, feature engineering, funnel constructionscikit-learnLogistic Regression, Random Forest, train/test split, evaluation metricsXGBoostFinal risk classifierPlotlyAll EDA and model-evaluation chartsPostgreSQL (T-SQL dialect also written)Independent funnel logic, live-verified against AACT's databasepsycopg2 / python-dotenvLive database connection, credential handlingExcel + Power QueryPivot-based stakeholder reportingTableau PublicInteractive, filterable dashboard + guided StoryGit / GitHubVersion control and portfolio publishing


6. Outputs at Each Stage

StageArtifactVerified?Ingestion9 cohort-filtered parquet filesRow counts logged on every runFunnel analysismaster_funnel.parquet, 6 HTML chartsCross-checked against live SQLML modelrisk_classifier_xgb.pkl, risk_scores.csv, 3 chartsTest-set metrics reported, not training-setSQL6 CSVs + full text execution logRun live against AACT PostgreSQL, not just writtenExcelhealthcare_funnel_report.xlsx (4 sheets + raw data)Built from the same risk_scores.csv, numbers cross-checkedTableauPublished interactive dashboard + StoryFilter actions tested and working


7. Key Findings


Results transparency gap: only 43.9% of completed Phase 2/3 trials ever post their results publicly. More than half of completed clinical research is never made publicly visible in structured form.
Phase matters: Phase 2 trials terminate at 17.6% vs 11.8% for Phase 3 -- later-phase trials, having already survived an earlier filtering stage, are meaningfully more likely to finish.
Sponsor type matters: Individual-investigator-led trials terminate at 19.6%, the highest of any sponsor category; federally-funded trials terminate least often, at 9.1%.
The #1 reported reason for withdrawal across all trials is "Withdrawal by Subject" (383,319 instances, live-verified), followed by adverse events and death -- underscoring that patient-level attrition, not just sponsor decisions, drives a large share of trial risk.
The model creates real, honest separation on unseen data. On the held-out test set (14,917 trials the model never trained on), trials it scored as Very High Risk terminated at 64.8%, compared to 4.0% for trials it scored Low Risk -- a 16x difference. (Scored across the entire dataset including training data, the same bands show 67.2% vs 2.6% -- slightly more optimistic, as expected, since the model has partially "seen" those rows during training. The test-set numbers are the honest measure of real-world performance.)
Enrollment size is the single strongest predictor of termination risk (XGBoost feature importance: 0.242), ahead of sponsor type, site count, or trial duration.



8. How This Applies to the Real World


Pharma/CRO portfolio risk triage: a sponsor running dozens of simultaneous trials could use a model like this to flag which trials need closer monitoring or intervention before they reach a costly late-stage termination.
Regulatory/policy transparency tracking: the results-posting compliance metric mirrors a real, ongoing concern among regulators (FDA, NIH) about underreporting of completed trial outcomes.
Site and sponsor selection: the sponsor-type and enrollment findings could inform how a CRO chooses which sponsors or trial designs represent lower operational risk.
The pipeline architecture itself -- raw ingestion to SQL-verified transformation to ML scoring to BI dashboard -- mirrors the standard analytics engineering pattern used in real healthcare/pharma data teams, just at a portfolio scale.



9. Conclusion

This project shows that a meaningful amount of clinical trial risk is visible in structural data available at enrollment, not just in clinical outcomes after the fact. A relatively simple, well-validated XGBoost model, built from publicly available registry data, achieves a 16x separation in real termination outcomes between its lowest and highest risk bands on data it had never seen. Combined with a funnel analysis that pinpoints exactly where trials lose momentum (most sharply between primary completion and public results reporting), this gives a concrete, data-backed starting point for where intervention would matter most.


10. Limitations


Enrollment figures are self-reported by sponsors; actual vs. anticipated enrollment is not always consistently distinguished in the source data.
AACT records trial-level, not patient-level, data -- all analysis here describes trial outcomes, not individual patient journeys.
why_stopped (the free-text termination reason) is missing for 86.7% of trials, limiting root-cause analysis for many terminated trials.
A small funnel ordering quirk exists between Stage 2 and Stage 3 (a handful of trials have a primary completion date recorded without a formal enrollment figure) -- a known AACT data-quality artifact, not a pipeline bug.
The model's risk score reflects structural/administrative risk factors, not clinical efficacy or safety -- it cannot and does not predict whether a drug works.



11. What Could Be Added Next


Therapeutic area segmentation -- the conditions table was loaded but not yet used to compare termination risk across oncology, cardiology, infectious disease, etc.
SHAP explainability -- individual trial-level explanations for why a specific trial was scored high-risk, beyond global feature importance.
S3 staging layer -- landing risk_scores.csv in an S3 bucket and pointing Tableau/Power BI at it directly, to demonstrate a cloud data-engineering pattern rather than a local file handoff.
Power BI version -- a second BI deliverable alongside Tableau, since both tools are commonly requested in different job postings.
Excel VBA macro -- a small macro to auto-refresh the Power Query connection when risk_scores.csv updates, rounding out the Excel automation story.
dbt staging/mart models -- formalizing the SQL transformation layer using dbt instead of a single flat .sql file, for a closer match to a modern production data stack.



Project Structure

healthcare-funnel-analyzer/
├── src/
│   ├── 01_load_data.py
│   ├── 02_funnel_analysis.py
│   ├── 03_ml_model.py
│   └── run_funnel_query.py
├── sql/
│   └── funnel_query.sql
├── reports/
│   ├── eda/                  (6 Plotly HTML charts)
│   ├── shap/                 (3 model evaluation charts)
│   └── sql_output/           (live SQL verification log)
├── data/
│   ├── raw/aact/              (gitignored)
│   └── processed/              (gitignored; includes sql_verified/)
├── models/
│   ├── risk_classifier_xgb.pkl
│   └── imputer.pkl
├── healthcare_funnel_report.xlsx
├── requirements.txt
└── README.md


About

Built by Preethi Amasa as a portfolio project targeting Data Analyst and Data Engineer roles in healthcare and pharma, demonstrating end-to-end pipeline skills: ingestion, SQL validation, funnel analysis, ML modeling, and multi-tool BI reporting on real government clinical trial data.
