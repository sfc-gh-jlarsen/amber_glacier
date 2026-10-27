-- Step 3 of the AI loop: Optimize with AI Function Studio (GEPA prompt/body optimization across models)
USE SCHEMA OFFICEHOURS_20261027.SAP_FINANCIALS;
USE WAREHOUSE OFFICEHOURS_WH;

DROP EXPERIMENT IF EXISTS CLASSIFY_DISPUTE_OPT_EXP;
CREATE EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP
  TYPE = 'AI_FUNCTION_OPTIMIZATION'
  FROM SPECIFICATION $$
    function:
      function_name: OFFICEHOURS_20261027.SAP_FINANCIALS.CLASSIFY_DISPUTE
    metrics:
      - name: exact_match
    dataset:
      name: OFFICEHOURS_20261027.SAP_FINANCIALS.DISPUTE_TRAIN_DS
      version: v1
      column_mapping:
        argument_mapping:
          NOTE_TEXT: NOTE_TEXT
        ground_truth: REASON_CODE
      holdout_data: OFFICEHOURS_20261027.SAP_FINANCIALS.DISPUTE_HOLDOUT_DS
      holdout_version: v1
    optimization:
      models: [claude-haiku-4-5, claude-sonnet-4-6]
      reflection_model: claude-opus-4-7
      strategy: quality_first
      budget: light
      algorithm: GEPA
  $$;
EXECUTE EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP;

-- Monitor:   SHOW RUNS IN EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP;
-- Winner:    SHOW RUN METRICS IN EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP RUN ITER_n;
-- Deploy the chosen run (step 4: the optimized AI Function):
--   CREATE OR REPLACE AI FUNCTION CLASSIFY_DISPUTE(NOTE_TEXT VARCHAR) RETURNS VARCHAR
--     FROM EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP RUN ITER_n;

-- Executed after the run finished: frontier = SEED (93.0%), ITER_4 (97.3%, 1.32x), ITER_9 (100%, 1.54x), all Haiku.
-- Keep the seed for comparison, then deploy the winner.
CREATE OR REPLACE AI FUNCTION CLASSIFY_DISPUTE(NOTE_TEXT VARCHAR)
RETURNS VARCHAR
COMMENT = 'Classify an AR dispute email into a Northwind SAP dispute reason code (optimized: CLASSIFY_DISPUTE_OPT_EXP ITER_9)'
FROM EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP RUN ITER_9;
