import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import os
import warnings
warnings.filterwarnings('ignore')


PROCESSED = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/data/processed")
REPORTS   = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/reports/eda")
os.makedirs(REPORTS, exist_ok=True)

print("\n" + "="*60)
print("  LOADING PROCESSED DATA")
print("="*60)

studies     = pd.read_parquet(os.path.join(PROCESSED, "cohort_studies.parquet"))
sponsors    = pd.read_parquet(os.path.join(PROCESSED, "cohort_sponsors.parquet"))
withdrawals = pd.read_parquet(os.path.join(PROCESSED, "cohort_drop_withdrawals.parquet"))
outcomes    = pd.read_parquet(os.path.join(PROCESSED, "cohort_outcomes.parquet"))
conditions  = pd.read_parquet(os.path.join(PROCESSED, "cohort_conditions.parquet"))
facilities  = pd.read_parquet(os.path.join(PROCESSED, "cohort_facilities.parquet"))
events      = pd.read_parquet(os.path.join(PROCESSED, "cohort_reported_events.parquet"))

print(f"Studies loaded:      {len(studies):>8,}")
print(f"Withdrawals loaded:  {len(withdrawals):>8,}")
print(f"Outcomes loaded:     {len(outcomes):>8,}")
print(f"Conditions loaded:   {len(conditions):>8,}")

print("\n" + "="*60)
print("  FEATURE ENGINEERING")
print("="*60)

df = studies.copy()

# Target variable
df['is_terminated'] = (df['overall_status'] == 'TERMINATED').astype(int)

# Trial duration
df['start_date']      = pd.to_datetime(df['start_date'],      errors='coerce')
df['completion_date'] = pd.to_datetime(df['completion_date'], errors='coerce')
df['primary_completion_date'] = pd.to_datetime(df['primary_completion_date'], errors='coerce')
df['duration_days']   = (df['completion_date'] - df['start_date']).dt.days
df['duration_months'] = (df['duration_days'] / 30.44).round(1)

# Results posted flag
df['results_first_submitted_date'] = pd.to_datetime(df['results_first_submitted_date'], errors='coerce')
df['results_posted'] = df['results_first_submitted_date'].notna().astype(int)

# Actual enrollment only
df['enrollment_actual'] = df.apply(
    lambda r: r['enrollment'] if r['enrollment_type'] == 'ACTUAL' else np.nan, axis=1
)

# Phase numeric
phase_map = {'PHASE2': 2, 'PHASE2/PHASE3': 2.5, 'PHASE3': 3}
df['phase_numeric'] = df['phase'].map(phase_map)

# Lead sponsor type
lead_sponsors = sponsors[sponsors['lead_or_collaborator'] == 'lead'][['nct_id', 'agency_class']]
lead_sponsors = lead_sponsors.drop_duplicates('nct_id')
df = df.merge(lead_sponsors, on='nct_id', how='left')

# Site count and multinational flag
df = df.merge(facilities[['nct_id', 'site_count', 'is_multinational']], on='nct_id', how='left')

# Withdrawal count per trial
withdrawal_counts = withdrawals.groupby('nct_id')['count'].sum().reset_index()
withdrawal_counts.columns = ['nct_id', 'total_withdrawals']
df = df.merge(withdrawal_counts, on='nct_id', how='left')
df['total_withdrawals'] = df['total_withdrawals'].fillna(0)

# Primary outcome count
primary_outcomes = outcomes[outcomes['outcome_type'] == 'PRIMARY'].groupby('nct_id').size().reset_index()
primary_outcomes.columns = ['nct_id', 'num_primary_outcomes']
df = df.merge(primary_outcomes, on='nct_id', how='left')
df['num_primary_outcomes'] = df['num_primary_outcomes'].fillna(0)

# Outcomes posted count
results_count = outcomes[outcomes['outcome_type'].notna()].groupby('nct_id').size().reset_index()
results_count.columns = ['nct_id', 'num_outcomes_posted']
df = df.merge(results_count, on='nct_id', how='left')
df['num_outcomes_posted'] = df['num_outcomes_posted'].fillna(0)

print(f"Feature engineering complete {len(df):,} trials, {df.shape[1]} features")


print("\n" + "="*60)
print("  FUNNEL ANALYSIS 5 STAGES")
print("="*60)

# Stage 1: All Phase 2/3 interventional trials in cohort
s1 = len(df)

# Stage 2: Had enrollment data recorded
s2 = df['enrollment_actual'].notna().sum()

# Stage 3: Reached primary completion date
s3 = df['primary_completion_date'].notna().sum()

# Stage 4: Completed (not terminated)
s4 = (df['overall_status'] == 'COMPLETED').sum()

# Stage 5: Posted results publicly
s5 = df['results_posted'].sum()

stages = [
    'Registered\n(Phase 2/3)',
    'Enrollment\nData Recorded',
    'Reached Primary\nCompletion Date',
    'Completed\n(Not Terminated)',
    'Results\nPosted'
]
counts = [s1, s2, s3, s4, s5]

print(f"\n{'Stage':<35} {'Count':>8}  {'% of Total':>12}  {'Drop-off':>10}")
print("-"*70)
for i, (stage, count) in enumerate(zip(stages, counts)):
    stage_clean = stage.replace('\n', ' ')
    pct_total   = count / s1 * 100   
    dropoff     = f"-{counts[i-1] - count:,}" if i > 0 else "baseline"
    print(f"{stage_clean:<35} {count:>8,}  {pct_total:>11.1f}%  {dropoff:>10}")

print(f"\nStage-to-Stage Conversion Rates:")
for i in range(1, len(counts)):
    rate   = counts[i] / counts[i-1] * 100 if counts[i-1] > 0 else 0
    s_from = stages[i-1].replace('\n', ' ')
    s_to   = stages[i].replace('\n', ' ')
    print(f"  {s_from:<35} -> {s_to:<30} {rate:.1f}%")


fig_funnel = go.Figure(go.Funnel(
    y=stages,
    x=counts,
    textposition="inside",
    textinfo="value+percent initial",
    marker=dict(color=[
        "#1F4E79", "#2E75B6", "#4299D9", "#70B8E8", "#D6EEFF"
    ]),
    connector=dict(line=dict(color="#BBBBBB", width=1))
))
fig_funnel.update_layout(
    title=dict(text="Clinical Trial Patient Funnel - Phase 2/3 (n=74,582)", font=dict(size=18)),
    font=dict(family="Arial", size=13),
    plot_bgcolor="white",
    paper_bgcolor="white",
    height=520
)
fig_funnel.write_html(os.path.join(REPORTS, "01_funnel_overview.html"))
print(f"\nSaved: 01_funnel_overview.html")


print("\n" + "="*60)
print("  SEGMENTATION - TERMINATION RATE BY PHASE")
print("="*60)

phase_summary = df.groupby('phase').agg(
    total=('nct_id', 'count'),
    terminated=('is_terminated', 'sum'),
    completed=('overall_status', lambda x: (x == 'COMPLETED').sum()),
    results_posted=('results_posted', 'sum'),
    avg_enrollment=('enrollment_actual', 'mean'),
    avg_duration_months=('duration_months', 'mean')
).reset_index()

phase_summary['termination_rate_%'] = (
    phase_summary['terminated'] / phase_summary['total'] * 100
).round(1)
phase_summary['results_rate_%'] = (
    phase_summary['results_posted'] / phase_summary['total'] * 100
).round(1)
phase_summary['avg_enrollment'] = phase_summary['avg_enrollment'].round(0)
phase_summary['avg_duration_months'] = phase_summary['avg_duration_months'].round(1)

print(phase_summary[[
    'phase', 'total', 'terminated', 'termination_rate_%',
    'results_posted', 'results_rate_%', 'avg_enrollment'
]].to_string(index=False))


print("\n" + "="*60)
print("  SEGMENTATION - TERMINATION RATE BY SPONSOR TYPE")
print("="*60)

sponsor_summary = df.groupby('agency_class').agg(
    total=('nct_id', 'count'),
    terminated=('is_terminated', 'sum'),
    avg_enrollment=('enrollment_actual', 'mean'),
    avg_duration_months=('duration_months', 'mean')
).reset_index()

sponsor_summary['termination_rate_%'] = (
    sponsor_summary['terminated'] / sponsor_summary['total'] * 100
).round(1)
sponsor_summary['avg_enrollment'] = sponsor_summary['avg_enrollment'].round(0)
sponsor_summary = sponsor_summary.sort_values('termination_rate_%', ascending=False)

print(sponsor_summary[[
    'agency_class', 'total', 'terminated', 'termination_rate_%', 'avg_enrollment'
]].to_string(index=False))

# Termination by phase bar chart
fig_phase = px.bar(
    phase_summary,
    x='phase',
    y='termination_rate_%',
    color='termination_rate_%',
    color_continuous_scale='Blues',
    text='termination_rate_%',
    title='Termination Rate by Trial Phase',
    labels={'termination_rate_%': 'Termination Rate (%)', 'phase': 'Trial Phase'}
)
fig_phase.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
fig_phase.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13), height=450, showlegend=False
)
fig_phase.write_html(os.path.join(REPORTS, "02_termination_by_phase.html"))
print(f"\nSaved: 02_termination_by_phase.html")

# Termination by sponsor bar chart
fig_sponsor = px.bar(
    sponsor_summary[sponsor_summary['total'] > 50],
    x='agency_class',
    y='termination_rate_%',
    color='termination_rate_%',
    color_continuous_scale='Reds',
    text='termination_rate_%',
    title='Termination Rate by Sponsor Type',
    labels={'termination_rate_%': 'Termination Rate (%)', 'agency_class': 'Sponsor Type'}
)
fig_sponsor.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
fig_sponsor.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13), height=450, showlegend=False
)
fig_sponsor.write_html(os.path.join(REPORTS, "03_termination_by_sponsor.html"))
print(f"Saved: 03_termination_by_sponsor.html")


print("\n" + "="*60)
print("  TOP WITHDRAWAL REASONS")
print("="*60)

w = withdrawals[withdrawals['nct_id'].isin(df['nct_id'])].copy()
w['reason_clean'] = w['reason'].str.strip().str.upper()
reason_summary = w.groupby('reason_clean')['count'].sum().sort_values(ascending=False).head(15)
print(reason_summary.to_string())

reason_df = reason_summary.reset_index()
reason_df.columns = ['reason', 'count']

fig_reasons = px.bar(
    reason_df,
    x='count',
    y='reason',
    orientation='h',
    title='Top 15 Withdrawal Reasons Across All Trials',
    labels={'count': 'Total Withdrawals', 'reason': 'Reason'},
    color='count',
    color_continuous_scale='Blues'
)
fig_reasons.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=12),
    height=550, yaxis={'categoryorder': 'total ascending'},
    showlegend=False
)
fig_reasons.write_html(os.path.join(REPORTS, "04_withdrawal_reasons.html"))
print(f"\nSaved: 04_withdrawal_reasons.html")


enrolled = df[df['enrollment_actual'].notna() & (df['enrollment_actual'] > 0)].copy()

fig_enroll = px.histogram(
    enrolled[enrolled['enrollment_actual'] < 1000],
    x='enrollment_actual',
    color='overall_status',
    nbins=50,
    title='Enrollment Distribution by Status (capped at 1,000)',
    labels={'enrollment_actual': 'Actual Enrollment', 'overall_status': 'Status'},
    color_discrete_map={'COMPLETED': '#1F4E79', 'TERMINATED': '#C00000'},
    barmode='overlay',
    opacity=0.7
)
fig_enroll.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13), height=450
)
fig_enroll.write_html(os.path.join(REPORTS, "05_enrollment_distribution.html"))
print(f"Saved: 05_enrollment_distribution.html")


scatter_df = df[
    df['duration_months'].notna() &
    (df['duration_months'] > 0) &
    (df['duration_months'] < 300)
].sample(min(5000, len(df)), random_state=42)

fig_scatter = px.scatter(
    scatter_df,
    x='duration_months',
    y='total_withdrawals',
    color='overall_status',
    color_discrete_map={'COMPLETED': '#1F4E79', 'TERMINATED': '#C00000'},
    opacity=0.5,
    title='Trial Duration vs Total Withdrawals (sample n=5,000)',
    labels={
        'duration_months': 'Trial Duration (months)',
        'total_withdrawals': 'Total Withdrawals',
        'overall_status': 'Status'
    }
)
fig_scatter.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13), height=500
)
fig_scatter.write_html(os.path.join(REPORTS, "06_duration_vs_withdrawals.html"))
print(f"Saved: 06_duration_vs_withdrawals.html")


print("\n" + "="*60)
print("  RESULTS POSTING COMPLIANCE BY PHASE")
print("="*60)

results_by_phase = df.groupby('phase').agg(
    total=('nct_id', 'count'),
    posted=('results_posted', 'sum')
).reset_index()
results_by_phase['compliance_%'] = (
    results_by_phase['posted'] / results_by_phase['total'] * 100
).round(1)
print(results_by_phase.to_string(index=False))


print("\n" + "="*60)
print("  SAVING MASTER FUNNEL TABLE")
print("="*60)

funnel_cols = [
    'nct_id', 'overall_status', 'is_terminated', 'phase', 'phase_numeric',
    'enrollment', 'enrollment_type', 'enrollment_actual',
    'start_date', 'completion_date', 'primary_completion_date',
    'duration_days', 'duration_months',
    'number_of_arms', 'agency_class', 'site_count', 'is_multinational',
    'total_withdrawals', 'num_primary_outcomes', 'num_outcomes_posted',
    'results_posted', 'why_stopped'
]

funnel_df = df[[c for c in funnel_cols if c in df.columns]].copy()
funnel_df.to_parquet(os.path.join(PROCESSED, "master_funnel.parquet"), index=False)
print(f"master_funnel.parquet saved  ({len(funnel_df):,} rows, {funnel_df.shape[1]} cols)")

print("\n" + "="*60)
print("  KEY INSIGHTS SUMMARY")
print("="*60)

term_rate    = df['is_terminated'].mean() * 100
comp_rate    = (1 - df['is_terminated'].mean()) * 100
results_pct  = df['results_posted'].mean() * 100
avg_dur      = df['duration_months'].median()
avg_enroll   = df['enrollment_actual'].median()
pct_reached  = df['primary_completion_date'].notna().mean() * 100

print(f"  Overall termination rate:           {term_rate:.1f}%")
print(f"  Overall completion rate:            {comp_rate:.1f}%")
print(f"  Reached primary completion date:    {pct_reached:.1f}%")
print(f"  Results posting compliance:         {results_pct:.1f}%")
print(f"  Median trial duration:              {avg_dur:.0f} months")
print(f"  Median actual enrollment:           {avg_enroll:.0f} patients")
print(f"  Phase 2 termination rate:           {phase_summary[phase_summary['phase']=='PHASE2']['termination_rate_%'].values[0]}%")
print(f"  Phase 3 termination rate:           {phase_summary[phase_summary['phase']=='PHASE3']['termination_rate_%'].values[0]}%")
print(f"  Highest sponsor termination rate:   INDIV at {sponsor_summary.iloc[0]['termination_rate_%']}%")

print("\n" + "="*60)
print("  PHASE 2 COMPLETE")
print(f"  6 charts saved to: reports/eda/")
print(f"  master_funnel.parquet saved to: data/processed/")
print("="*60)