
-- CTE 1: BASE COHORT
-- Filter to interventional Phase 2/3 trials that are completed or terminated

WITH base_cohort AS (
    SELECT
        s.nct_id,
        s.overall_status,
        s.phase,
        s.enrollment,
        s.enrollment_type,
        s.study_type,
        s.start_date,
        s.completion_date,
        s.primary_completion_date,
        s.results_first_submitted_date,
        s.number_of_arms,
        s.why_stopped,
        CASE
            WHEN s.overall_status = 'TERMINATED' THEN 1
            ELSE 0
        END AS is_terminated,
        CASE
            WHEN s.phase = 'PHASE2'        THEN 2
            WHEN s.phase = 'PHASE2/PHASE3' THEN 2.5
            WHEN s.phase = 'PHASE3'        THEN 3
        END AS phase_numeric
    FROM ctgov.studies s
    WHERE
        s.study_type     = 'INTERVENTIONAL'
        AND s.phase      IN ('PHASE2', 'PHASE2/PHASE3', 'PHASE3')
        AND s.overall_status IN ('COMPLETED', 'TERMINATED')
),

-- CTE 2: LEAD SPONSOR
-- Get the lead sponsor agency class for each trial.
-- PostgreSQL note: DISTINCT ON is the Postgres-native way to deduplicate
-- to one row per nct_id (equivalent to QUALIFY in Snowflake or a
-- ROW_NUMBER() subquery in T-SQL).


lead_sponsor AS (
    SELECT DISTINCT ON (nct_id)
        nct_id,
        agency_class,
        name AS sponsor_name
    FROM ctgov.sponsors
    WHERE lead_or_collaborator = 'lead'
    ORDER BY nct_id
),

-- CTE 3: SITE COUNTS
-- Aggregate facility data to get site count and multinational flag per trial

site_summary AS (
    SELECT
        nct_id,
        COUNT(*)                              AS site_count,
        COUNT(DISTINCT country)               AS country_count,
        CASE
            WHEN COUNT(DISTINCT country) > 1 THEN 1
            ELSE 0
        END                                   AS is_multinational
    FROM ctgov.facilities
    GROUP BY nct_id
),

-- CTE 4: WITHDRAWAL SUMMARY
-- Total withdrawals per trial

withdrawal_summary AS (
    SELECT
        nct_id,
        SUM(count)                            AS total_withdrawals,
        COUNT(DISTINCT reason)                AS distinct_withdrawal_reasons
    FROM ctgov.drop_withdrawals
    GROUP BY nct_id
),

-- CTE 5: OUTCOME SUMMARY
-- Count primary outcomes and flag if any outcomes were recorded

outcome_summary AS (
    SELECT
        nct_id,
        COUNT(*)                                                   AS total_outcomes,
        SUM(CASE WHEN outcome_type = 'PRIMARY' THEN 1 ELSE 0 END)  AS num_primary_outcomes,
        CASE
            WHEN COUNT(*) > 0 THEN 1
            ELSE 0
        END                                                        AS has_outcomes_posted
    FROM ctgov.outcomes
    GROUP BY nct_id
),

-- CTE 6: MASTER TRIAL TABLE
-- Join all CTEs into one flat table with all features.
-- PostgreSQL note: date subtraction (date - date) returns an integer number
-- of days directly - no DATEDIFF() function needed or available in Postgres.

master_trial AS (
    SELECT
        b.nct_id,
        b.overall_status,
        b.is_terminated,
        b.phase,
        b.phase_numeric,
        b.enrollment,
        b.enrollment_type,
        CASE
            WHEN b.enrollment_type = 'ACTUAL' THEN b.enrollment
            ELSE NULL
        END                                                   AS enrollment_actual,
        b.start_date,
        b.completion_date,
        b.primary_completion_date,
        b.results_first_submitted_date,
        CASE
            WHEN b.results_first_submitted_date IS NOT NULL THEN 1
            ELSE 0
        END                                                   AS results_posted,
        b.number_of_arms,
        b.why_stopped,
        ls.agency_class,
        ls.sponsor_name,
        COALESCE(ss.site_count, 1)                           AS site_count,
        COALESCE(ss.country_count, 1)                        AS country_count,
        COALESCE(ss.is_multinational, 0)                     AS is_multinational,
        COALESCE(ws.total_withdrawals, 0)                    AS total_withdrawals,
        COALESCE(ws.distinct_withdrawal_reasons, 0)          AS distinct_withdrawal_reasons,
        COALESCE(os.num_primary_outcomes, 0)                 AS num_primary_outcomes,
        COALESCE(os.has_outcomes_posted, 0)                  AS has_outcomes_posted,
        -- Duration in days: Postgres date subtraction returns an integer directly
        (b.completion_date - b.start_date)                    AS duration_days,
        ROUND(
            (b.completion_date - b.start_date) / 30.44
        , 1)                                                  AS duration_months
    FROM base_cohort b
    LEFT JOIN lead_sponsor      ls ON b.nct_id = ls.nct_id
    LEFT JOIN site_summary      ss ON b.nct_id = ss.nct_id
    LEFT JOIN withdrawal_summary ws ON b.nct_id = ws.nct_id
    LEFT JOIN outcome_summary   os ON b.nct_id = os.nct_id
),

-- CTE 7: FUNNEL STAGES
-- Build the 5-stage funnel with counts at each stage


funnel_stages AS (
    SELECT
        COUNT(*)                                                          AS stage1_registered,
        SUM(CASE WHEN enrollment_actual IS NOT NULL THEN 1 ELSE 0 END)    AS stage2_enrollment_recorded,
        SUM(CASE WHEN primary_completion_date IS NOT NULL THEN 1 ELSE 0 END)
                                                                          AS stage3_primary_completion,
        SUM(CASE WHEN overall_status = 'COMPLETED' THEN 1 ELSE 0 END)    AS stage4_completed,
        SUM(results_posted)                                               AS stage5_results_posted
    FROM master_trial
),

-- CTE 8: FUNNEL WITH CONVERSION RATES

funnel_with_rates AS (
    SELECT
        stage1_registered,
        stage2_enrollment_recorded,
        stage3_primary_completion,
        stage4_completed,
        stage5_results_posted,
        ROUND(stage2_enrollment_recorded * 100.0 / NULLIF(stage1_registered, 0), 1)
                                                              AS stage2_pct_of_total,
        ROUND(stage3_primary_completion  * 100.0 / NULLIF(stage1_registered, 0), 1)
                                                              AS stage3_pct_of_total,
        ROUND(stage4_completed           * 100.0 / NULLIF(stage1_registered, 0), 1)
                                                              AS stage4_pct_of_total,
        ROUND(stage5_results_posted      * 100.0 / NULLIF(stage1_registered, 0), 1)
                                                              AS stage5_pct_of_total,
        stage1_registered - stage2_enrollment_recorded        AS drop_stage1_to_2,
        stage2_enrollment_recorded - stage3_primary_completion AS drop_stage2_to_3,
        stage3_primary_completion  - stage4_completed         AS drop_stage3_to_4,
        stage4_completed           - stage5_results_posted    AS drop_stage4_to_5
    FROM funnel_stages
),

-- CTE 9: SEGMENTATION BY PHASE

phase_segmentation AS (
    SELECT
        phase,
        COUNT(*)                                              AS total_trials,
        SUM(is_terminated)                                    AS terminated,
        SUM(CASE WHEN overall_status = 'COMPLETED' THEN 1 ELSE 0 END)
                                                              AS completed,
        SUM(results_posted)                                   AS results_posted,
        ROUND(SUM(is_terminated) * 100.0 / NULLIF(COUNT(*), 0), 1)
                                                              AS termination_rate_pct,
        ROUND(SUM(results_posted) * 100.0 / NULLIF(COUNT(*), 0), 1)
                                                              AS results_compliance_pct,
        ROUND(AVG(enrollment_actual), 0)                      AS avg_actual_enrollment,
        ROUND(AVG(duration_months), 1)                        AS avg_duration_months,
        ROUND(AVG(total_withdrawals), 1)                      AS avg_withdrawals
    FROM master_trial
    GROUP BY phase
    ORDER BY MIN(phase_numeric)
),

-- CTE 10: SEGMENTATION BY SPONSOR TYPE

sponsor_segmentation AS (
    SELECT
        agency_class,
        COUNT(*)                                              AS total_trials,
        SUM(is_terminated)                                    AS terminated,
        ROUND(SUM(is_terminated) * 100.0 / NULLIF(COUNT(*), 0), 1)
                                                              AS termination_rate_pct,
        ROUND(AVG(enrollment_actual), 0)                      AS avg_actual_enrollment,
        ROUND(AVG(duration_months), 1)                        AS avg_duration_months
    FROM master_trial
    WHERE agency_class IS NOT NULL
    GROUP BY agency_class
    ORDER BY termination_rate_pct DESC
),

-- CTE 11: TOP WITHDRAWAL REASONS

withdrawal_reasons AS (
    SELECT
        UPPER(TRIM(dw.reason))                                AS withdrawal_reason,
        SUM(dw.count)                                         AS total_count,
        COUNT(DISTINCT dw.nct_id)                             AS trials_affected
    FROM ctgov.drop_withdrawals dw
    INNER JOIN base_cohort bc ON dw.nct_id = bc.nct_id
    WHERE dw.reason IS NOT NULL
    GROUP BY UPPER(TRIM(dw.reason))
    ORDER BY total_count DESC
    LIMIT 15
),

-- CTE 12: HIGH RISK TRIALS
-- Top 50 highest-risk trials for stakeholder review

high_risk_trials AS (
    SELECT
        nct_id,
        overall_status,
        phase,
        agency_class,
        enrollment_actual,
        duration_months,
        total_withdrawals,
        has_outcomes_posted,
        results_posted,
        why_stopped,
        (
            is_terminated * 3
            + (1 - results_posted) * 2
            + CASE WHEN total_withdrawals > 100 THEN 1 ELSE 0 END
        )                                                     AS risk_flag_score
    FROM master_trial
    ORDER BY risk_flag_score DESC, total_withdrawals DESC
    LIMIT 50
)

-- OUTPUT 1: Full master trial table (use for Power BI / Excel import)
SELECT * FROM master_trial;

-- OUTPUT 2: Funnel overview
-- SELECT * FROM funnel_with_rates;

-- OUTPUT 3: Phase segmentation
-- SELECT * FROM phase_segmentation;

-- OUTPUT 4: Sponsor segmentation
-- SELECT * FROM sponsor_segmentation;

-- OUTPUT 5: Top withdrawal reasons
-- SELECT * FROM withdrawal_reasons;

-- OUTPUT 6: High risk trials
-- SELECT * FROM high_risk_trials;