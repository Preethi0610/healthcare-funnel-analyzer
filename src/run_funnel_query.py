import psycopg2
import pandas as pd
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

HOST     = "aact-db.ctti-clinicaltrials.org"
PORT     = 5432
DATABASE = "aact"
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

if not USERNAME or not PASSWORD:
    raise SystemExit(
        "Missing credentials. Run:\n"
        "  export USERNAME='your_username'\n"
        "  export PASSWORD='your_password'\n"
        "before running this script."
    )

SQL_FILE = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/sql/funnel_query.sql")
CSV_DIR  = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/data/processed/sql_verified")
TXT_DIR  = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/reports/sql_output")
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(TXT_DIR, exist_ok=True)

log_lines = []
def log(text=""):
    print(text)
    log_lines.append(str(text))


with open(SQL_FILE, "r") as f:
    full_sql = f.read()

cte_block = full_sql.split("-- FINAL OUTPUT")[0]

cte_block = cte_block.rstrip()
if cte_block.endswith(","):
    cte_block = cte_block[:-1]

log("="*60)
log("  SQL VERIFICATION OUTPUT - FULL funnel_query.sql (12 CTEs)")
log(f"  Run date: {datetime.now().strftime('%B %d, %Y %H:%M')}")
log("="*60)
log()

log("Connecting to AACT live database...")
conn = psycopg2.connect(host=HOST, port=PORT, dbname=DATABASE, user=USERNAME, password=PASSWORD)
log("Connected.\n")

outputs = [
    ("master_trial",         "01_master_trial_sample.csv",     "Full master trial table (first 20 rows shown)"),
    ("funnel_with_rates",    "02_funnel_with_rates.csv",        "5-stage funnel with conversion rates"),
    ("phase_segmentation",   "03_phase_segmentation.csv",       "Termination rate by phase"),
    ("sponsor_segmentation", "04_sponsor_segmentation.csv",     "Termination rate by sponsor type"),
    ("withdrawal_reasons",   "05_withdrawal_reasons.csv",       "Top 15 withdrawal reasons"),
    ("high_risk_trials",     "06_high_risk_trials.csv",         "Top 50 highest-risk trials"),
]

for cte_name, filename, description in outputs:
    log("="*60)
    log(f"  OUTPUT: {cte_name}")
    log(f"  {description}")
    log("="*60)

    query = f"{cte_block}\nSELECT * FROM {cte_name};"

    try:
        df = pd.read_sql(query, conn)

        if cte_name == "master_trial":
            log(f"Total rows returned: {len(df):,}")
            log(df.head(20).to_string(index=False))
            df.to_csv(os.path.join(CSV_DIR, filename), index=False)
        else:
            log(df.to_string(index=False))
            df.to_csv(os.path.join(CSV_DIR, filename), index=False)

        log(f"\nSaved: data/processed/sql_verified/{filename}\n")

    except Exception as e:
        log(f"ERROR running {cte_name}: {e}\n")
        conn.rollback()

conn.close()

log("="*60)
log("  ALL 6 OUTPUTS EXECUTED FROM THE FULL 12-CTE funnel_query.sql")
log(f"  CSV files saved to:  data/processed/sql_verified/")
log("="*60)

txt_path = os.path.join(TXT_DIR, "sql_verification_output.txt")
with open(txt_path, "w") as f:
    f.write("\n".join(log_lines))

print(f"\nFull log written to: {txt_path}")