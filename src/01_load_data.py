import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

RAW = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/data/raw/aact")
PROCESSED = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/data/processed")
os.makedirs(PROCESSED, exist_ok=True)

def load_table(filename, usecols=None):
    path = os.path.join(RAW, filename)
    df = pd.read_csv(path, sep='|', encoding='utf-8', low_memory=False, usecols=usecols)
    print(f"{filename:<40} {df.shape[0]:>8,} rows  {df.shape[1]:>3} cols")
    return df

print("\n" + "="*60)
print("  LOADING AACT TABLES")
print("="*60)

# Core tables for the funnel
studies = load_table("studies.txt", usecols=[
    'nct_id', 'overall_status', 'phase', 'enrollment', 'enrollment_type',
    'study_type', 'start_date', 'completion_date', 'primary_completion_date',
    'study_first_submitted_date', 'results_first_submitted_date',
    'number_of_arms', 'number_of_groups', 'why_stopped', 'has_expanded_access'
])

sponsors = load_table("sponsors.txt", usecols=[
    'nct_id', 'agency_class', 'lead_or_collaborator', 'name'
])

eligibilities = load_table("eligibilities.txt", usecols=[
    'nct_id', 'gender', 'minimum_age', 'maximum_age',
    'healthy_volunteers', 'criteria'
])

drop_withdrawals = load_table("drop_withdrawals.txt", usecols=[
    'nct_id', 'period', 'reason', 'count'
])

outcomes = load_table("outcomes.txt", usecols=[
    'nct_id', 'outcome_type', 'title', 'time_frame', 'population'
])

conditions = load_table("conditions.txt", usecols=[
    'nct_id', 'name', 'downcase_name'
])

facilities_raw = load_table("facilities.txt", usecols=['nct_id', 'country'])  

facilities = facilities_raw.groupby('nct_id').agg(
    site_count=('country', 'count'),
    is_multinational=('country', lambda x: int(x.nunique() > 1))
).reset_index()

print(f"{'facilities.txt (aggregated)':<40} {len(facilities):>8,} rows   2 cols")

del facilities_raw

# Load reported_events — aggregate immediately, don't keep full table
reported_events_raw = load_table("reported_events.txt" , usecols=['nct_id', 'event_type', 'subjects_affected', 'subjects_at_risk'])

reported_events = reported_events_raw.groupby(['nct_id', 'event_type']).agg(
    total_affected=('subjects_affected', 'sum'),
    total_at_risk=('subjects_at_risk', 'sum')
).reset_index()

del reported_events_raw

print(f"{'reported_events.txt (aggregated)':<40} {len(reported_events):>8,} rows   4 cols")

interventions = load_table("interventions.txt", usecols=[
    'nct_id', 'intervention_type', 'name'
])

print("\n" + "="*60)
print("  FILTERING COHORT")
print("="*60)

print(f"\nTotal studies before filter: {len(studies):,}")

# Keep only interventional trials in Phase 2 or 3
# with a completed or terminated status
cohort = studies[
    (studies['study_type'] == 'INTERVENTIONAL') &
    (studies['phase'].isin(['PHASE2', 'PHASE3', 'PHASE2/PHASE3'])) &
    (studies['overall_status'].isin(['COMPLETED', 'TERMINATED']))
].copy()

print(f"After filter (Interventional, Phase 2/3, Completed/Terminated): {len(cohort):,}")

# Class balance check
status_counts = cohort['overall_status'].value_counts()
print(f"\nClass Balance:")
for status, count in status_counts.items():
    pct = count / len(cohort) * 100
    print(f"  {status:<15} {count:>6,}  ({pct:.1f}%)")

print("\n" + "="*60)
print("  NULL AUDIT — STUDIES COHORT")
print("="*60)

null_report = pd.DataFrame({
    'column': cohort.columns,
    'null_count': cohort.isnull().sum().values,
    'null_pct': (cohort.isnull().sum().values / len(cohort) * 100).round(1)
}).sort_values('null_pct', ascending=False)

print(null_report[null_report['null_count'] > 0].to_string(index=False))

print("\n" + "="*60)
print("  PHASE DISTRIBUTION")
print("="*60)

phase_dist = cohort.groupby(['phase', 'overall_status']).size().unstack(fill_value=0)
phase_dist['total'] = phase_dist.sum(axis=1)
phase_dist['termination_rate_%'] = (
    phase_dist.get('Terminated', 0) / phase_dist['total'] * 100
).round(1)
print(phase_dist.to_string())

print("\n" + "="*60)
print("  SPONSOR TYPE DISTRIBUTION")
print("="*60)

# Get lead sponsors only
lead_sponsors = sponsors[sponsors['lead_or_collaborator'] == 'lead'][['nct_id', 'agency_class']]
cohort_with_sponsor = cohort.merge(lead_sponsors, on='nct_id', how='left')

sponsor_dist = cohort_with_sponsor.groupby('agency_class')['nct_id'].count().sort_values(ascending=False)
print(sponsor_dist.to_string())

print("\n" + "="*60)
print("  ENROLLMENT STATS")
print("="*60)

enroll = cohort[cohort['enrollment'].notna()]['enrollment']
print(f"  Mean enrollment:   {enroll.mean():>8,.0f}")
print(f"  Median enrollment: {enroll.median():>8,.0f}")
print(f"  Min enrollment:    {enroll.min():>8,.0f}")
print(f"  Max enrollment:    {enroll.max():>8,.0f}")
print(f"  Std deviation:     {enroll.std():>8,.0f}")

print("\n" + "="*60)
print("  SAVING TO PROCESSED FOLDER")
print("="*60)

# Save filtered cohort
cohort.to_parquet(os.path.join(PROCESSED, "cohort_studies.parquet"), index=False)
print(f"cohort_studies.parquet saved  ({len(cohort):,} rows)")

# Save filtered versions of supporting tables (only nct_ids in cohort)
cohort_ids = set(cohort['nct_id'])

def save_filtered(df, name):
    filtered = df[df['nct_id'].isin(cohort_ids)].copy()
    filtered.to_parquet(os.path.join(PROCESSED, f"{name}.parquet"), index=False)
    print(f"{name}.parquet saved  ({len(filtered):,} rows)")

save_filtered(sponsors,         "cohort_sponsors")
save_filtered(eligibilities,    "cohort_eligibilities")
save_filtered(drop_withdrawals, "cohort_drop_withdrawals")
save_filtered(outcomes,         "cohort_outcomes")
save_filtered(conditions,       "cohort_conditions")
save_filtered(facilities,       "cohort_facilities")
save_filtered(reported_events,  "cohort_reported_events")
save_filtered(interventions,    "cohort_interventions")

print("\n" + "="*60)
print("  PHASE 1 COMPLETE ALL FILES SAVED TO /data/processed/")
print("="*60)