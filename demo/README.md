# Demo: AI Functions for SAP dispute triage

`ai_function_create_evaluate_optimize.ipynb` is a Snowsight Workspace notebook (SQL-first). Open it in a
Snowsight Workspace and choose Run all; it runs in about 5 minutes. Build the environment first (see the
[repo README](../README.md)).

| Section | What it shows | Key objects |
|---|---|---|
| The problem | 55% of SAP dispute reason codes are blank; the reason is in the email | `UDMCASEATTR00`, `UDM_DISPUTE_NOTES` |
| 1. Create | `CREATE AI FUNCTION` over `AI_COMPLETE` with a JSON-schema `response_format`; a multi-field structured extract | `CLASSIFY_DISPUTE_DEMO` |
| 2. Evaluate | `AI_FUNCTION_EVALUATION` experiment on a versioned `DATASET`; misses are all policy cases | `EVAL_CLASSIFY_DISPUTE_DEMO`, `DISPUTE_HOLDOUT_DS` |
| 3. Optimize | GEPA across Haiku and Sonnet; cost/quality Pareto frontier; the rewritten prompt | `CLASSIFY_DISPUTE_OPT_EXP` (pre-run) |
| 4. Deploy | `CREATE AI FUNCTION ... FROM EXPERIMENT ... RUN ITER_9`; before/after on missed cases | `CLASSIFY_DISPUTE_DEMO` |
| 5. Cost | Credits from this account's `CORTEX_AISQL_USAGE_HISTORY`, projected annually | |

Numbers from the last run (2,000 emails; costs at 2,000 disputes/day and $2/credit):

| Option | Accuracy | Credits / 1K disputes | Annual $ | Misrouted / yr |
|---|---|---|---|---|
| Haiku, seed prompt | 93.5% | 0.91 | $1,326 | 47,815 |
| Sonnet, seed prompt | 97.3% | 2.89 | $4,216 | 19,710 |
| **Haiku, optimized** | **99.9%** | **1.40** | **$2,045** | **1,095** |

The optimized figure includes the 250 rows used for training, so treat it as slightly optimistic; on the 300-row holdout it scored 100%.

Notes:
- The live optimization takes ~15 minutes, so the notebook reads the pre-run experiment. Set `RUN_LIVE_OPTIMIZATION = True` to launch a fresh one.
- Everything created here ends in `_DEMO`. Production `CLASSIFY_DISPUTE` (used by the daily automation) is not touched.
- Reset: `DROP FUNCTION IF EXISTS CLASSIFY_DISPUTE_DEMO(VARCHAR); DROP EXPERIMENT IF EXISTS EVAL_CLASSIFY_DISPUTE_DEMO;`
- Rebuild the notebook from source: `python utilities/build_notebook.py` (the notebook is generated; edit the script, not the .ipynb)
