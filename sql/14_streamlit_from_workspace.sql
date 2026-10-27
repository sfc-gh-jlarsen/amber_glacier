-- Streamlit app on the container runtime (SPCS compute pool), sourced from the Workspace so
-- "Edit" in Snowsight opens the Workspace. Re-run after changing settings; code edits happen in the Workspace.
-- Replace <YOUR_USER> with your Snowflake user name (personal workspaces live in the USER$<name> schema).
CREATE WORKSPACE IF NOT EXISTS USER$<YOUR_USER>.PUBLIC."Office Hours 20261027";
-- Upload once from a laptop:
--   cortex ws cp ./"Dispute AI - Haiku vs Sonnet"/* 'USER$<YOUR_USER>.PUBLIC."Office Hours 20261027":/streamlit/'
CREATE OR REPLACE STREAMLIT OFFICEHOURS_20261027.STREAMLITS.DISPUTE_AI_COMPARE
  FROM 'snow://workspace/USER$<YOUR_USER>.PUBLIC."Office Hours 20261027"/versions/live/streamlit'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = OFFICEHOURS_WH                      -- runs the app's SQL only
  RUNTIME_NAME = 'SYSTEM$ST_CONTAINER_RUNTIME_PY3_11'   -- app code runs in SPCS
  COMPUTE_POOL = SYSTEM_COMPUTE_POOL_CPU
  TITLE = 'Dispute AI - Haiku vs Sonnet';
ALTER STREAMLIT OFFICEHOURS_20261027.STREAMLITS.DISPUTE_AI_COMPARE ADD LIVE VERSION FROM LAST;
