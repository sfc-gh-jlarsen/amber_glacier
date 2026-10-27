-- Step 1 of the AI loop: bulk AI_COMPLETE inference with structured output, for any model / prompt version.
USE SCHEMA OFFICEHOURS_20261027.SAP_FINANCIALS;
USE WAREHOUSE OFFICEHOURS_WH;

-- 2,000 inbound dispute emails with ground truth (fixed sample so every model sees the same rows)
CREATE OR REPLACE TABLE AI_EVAL_SET AS
SELECT n.NOTE_ID, n.NOTE_TEXT, l.REASON_CODE, l.ROUTE_TO, l.INVOICE_REF, l.DISPUTED_AMOUNT, l.IS_HARD, l.HARD_TYPE
FROM UDM_DISPUTE_NOTES n JOIN DISPUTE_NOTE_LABELS l USING (NOTE_ID)
WHERE n.NOTE_TYPE = 'EMAIL_IN'
ORDER BY HASH(n.NOTE_ID, 20261027)
LIMIT 2000;

CREATE TABLE IF NOT EXISTS PROMPT_LIBRARY (PROMPT_VERSION VARCHAR, CREATED_AT TIMESTAMP_NTZ, NOTES VARCHAR, PROMPT VARCHAR);

MERGE INTO PROMPT_LIBRARY t USING (SELECT 'v1_baseline' AS PROMPT_VERSION, $$You are an accounts receivable dispute analyst. Read the customer correspondence below and classify the dispute.

Reason codes:
- PRICING: invoiced price differs from contract/PO price
- PROMO_DEDUCTION: customer deducted for a promotion, rebate, trade allowance, co-op or MDF
- SHORT_SHIPMENT: fewer goods received than invoiced
- DAMAGED_GOODS: goods arrived damaged
- DUPLICATE_BILLING: customer was invoiced twice for the same delivery
- MISSING_POD: customer asks for proof of delivery
- TAX_EXEMPT: tax charged to an exempt customer
- ALREADY_PAID: customer says the invoice is already paid
- QUALITY: goods do not meet specification
- OTHER: anything else (address changes, missing invoice copy, etc.)

Route to: SALES (PRICING, PROMO_DEDUCTION), LOGISTICS (SHORT_SHIPMENT, DAMAGED_GOODS, MISSING_POD, QUALITY), BILLING (DUPLICATE_BILLING, TAX_EXEMPT), COLLECTIONS (ALREADY_PAID, OTHER).
Extract the invoice number referenced (or null) and the disputed amount as a number (or null).$$ AS PROMPT) s
ON t.PROMPT_VERSION = s.PROMPT_VERSION
WHEN NOT MATCHED THEN INSERT VALUES (s.PROMPT_VERSION, CURRENT_TIMESTAMP(), 'Baseline: definitions only', s.PROMPT);

CREATE TABLE IF NOT EXISTS DISPUTE_CLASSIFICATION_RUNS (
  RUN_ID VARCHAR, MODEL VARCHAR, PROMPT_VERSION VARCHAR, NOTE_ID VARCHAR, RESULT VARIANT,
  REASON_CODE VARCHAR, ROUTE_TO VARCHAR, INVOICE_REF VARCHAR, DISPUTED_AMOUNT FLOAT, CONFIDENCE FLOAT,
  PROMPT_TOKENS NUMBER, COMPLETION_TOKENS NUMBER, RUN_TS TIMESTAMP_NTZ
);

-- Runs one model over the first N rows of AI_EVAL_SET. Model must be a literal in AI_COMPLETE,
-- so the statement is built dynamically; the model is checked against an allowlist first.
CREATE OR REPLACE PROCEDURE SP_RUN_CLASSIFIER(MODEL VARCHAR, PROMPT_VERSION VARCHAR, N NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  run_id VARCHAR DEFAULT :MODEL || '|' || :PROMPT_VERSION || '|' || TO_VARCHAR(CURRENT_TIMESTAMP(), 'YYYYMMDDHH24MISS');
  stmt VARCHAR;
BEGIN
  IF (:MODEL NOT IN ('claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-sonnet-4-5', 'claude-opus-4-5',
                     'openai-gpt-5-nano', 'openai-gpt-5-mini', 'llama4-maverick')) THEN
    RETURN 'Model not in allowlist: ' || :MODEL;
  END IF;
  stmt := '
  INSERT INTO DISPUTE_CLASSIFICATION_RUNS
  WITH src AS (SELECT * FROM AI_EVAL_SET ORDER BY HASH(NOTE_ID, 20261027) LIMIT ' || :N || '),
  p AS (SELECT PROMPT FROM PROMPT_LIBRARY WHERE PROMPT_VERSION = ?),
  r AS (
    SELECT src.NOTE_ID, AI_COMPLETE(
      model => ''' || :MODEL || ''',
      prompt => p.PROMPT || ''\n\nCORRESPONDENCE:\n'' || src.NOTE_TEXT,
      model_parameters => {''temperature'': 0, ''max_tokens'': 300},
      response_format => {''type'': ''json'', ''schema'': {''type'': ''object'', ''properties'': {
        ''reason_code'': {''type'': ''string'', ''enum'': [''PRICING'',''PROMO_DEDUCTION'',''SHORT_SHIPMENT'',''DAMAGED_GOODS'',''DUPLICATE_BILLING'',''MISSING_POD'',''TAX_EXEMPT'',''ALREADY_PAID'',''QUALITY'',''OTHER'']},
        ''route_to'': {''type'': ''string'', ''enum'': [''SALES'',''LOGISTICS'',''BILLING'',''COLLECTIONS'']},
        ''invoice_ref'': {''type'': [''string'', ''null'']},
        ''disputed_amount'': {''type'': [''number'', ''null'']},
        ''confidence'': {''type'': ''number''}},
        ''required'': [''reason_code'', ''route_to'', ''invoice_ref'', ''disputed_amount'', ''confidence'']}},
      show_details => TRUE) AS D
    FROM src, p)
  SELECT ?, ''' || :MODEL || ''', ?, NOTE_ID, D:structured_output[0]:raw_message,
         D:structured_output[0]:raw_message:reason_code::VARCHAR, D:structured_output[0]:raw_message:route_to::VARCHAR,
         D:structured_output[0]:raw_message:invoice_ref::VARCHAR, D:structured_output[0]:raw_message:disputed_amount::FLOAT,
         D:structured_output[0]:raw_message:confidence::FLOAT,
         D:usage:prompt_tokens::NUMBER, D:usage:completion_tokens::NUMBER, CURRENT_TIMESTAMP()
  FROM r';
  EXECUTE IMMEDIATE :stmt USING (PROMPT_VERSION, run_id, PROMPT_VERSION);
  RETURN run_id;
END;
$$;

-- Accuracy per run (exact match on reason code is the headline metric)
CREATE OR REPLACE VIEW V_CLASSIFIER_ACCURACY AS
SELECT r.RUN_ID, r.MODEL, r.PROMPT_VERSION, COUNT(*) AS N,
       AVG(IFF(r.REASON_CODE = e.REASON_CODE, 1, 0)) AS REASON_ACC,
       AVG(IFF(r.ROUTE_TO = e.ROUTE_TO, 1, 0)) AS ROUTE_ACC,
       AVG(IFF(EQUAL_NULL(r.INVOICE_REF, e.INVOICE_REF), 1, 0)) AS INVOICE_ACC,
       AVG(IFF(e.DISPUTED_AMOUNT IS NULL OR ABS(r.DISPUTED_AMOUNT - e.DISPUTED_AMOUNT) < 1, 1, 0)) AS AMOUNT_ACC,
       AVG(IFF(e.IS_HARD, IFF(r.REASON_CODE = e.REASON_CODE, 1, 0), NULL)) AS HARD_ACC,
       AVG(IFF(NOT e.IS_HARD, IFF(r.REASON_CODE = e.REASON_CODE, 1, 0), NULL)) AS EASY_ACC,
       SUM(r.PROMPT_TOKENS) AS PROMPT_TOKENS, SUM(r.COMPLETION_TOKENS) AS COMPLETION_TOKENS,
       MIN(r.RUN_TS) AS RUN_TS
FROM DISPUTE_CLASSIFICATION_RUNS r JOIN AI_EVAL_SET e USING (NOTE_ID)
GROUP BY ALL;
