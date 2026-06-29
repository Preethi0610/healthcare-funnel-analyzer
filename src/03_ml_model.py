
import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    roc_auc_score, f1_score, classification_report,
    confusion_matrix, roc_curve, precision_recall_curve, average_precision_score
)
from sklearn.impute import SimpleImputer
import xgboost as xgb
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import joblib


PROCESSED = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/data/processed")
REPORTS   = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/reports/shap")
MODELS    = os.path.expanduser("~/Downloads/healthcare-funnel-analyzer/models")
os.makedirs(REPORTS, exist_ok=True)
os.makedirs(MODELS, exist_ok=True)


print("\n" + "="*60)
print("  LOADING MASTER FUNNEL TABLE")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED, "master_funnel.parquet"))
print(f"Loaded: {len(df):,} trials, {df.shape[1]} columns")
print(f"Target balance: {df['is_terminated'].value_counts().to_dict()}")

print("\n" + "="*60)
print("  FEATURE ENGINEERING FOR ML")
print("="*60)

ml = df.copy()

# --- Encode sponsor type ---
agency_map = {
    'INDUSTRY':  0,
    'NIH':       1,
    'OTHER_GOV': 2,
    'NETWORK':   3,
    'OTHER':     4,
    'FED':       5,
    'INDIV':     6,
    'UNKNOWN':   7
}
ml['sponsor_encoded'] = ml['agency_class'].map(agency_map).fillna(4)

# --- Enrollment type binary flag ---
ml['is_actual_enrollment'] = (ml['enrollment_type'] == 'ACTUAL').astype(int)

# --- Log-transform enrollment (heavy right skew) ---
ml['log_enrollment'] = np.log1p(ml['enrollment'].fillna(0))

# --- Log-transform withdrawals ---
ml['log_withdrawals'] = np.log1p(ml['total_withdrawals'])

# --- Multi-site flag ---
ml['is_multinational'] = ml['is_multinational'].fillna(0).astype(int)
ml['site_count']       = ml['site_count'].fillna(1)
ml['log_site_count']   = np.log1p(ml['site_count'])

# --- Number of arms ---
ml['number_of_arms'] = ml['number_of_arms'].fillna(ml['number_of_arms'].median())

# --- Duration ---
ml['duration_months'] = ml['duration_months'].fillna(ml['duration_months'].median())

# --- Outcomes ---
ml['num_primary_outcomes'] = ml['num_primary_outcomes'].fillna(0)
ml['num_outcomes_posted']  = ml['num_outcomes_posted'].fillna(0)
ml['has_outcomes_posted']  = (ml['num_outcomes_posted'] > 0).astype(int)

# --- Phase already numeric ---
ml['phase_numeric'] = ml['phase_numeric'].fillna(2)

# Final feature list
FEATURES = [
    'phase_numeric',
    'log_enrollment',
    'is_actual_enrollment',
    'duration_months',
    'number_of_arms',
    'sponsor_encoded',
    'log_site_count',
    'is_multinational',
    'log_withdrawals',
    'num_primary_outcomes',
    'has_outcomes_posted',
]

TARGET = 'is_terminated'

X = ml[FEATURES].copy()
y = ml[TARGET].copy()

print(f"Features: {FEATURES}")
print(f"\nFeature matrix shape: {X.shape}")
print(f"Target distribution:")
print(f"  Completed  (0): {(y==0).sum():,} ({(y==0).mean()*100:.1f}%)")
print(f"  Terminated (1): {(y==1).sum():,} ({(y==1).mean()*100:.1f}%)")

print("\n" + "="*60)
print("  TRAIN / TEST SPLIT")
print("="*60)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"Train size: {len(X_train):,}")
print(f"Test size:  {len(X_test):,}")

# Impute any remaining nulls
imputer = SimpleImputer(strategy='median')
X_train = pd.DataFrame(imputer.fit_transform(X_train), columns=FEATURES)
X_test  = pd.DataFrame(imputer.transform(X_test),      columns=FEATURES)

print("\n" + "="*60)
print("  MODEL 1 - LOGISTIC REGRESSION (BASELINE)")
print("="*60)

lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
lr.fit(X_train, y_train)
lr_proba = lr.predict_proba(X_test)[:, 1]
lr_pred  = lr.predict(X_test)

lr_auc = roc_auc_score(y_test, lr_proba)
lr_f1  = f1_score(y_test, lr_pred, average='macro')
lr_ap  = average_precision_score(y_test, lr_proba)

print(f"ROC-AUC:             {lr_auc:.4f}")
print(f"F1 (macro):          {lr_f1:.4f}")
print(f"Avg Precision:       {lr_ap:.4f}")


print("\n" + "="*60)
print("  MODEL 2 - RANDOM FOREST")
print("="*60)

rf = RandomForestClassifier(
    n_estimators=200,
    max_depth=8,
    min_samples_leaf=20,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1
)
rf.fit(X_train, y_train)
rf_proba = rf.predict_proba(X_test)[:, 1]
rf_pred  = rf.predict(X_test)

rf_auc = roc_auc_score(y_test, rf_proba)
rf_f1  = f1_score(y_test, rf_pred, average='macro')
rf_ap  = average_precision_score(y_test, rf_proba)

print(f"ROC-AUC:             {rf_auc:.4f}")
print(f"F1 (macro):          {rf_f1:.4f}")
print(f"Avg Precision:       {rf_ap:.4f}")


print("\n" + "="*60)
print("  MODEL 3 - XGBOOST")
print("="*60)

scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()

xgb_model = xgb.XGBClassifier(
    n_estimators=300,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=scale_pos_weight,
    eval_metric='auc',
    random_state=42,
    verbosity=0
)
xgb_model.fit(
    X_train, y_train,
    eval_set=[(X_test, y_test)],
    verbose=False
)
xgb_proba = xgb_model.predict_proba(X_test)[:, 1]
xgb_pred  = xgb_model.predict(X_test)

xgb_auc = roc_auc_score(y_test, xgb_proba)
xgb_f1  = f1_score(y_test, xgb_pred, average='macro')
xgb_ap  = average_precision_score(y_test, xgb_proba)

print(f"ROC-AUC:             {xgb_auc:.4f}")
print(f"F1 (macro):          {xgb_f1:.4f}")
print(f"Avg Precision:       {xgb_ap:.4f}")


print("\n" + "="*60)
print("  MODEL COMPARISON")
print("="*60)

comparison = pd.DataFrame({
    'Model':         ['Logistic Regression', 'Random Forest', 'XGBoost'],
    'ROC-AUC':       [lr_auc, rf_auc, xgb_auc],
    'F1 (macro)':    [lr_f1,  rf_f1,  xgb_f1],
    'Avg Precision': [lr_ap,  rf_ap,  xgb_ap]
})
comparison[['ROC-AUC', 'F1 (macro)', 'Avg Precision']] = comparison[['ROC-AUC', 'F1 (macro)', 'Avg Precision']].round(4)

print(comparison.to_string(index=False))

best_model     = xgb_model
best_proba     = xgb_proba
best_pred      = xgb_pred
best_model_name = 'XGBoost'
print(f"\nBest model: {best_model_name} (ROC-AUC: {xgb_auc:.4f})")


print("\n" + "="*60)
print(f"  CLASSIFICATION REPORT - {best_model_name}")
print("="*60)
print(classification_report(y_test, best_pred, target_names=['Completed', 'Terminated']))

fig_roc = go.Figure()

for name, proba, color in [
    ('Logistic Regression', lr_proba,  '#A8D5F5'),
    ('Random Forest',       rf_proba,  '#2E75B6'),
    ('XGBoost',             xgb_proba, '#C00000'),
]:
    fpr, tpr, _ = roc_curve(y_test, proba)
    auc_val = roc_auc_score(y_test, proba)
    fig_roc.add_trace(go.Scatter(
        x=fpr, y=tpr,
        name=f"{name} (AUC={auc_val:.3f})",
        line=dict(color=color, width=2)
    ))

fig_roc.add_trace(go.Scatter(
    x=[0,1], y=[0,1],
    name='Random Baseline',
    line=dict(color='grey', width=1, dash='dash')
))

fig_roc.update_layout(
    title='ROC Curves - All Models',
    xaxis_title='False Positive Rate',
    yaxis_title='True Positive Rate',
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13),
    height=500
)
fig_roc.write_html(os.path.join(REPORTS, "01_roc_curves.html"))
print(f"\nSaved: 01_roc_curves.html")


print("\n" + "="*60)
print("  FEATURE IMPORTANCE - XGBOOST")
print("="*60)

importance_df = pd.DataFrame({
    'feature':    FEATURES,
    'importance': xgb_model.feature_importances_
}).sort_values('importance', ascending=False)

print(importance_df.to_string(index=False))

fig_importance = px.bar(
    importance_df,
    x='importance',
    y='feature',
    orientation='h',
    title='XGBoost Feature Importance (Gain)',
    labels={'importance': 'Importance Score', 'feature': 'Feature'},
    color='importance',
    color_continuous_scale='Blues'
)
fig_importance.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13),
    height=500,
    yaxis={'categoryorder': 'total ascending'},
    showlegend=False
)
fig_importance.write_html(os.path.join(REPORTS, "02_feature_importance.html"))
print(f"\nSaved: 02_feature_importance.html")

risk_df = X_test.copy()
risk_df['risk_score']    = xgb_proba
risk_df['actual_status'] = y_test.values
risk_df['risk_band'] = pd.cut(
    risk_df['risk_score'],
    bins=[0, 0.25, 0.50, 0.75, 1.0],
    labels=['Low (0-25%)', 'Medium (25-50%)', 'High (50-75%)', 'Very High (75-100%)']
)

print("\n" + "="*60)
print("  RISK BAND DISTRIBUTION")
print("="*60)

risk_band_summary = risk_df.groupby('risk_band', observed=True).agg(
    count=('risk_score', 'count'),
    actual_terminated=('actual_status', 'sum')
).reset_index()
risk_band_summary['termination_rate_%'] = (
    risk_band_summary['actual_terminated'] / risk_band_summary['count'] * 100
).round(1)
print(risk_band_summary.to_string(index=False))

fig_risk = px.histogram(
    risk_df,
    x='risk_score',
    color='actual_status',
    nbins=50,
    title='Risk Score Distribution by Actual Outcome',
    labels={'risk_score': 'Predicted Risk Score', 'actual_status': 'Actual (1=Terminated)'},
    color_discrete_map={0: '#1F4E79', 1: '#C00000'},
    barmode='overlay',
    opacity=0.7
)
fig_risk.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='Arial', size=13), height=450
)
fig_risk.write_html(os.path.join(REPORTS, "03_risk_score_distribution.html"))
print(f"\nSaved: 03_risk_score_distribution.html")

print("\n" + "="*60)
print("  SAVING MODEL AND OUTPUTS")
print("="*60)

# Save model and imputer
joblib.dump(xgb_model, os.path.join(MODELS, "risk_classifier_xgb.pkl"))
joblib.dump(imputer,   os.path.join(MODELS, "imputer.pkl"))
print(f"Saved: models/risk_classifier_xgb.pkl")
print(f"Saved: models/imputer.pkl")

# Save full risk scores for Power BI
full_features = pd.DataFrame(imputer.transform(ml[FEATURES]), columns=FEATURES)
ml['risk_score'] = xgb_model.predict_proba(full_features)[:, 1]
ml['risk_band']  = pd.cut(
    ml['risk_score'],
    bins=[0, 0.25, 0.50, 0.75, 1.0],
    labels=['Low', 'Medium', 'High', 'Very High']
)

risk_output = ml[[
    'nct_id', 'overall_status', 'is_terminated', 'phase',
    'agency_class', 'enrollment', 'duration_months',
    'site_count', 'total_withdrawals', 'risk_score', 'risk_band'
]].copy()

risk_output.to_parquet(os.path.join(PROCESSED, "risk_scores.parquet"), index=False)
risk_output.to_csv(os.path.join(PROCESSED,     "risk_scores.csv"),     index=False)
print(f"Saved: data/processed/risk_scores.parquet")
print(f"Saved: data/processed/risk_scores.csv  ({len(risk_output):,} rows)")

print("\n" + "="*60)
print("  FINAL MODEL SUMMARY")
print("="*60)

print(f"  Best model:               XGBoost")
print(f"  ROC-AUC:                  {xgb_auc:.4f}")
print(f"  F1 score (macro):         {xgb_f1:.4f}")
print(f"  Average precision:        {xgb_ap:.4f}")
print(f"  Training samples:         {len(X_train):,}")
print(f"  Test samples:             {len(X_test):,}")
print(f"  Features used:            {len(FEATURES)}")
print(f"  Class weight strategy:    scale_pos_weight ({scale_pos_weight:.2f})")

print("\n  Top 3 Risk Factors (by XGBoost importance):")
for i, row in importance_df.head(3).iterrows():
    print(f"    {row['feature']:<30} {row['importance']:.4f}")

print("\n" + "="*60)
print("  PHASE 3 COMPLETE")
print(f"  Charts saved to:  reports/shap/")
print(f"  Model saved to:   models/")
print(f"  Scores saved to:  data/processed/risk_scores.csv")
print("="*60)