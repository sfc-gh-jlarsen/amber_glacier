"""Generate demo/ai_function_create_evaluate_optimize.ipynb from source.

The notebook is generated, not hand-edited: change the cells here and re-run
    python utilities/build_notebook.py
so the .ipynb stays reviewable as plain Python in diffs.

Helpers: md() adds a markdown cell, sql(name, text) adds a Snowsight SQL cell whose
result is exposed to later cells as a dataframe called `name`, py() adds a Python cell.
"""
import json, os, uuid

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo", "ai_function_create_evaluate_optimize.ipynb")
cells = []


def md(s):
    cells.append({"cell_type": "markdown", "id": uuid.uuid4().hex[:8], "metadata": {}, "source": s.strip("\n").splitlines(True)})


def sql(name, s):
    cells.append({"cell_type": "code", "id": uuid.uuid4().hex[:8], "execution_count": None,
                  "metadata": {"codeCollapsed": False, "language": "sql", "name": name, "resultVariableName": name},
                  "outputs": [], "source": (f"%%sql -r {name}\n" + s.strip("\n")).splitlines(True)})


def py(s):
    cells.append({"cell_type": "code", "id": uuid.uuid4().hex[:8], "execution_count": None,
                  "metadata": {"language": "python"}, "outputs": [], "source": s.strip("\n").splitlines(True)})


md("""
# Dispute triage with AI Functions: create, evaluate, optimize

**Northwind Industrial** runs SAP S/4HANA with FSCM Dispute Management. There are 7,000+ disputes, and the reason code
in SAP is blank or wrong on most of them. The real reason is in the customer's email.

In this notebook we:
1. **Create** an AI Function that reads the email and returns a SAP dispute reason code
2. **Evaluate** it against a labeled, versioned dataset
3. **Optimize** it across Haiku and Sonnet, then pick from a cost/quality frontier
4. **Deploy** the winner with one line and compare cost

Objects created here end in `_DEMO`, so the production `CLASSIFY_DISPUTE` used by the daily automation is never touched.

**Before you run this:** build the environment once with `sql/00`-`13` and `generator/generate.py` (see the repo README).
Sections 3-5 read the pre-run optimization experiment `CLASSIFY_DISPUTE_OPT_EXP` and its winning run `ITER_9`.
Run names come from your own optimization, so update `ITER_9` below if your winner differs.
""")
sql("ctx", "USE WAREHOUSE OFFICEHOURS_WH")
sql("ctx_schema", "USE SCHEMA OFFICEHOURS_20261027.SAP_FINANCIALS")
md("""
### The problem: what SAP says today
How the processor keyed the reason code, compared with what the customer's email actually says.
""")
sql("keyed_reason", """
SELECT IFF(c.REASON IS NULL, 'Blank', IFF(c.REASON = l.REASON_CODE, 'Correct', 'Wrong')) AS KEYED_REASON,
       COUNT(*) AS DISPUTES,
       ROUND(RATIO_TO_REPORT(COUNT(*)) OVER () * 100, 1) AS PCT
FROM UDMCASEATTR00 c
JOIN UDM_DISPUTE_NOTES n ON n.EXT_KEY = c.EXT_KEY AND n.NOTE_TYPE = 'EMAIL_IN'
JOIN DISPUTE_NOTE_LABELS l ON l.NOTE_ID = n.NOTE_ID
GROUP BY 1 ORDER BY 2 DESC
""")
sql("sample_emails", "SELECT NOTE_ID, NOTE_TEXT FROM AI_EVAL_SET WHERE IS_HARD ORDER BY NOTE_ID LIMIT 5")

md("""
## 1. Create an AI Function

An **AI Function** is a governed SQL object: model + prompt + typed output, behind one function call.
Analysts call it like any other function, and you can grant it, version it and audit it.

The body is `AI_COMPLETE` with a **`response_format` JSON schema**, so the output is structured and needs no free-text parsing.
We start on **claude-haiku-4-5**, the cheapest capable model.
""")
sql("create_fn", """
CREATE OR REPLACE AI FUNCTION CLASSIFY_DISPUTE_DEMO(NOTE_TEXT VARCHAR)
RETURNS VARCHAR
COMMENT = 'Office hours demo: classify an AR dispute email into a SAP dispute reason code'
AS
$$
SELECT AI_COMPLETE(
  model => 'claude-haiku-4-5',
  messages => ARRAY_CONSTRUCT(
    OBJECT_CONSTRUCT('role', 'system', 'content',
      'You are an accounts receivable dispute analyst. Read the customer correspondence and classify the primary dispute reason. '
      || 'Reason codes: PRICING (invoiced price differs from contract/PO price); PROMO_DEDUCTION (customer deducted for a promotion, rebate, trade allowance, co-op or MDF); '
      || 'SHORT_SHIPMENT (fewer goods received than invoiced); DAMAGED_GOODS (goods arrived damaged); DUPLICATE_BILLING (invoiced twice for the same delivery); '
      || 'MISSING_POD (customer asks for proof of delivery); TAX_EXEMPT (tax charged to an exempt customer); ALREADY_PAID (customer says the invoice is already paid); '
      || 'QUALITY (goods do not meet specification); OTHER (anything else). Respond with exactly one reason code.'),
    OBJECT_CONSTRUCT('role', 'user', 'content', 'Customer correspondence:\\n\\n' || NOTE_TEXT)),
  response_format => PARSE_JSON('{"type":"json","schema":{"type":"object","properties":{"reason_code":{"type":"string","enum":["PRICING","PROMO_DEDUCTION","SHORT_SHIPMENT","DAMAGED_GOODS","DUPLICATE_BILLING","MISSING_POD","TAX_EXEMPT","ALREADY_PAID","QUALITY","OTHER"]}},"required":["reason_code"],"additionalProperties":false}}')
):reason_code::VARCHAR
$$
""")
sql("ai_functions", "SHOW USER AI FUNCTIONS IN SCHEMA OFFICEHOURS_20261027.SAP_FINANCIALS")
md("Call it like any SQL function:")
sql("try_fn", """
SELECT NOTE_TEXT, CLASSIFY_DISPUTE_DEMO(NOTE_TEXT) AS AI_REASON, REASON_CODE AS TRUE_REASON
FROM AI_EVAL_SET ORDER BY NOTE_ID LIMIT 8
""")
md("""
#### Structured output beyond a single label
The same `AI_COMPLETE` call can return a full record: reason, routing, extracted invoice and amount, and confidence. Every field is typed by the schema.
""")
sql("structured", """
SELECT NOTE_TEXT,
       AI_COMPLETE(
         model => 'claude-haiku-4-5',
         prompt => 'Classify this AR dispute and extract fields.\\n\\n' || NOTE_TEXT,
         model_parameters => {'temperature': 0},
         response_format => {'type': 'json', 'schema': {'type': 'object', 'properties': {
            'reason_code': {'type': 'string', 'enum': ['PRICING','PROMO_DEDUCTION','SHORT_SHIPMENT','DAMAGED_GOODS','DUPLICATE_BILLING','MISSING_POD','TAX_EXEMPT','ALREADY_PAID','QUALITY','OTHER']},
            'route_to': {'type': 'string', 'enum': ['SALES','LOGISTICS','BILLING','COLLECTIONS']},
            'invoice_ref': {'type': ['string', 'null']},
            'disputed_amount': {'type': ['number', 'null']},
            'confidence': {'type': 'number'}},
            'required': ['reason_code', 'route_to', 'invoice_ref', 'disputed_amount', 'confidence']}}
       ) AS RESULT
FROM AI_EVAL_SET ORDER BY NOTE_ID LIMIT 3
""")

md("""
## 2. Evaluate it

How do we know it's right? Evaluation is a native **EXPERIMENT** object running against a **DATASET**: a versioned, immutable
snapshot of labeled rows, so the test set can't drift between runs.

The holdout is 300 dispute emails with known reason codes.
""")
sql("holdout_profile", """
SELECT REASON_CODE, COUNT(*) AS ROWS_, COUNT_IF(IS_HARD) AS POLICY_CASES
FROM AI_HOLDOUT GROUP BY 1 ORDER BY 2 DESC
""")
sql("eval_drop", "DROP EXPERIMENT IF EXISTS EVAL_CLASSIFY_DISPUTE_DEMO")
sql("eval_create", """
CREATE EXPERIMENT EVAL_CLASSIFY_DISPUTE_DEMO
  TYPE = 'AI_FUNCTION_EVALUATION'
  FROM SPECIFICATION $$
    query_text: OFFICEHOURS_20261027.SAP_FINANCIALS.CLASSIFY_DISPUTE_DEMO(NOTE_TEXT)
    metrics:
      - name: exact_match
    dataset:
      name: OFFICEHOURS_20261027.SAP_FINANCIALS.DISPUTE_HOLDOUT_DS
      version: v1
      ground_truth: REASON_CODE
    evaluation:
      num_eval_runs: 1
  $$
""")
sql("eval_execute", "EXECUTE EXPERIMENT EVAL_CLASSIFY_DISPUTE_DEMO")
md("""
The evaluation runs in the background (about 2-3 minutes). Re-run the next cell until `STATUS = FINISHED`.
Below it are the pre-run baselines: the same prompt on **Haiku** and on **Sonnet**.
""")
sql("eval_status", """
SHOW RUNS IN EXPERIMENT EVAL_CLASSIFY_DISPUTE_DEMO
 ->> SELECT "name" AS RUN, PARSE_JSON("metadata"):status::VARCHAR AS STATUS,
            PARSE_JSON("metadata"):metrics:score:value::FLOAT AS EXACT_MATCH FROM $1
""")
sql("baselines", """
SELECT STAGE, EXPERIMENT, MODEL, ROUND(SCORE, 3) AS EXACT_MATCH
FROM AI_EXPERIMENT_RESULTS WHERE STAGE LIKE '1%' ORDER BY MODEL
""")
md("""
**The trap:** Sonnet scores slightly higher, so the obvious move is to switch models. That costs **about 3x more per dispute** (credits from this account, section 5).

Look at *where* the model misses. Over the 2,000-row baseline run, every miss is on a **policy case**: a mispick, restocking fee,
compliance chargeback or unapplied cash. The model isn't wrong about English; it doesn't know Northwind's AR rules. That's a prompt problem, not a model problem.
""")
sql("misses_by_type", """
SELECT e.HARD_TYPE AS CASE_TYPE, e.REASON_CODE AS NORTHWIND_POLICY_SAYS,
       MODE(r.REASON_CODE) AS HAIKU_USUALLY_SAYS,
       COUNT(*) AS CASES,
       ROUND(AVG(IFF(r.REASON_CODE = e.REASON_CODE, 1, 0)), 2) AS HAIKU_ACC
FROM DISPUTE_CLASSIFICATION_RUNS r JOIN AI_EVAL_SET e USING (NOTE_ID)
WHERE r.MODEL = 'claude-haiku-4-5' AND r.PROMPT_VERSION = 'v1_baseline' AND e.IS_HARD
GROUP BY 1, 2 ORDER BY HAIKU_ACC
""")
sql("acc_by_model", """
SELECT MODEL || ' | ' || PROMPT_VERSION AS RUN, ROUND(EASY_ACC, 3) AS EASY_CASES, ROUND(HARD_ACC, 3) AS POLICY_CASES, ROUND(REASON_ACC, 3) AS OVERALL
FROM V_CLASSIFIER_ACCURACY ORDER BY RUN_TS
""")
py("""
import altair as alt
import pandas as pd
alt.renderers.enable("mimetype")


def as_pandas(df):
    return df.copy() if isinstance(df, pd.DataFrame) else df.to_pandas()


acc = as_pandas(acc_by_model).melt(id_vars="RUN", var_name="SEGMENT", value_name="ACCURACY")
alt.Chart(acc).mark_bar().encode(
    x=alt.X("SEGMENT:N", sort=["EASY_CASES", "POLICY_CASES", "OVERALL"], title=None),
    xOffset="RUN:N", color=alt.Color("RUN:N", title="Model | prompt"),
    y=alt.Y("ACCURACY:Q", scale=alt.Scale(domain=[0.5, 1.0])),
    tooltip=["RUN", "SEGMENT", "ACCURACY"],
).properties(height=320, width=520, title="Accuracy on 2,000 dispute emails")
""")

md("""
## 3. Optimize it

Instead of buying a bigger model, Snowflake fixes the function. One **optimization experiment** takes the function, the labeled
training data and the candidate models (**Haiku and Sonnet**). The GEPA optimizer then:
- runs the function and reads its failures
- has a reflection model rewrite the prompt and function body
- re-scores each candidate on the held-out set
- returns a **Pareto frontier of cost vs. quality** across both models

A light-budget run takes about 15 minutes, so we show the run done before the session (`CLASSIFY_DISPUTE_OPT_EXP`).
To launch a fresh one live, set `RUN_LIVE_OPTIMIZATION = True`.
""")
py('''
RUN_LIVE_OPTIMIZATION = False   # set True to launch a fresh ~15 min optimization in the background

if RUN_LIVE_OPTIMIZATION:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
    session.sql("DROP EXPERIMENT IF EXISTS CLASSIFY_DISPUTE_DEMO_OPT_EXP").collect()
    session.sql("""
CREATE EXPERIMENT CLASSIFY_DISPUTE_DEMO_OPT_EXP
  TYPE = 'AI_FUNCTION_OPTIMIZATION'
  FROM SPECIFICATION $$
    function:
      function_name: OFFICEHOURS_20261027.SAP_FINANCIALS.CLASSIFY_DISPUTE_DEMO
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
  $$""").collect()
    session.sql("EXECUTE EXPERIMENT CLASSIFY_DISPUTE_DEMO_OPT_EXP").collect()
    status = "Optimization launched: CLASSIFY_DISPUTE_DEMO_OPT_EXP"
else:
    status = "Using the pre-run experiment CLASSIFY_DISPUTE_OPT_EXP"
status
''')
md("Every candidate the optimizer tried, with model, validation score, held-out test score and cost relative to the seed:")
sql("opt_candidates", """
SELECT RUN_NAME, MODEL, ROUND(VAL_SCORE, 3) AS VAL_SCORE, ROUND(SCORE, 3) AS HOLDOUT_SCORE,
       ROUND(EST_COST, 2) AS COST_VS_SEED, COALESCE(IS_FRONTIER, FALSE) AS ON_FRONTIER
FROM AI_EXPERIMENT_RESULTS
WHERE EXPERIMENT = 'CLASSIFY_DISPUTE_OPT_EXP' AND STATUS = 'FINISHED'
ORDER BY COST_VS_SEED
""")
py("""
cand = as_pandas(opt_candidates)
cand["SCORE"] = cand["HOLDOUT_SCORE"].fillna(cand["VAL_SCORE"])
points = alt.Chart(cand).mark_circle(size=220).encode(
    x=alt.X("COST_VS_SEED:Q", title="Cost per call vs. seed (x)"),
    y=alt.Y("SCORE:Q", scale=alt.Scale(domain=[0.8, 1.0]), title="Score"),
    color=alt.Color("MODEL:N"), shape=alt.Shape("ON_FRONTIER:N", title="Pareto frontier"),
    tooltip=["RUN_NAME", "MODEL", "VAL_SCORE", "HOLDOUT_SCORE", "COST_VS_SEED"])
frontier = alt.Chart(cand[cand.ON_FRONTIER]).mark_line(strokeDash=[4, 4], color="gray").encode(x="COST_VS_SEED:Q", y="SCORE:Q")
(frontier + points).properties(height=340, width=560, title="Optimization: cost vs. quality")
""")
md("""
**Result:** optimized Haiku reaches **100% on the holdout at about 1.5x the seed's cost**. Sonnet candidates cost **4-5x**
and none made the frontier. The cheap model with a better prompt beats the expensive model.

What did the optimizer change? It learned Northwind's policy from the labeled data and wrote it into the prompt:
""")
# ITER_9 is the winning run from our pre-run experiment; replace it with your own winner (see sql/12_optimize.sql).
sql("what_changed", """
SHOW RUN PARAMETERS IN EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP RUN ITER_9
 ->> SELECT "value" AS OPTIMIZED_FUNCTION_BODY FROM $1 WHERE "name" = 'function_impl'
""")

md("""
## 4. Deploy the winner

One statement. The name and signature stay the same, so every downstream query, procedure and automation picks up the better version with no code changes.
""")
sql("deploy", """
CREATE OR REPLACE AI FUNCTION CLASSIFY_DISPUTE_DEMO(NOTE_TEXT VARCHAR)
RETURNS VARCHAR
FROM EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP RUN ITER_9
""")
md("Policy cases the seed got wrong, before and after:")
sql("before_after", """
SELECT e.HARD_TYPE, e.REASON_CODE AS POLICY_SAYS,
       r.REASON_CODE AS SEED_HAIKU,
       CLASSIFY_DISPUTE_DEMO(e.NOTE_TEXT) AS OPTIMIZED_HAIKU,
       e.NOTE_TEXT
FROM DISPUTE_CLASSIFICATION_RUNS r JOIN AI_EVAL_SET e USING (NOTE_ID)
WHERE r.MODEL = 'claude-haiku-4-5' AND r.PROMPT_VERSION = 'v1_baseline' AND r.REASON_CODE <> e.REASON_CODE
QUALIFY ROW_NUMBER() OVER (PARTITION BY e.HARD_TYPE ORDER BY e.NOTE_ID) <= 2
""")

md("""
## 5. What it costs

Effective credits per million tokens come from this account's own `CORTEX_AISQL_USAGE_HISTORY`, not a price list.
Change `disputes_per_day` and `usd_per_credit` to match the customer, then re-run the cost cell.
""")
py("""
disputes_per_day = 2000
usd_per_credit = 2.00
""")
sql("cost", """
WITH rates AS (
  SELECT MODEL_NAME AS MODEL, SUM(TOKEN_CREDITS) / NULLIF(SUM(TOKENS), 0) * 1e6 AS CREDITS_PER_1M_TOKENS
  FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY
  WHERE FUNCTION_NAME = 'AI_COMPLETE' AND MODEL_NAME IN ('claude-haiku-4-5', 'claude-sonnet-4-6')
    AND USAGE_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  GROUP BY 1),
toks AS (
  SELECT r.MODEL, AVG(r.PROMPT_TOKENS + r.COMPLETION_TOKENS) AS TOKENS_PER_CALL,
         AVG(IFF(r.REASON_CODE = e.REASON_CODE, 1, 0)) AS ACCURACY
  FROM DISPUTE_CLASSIFICATION_RUNS r JOIN AI_EVAL_SET e USING (NOTE_ID)
  WHERE r.PROMPT_VERSION = 'v1_baseline' GROUP BY 1),
opt AS (
  SELECT 'claude-haiku-4-5 (optimized)' AS LABEL, 'claude-haiku-4-5' AS MODEL,
         (SELECT MAX(EST_COST) FROM AI_EXPERIMENT_RESULTS WHERE EXPERIMENT = 'CLASSIFY_DISPUTE_OPT_EXP' AND RUN_NAME = 'ITER_9') AS MULT,
         (SELECT MAX(REASON_ACC) FROM V_CLASSIFIER_ACCURACY WHERE PROMPT_VERSION = 'v2_optimized_ITER_9') AS ACCURACY),
options AS (
  SELECT t.MODEL || ' (seed prompt)' AS OPTION_NAME, t.TOKENS_PER_CALL, t.ACCURACY, r.CREDITS_PER_1M_TOKENS
  FROM toks t JOIN rates r USING (MODEL)
  UNION ALL
  SELECT o.LABEL, t.TOKENS_PER_CALL * o.MULT, o.ACCURACY, r.CREDITS_PER_1M_TOKENS
  FROM opt o JOIN toks t USING (MODEL) JOIN rates r USING (MODEL))
SELECT OPTION_NAME, ROUND(ACCURACY, 3) AS ACCURACY, ROUND(TOKENS_PER_CALL) AS TOKENS_PER_CALL,
       ROUND(TOKENS_PER_CALL * CREDITS_PER_1M_TOKENS / 1e3, 3) AS CREDITS_PER_1K_DISPUTES,
       ROUND(TOKENS_PER_CALL * CREDITS_PER_1M_TOKENS / 1e6 * {{disputes_per_day}} * 365) AS ANNUAL_CREDITS,
       ROUND(TOKENS_PER_CALL * CREDITS_PER_1M_TOKENS / 1e6 * {{disputes_per_day}} * 365 * {{usd_per_credit}}) AS ANNUAL_USD,
       ROUND((1 - ACCURACY) * {{disputes_per_day}} * 365) AS MISROUTED_PER_YEAR
FROM options ORDER BY ANNUAL_CREDITS
""")
md("""
Optimized Haiku is cheaper than Sonnet and more accurate than either seed version. The cost estimate for the optimized prompt scales Haiku's
baseline tokens by the optimizer's measured cost-vs-seed ratio.

## Where it goes next
- `SP_CLASSIFY_NEW_DISPUTES` calls the production `CLASSIFY_DISPUTE` function, which runs this same optimized body
- The **Daily Collections Worklist** automation runs it every weekday morning, routes disputes to Sales, Logistics and Billing,
  and takes disputed dollars off the collectors' call list
- The Streamlit app `STREAMLITS.DISPUTE_AI_COMPARE` shows architecture, accuracy and cost side by side

**Reset:** `DROP FUNCTION IF EXISTS CLASSIFY_DISPUTE_DEMO(VARCHAR); DROP EXPERIMENT IF EXISTS EVAL_CLASSIFY_DISPUTE_DEMO;`
""")

nb = {"cells": cells,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python", "version": "3.11"}},
      "nbformat": 4, "nbformat_minor": 5}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(nb, f, indent=1)
ids = [c["id"] for c in cells]
assert len(set(ids)) == len(ids)
sql_cells = [c for c in cells if c["metadata"].get("language") == "sql"]

print(len(cells), "cells,", len(sql_cells), "sql")
