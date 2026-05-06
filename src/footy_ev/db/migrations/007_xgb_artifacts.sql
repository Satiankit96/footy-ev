-- =========================================================================
-- Migration 007: XGBoost fit artifacts and per-fold feature importances.
--
-- xgb_fits stores one row per walk-forward fold fit (booster JSON + params).
-- xgb_feature_importances stores per-feature audit results (gain importance +
-- permutation importance vs null CI from the audit_noise canary).
--
-- Both tables are idempotent (CREATE TABLE IF NOT EXISTS).
-- =========================================================================

CREATE TABLE IF NOT EXISTS xgb_fits (
    fit_id              VARCHAR PRIMARY KEY,
    league              VARCHAR NOT NULL,
    as_of               TIMESTAMP NOT NULL,
    model_version       VARCHAR NOT NULL,
    xg_skellam_run_id   VARCHAR NOT NULL,
    n_train             INTEGER NOT NULL,
    n_estimators        INTEGER NOT NULL,
    max_depth           INTEGER NOT NULL,
    learning_rate       DOUBLE NOT NULL,
    feature_names       VARCHAR[] NOT NULL,
    booster_json        VARCHAR NOT NULL,
    train_log_loss      DOUBLE,
    fitted_at           TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS xgb_feature_importances (
    fit_id                 VARCHAR NOT NULL,
    feature_name           VARCHAR NOT NULL,
    importance_gain        DOUBLE NOT NULL,
    permutation_importance DOUBLE,
    perm_ci_low            DOUBLE,
    perm_ci_high           DOUBLE,
    below_null_baseline    BOOLEAN,
    PRIMARY KEY (fit_id, feature_name)
);
