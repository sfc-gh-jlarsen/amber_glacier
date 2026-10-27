# SAP AR collections and dispute triage on Snowflake

A self-contained demo built on synthetic SAP S/4HANA accounts receivable data for a fictional
manufacturer, **Northwind Industrial**. It shows how to:

- **Create, evaluate and optimize an AI Function** that reads a customer's dispute email and returns
  the SAP dispute reason code, then deploy the optimized version with one statement
- Pick a model on a **cost/quality Pareto frontier** (Claude Haiku vs. Sonnet), with costs taken from
  the account's own `CORTEX_AISQL_USAGE_HISTORY`
- Drive a collections policy from a **schema variable** instead of hard-coded thresholds
- Run the daily and weekly AR reviews as **Cortex Code automations**

All data is generated. Customer names, emails and amounts are fictional.

> **Your numbers will differ.** LLM calls and the prompt optimizer are not deterministic, so
> accuracy, the winning run and the rewritten prompt will vary from run to run and from what is
> shown here. That's fine: the point is the pattern, not the decimal places. A working example
> you can run in your own account is worth a hundred slides and days of meetings.

## Start here: the demo notebooks

The [`demo/`](demo/) directory is the main entry point. Both notebooks are SQL-first Snowsight
Workspace notebooks.

| Notebook | What it shows | Runtime |
|---|---|---|
| [`ai_function_create_evaluate_optimize.ipynb`](demo/ai_function_create_evaluate_optimize.ipynb) | Create → Evaluate → Optimize → Deploy an AI Function, then cost it | ~5 min |
| [`schema_variables.ipynb`](demo/schema_variables.ipynb) | A typed, governed schema variable (`MIN_DAYS_PAST_DUE`) drives a call-list view; change it with one `SET` | ~1 min |

See [`demo/README.md`](demo/README.md) for the section-by-section walkthrough and the results from
our last run.

The AI Function notebook is generated from
[`utilities/build_notebook.py`](utilities/build_notebook.py). Edit the script, not the `.ipynb`,
then rebuild:

```bash
python utilities/build_notebook.py
```

## Repository layout

| Path | Contents |
|---|---|
| `demo/` | The demo notebooks and their walkthrough |
| `sql/` | Numbered setup scripts: database, SAP tables, views, procedures, and the AI evaluate/optimize loop |
| `generator/` | Synthetic SAP FI-AR / FSCM data generator (seeded and reproducible) with labeled dispute emails |
| `automations/` | Prompts for the Daily Collections Worklist and Weekly Dispute Leakage automations |
| `Dispute AI - Haiku vs Sonnet/` | Streamlit app comparing architecture, accuracy and cost across models |
| `utilities/` | Build script that generates the AI Function notebook |

## Prerequisites

- A Snowflake account with Cortex AI Functions, `AI_COMPLETE` on `claude-haiku-4-5` and
  `claude-sonnet-4-6`, and AI Function experiments (`CREATE AI FUNCTION`, `CREATE EXPERIMENT`)
- A role that can create a database, warehouse and Streamlit app
- For local runs: Python 3.11 with `snowflake-snowpark-python`, `pandas` and `numpy`, plus a
  connection in `~/.snowflake/connections.toml`

Everything is created in database `OFFICEHOURS_20261027` (schemas `SAP_FINANCIALS` and `STREAMLITS`)
on an XS warehouse `OFFICEHOURS_WH`.

## Build the environment

Run these in order from a Snowsight Workspace or the `snow` CLI.

1. `sql/00_setup.sql`: database, schemas, warehouse, stage
2. `sql/01_tables.sql`: SAP tables (`KNA1`, `BSID`, `BSAD`, `UDMCASEATTR00`, ...)
3. Load synthetic data:
   ```bash
   python generator/generate.py                          # uses your default connection
   python generator/generate.py --connection <name>      # or a named one
   python generator/generate.py --dry-run                # generate without loading
   ```
   In a Snowsight Workspace it uses the active session.
4. `sql/02_views_dt.sql`, `sql/03_procs.sql`: business views, dynamic table, procedures
5. `sql/10_ai_complete.sql`: evaluation set and the `SP_RUN_CLASSIFIER` procedure. Then fill the
   baseline runs the notebook compares:
   ```sql
   CALL SP_RUN_CLASSIFIER('claude-haiku-4-5',  'v1_baseline', 2000);
   CALL SP_RUN_CLASSIFIER('claude-sonnet-4-6', 'v1_baseline', 2000);
   ```
6. `sql/11a`–`11c`: the seed AI Functions; `sql/11_eval.sql`: holdout/train datasets and baseline
   evaluation experiments
7. `sql/12_optimize.sql`: the GEPA optimization experiment (about 15 minutes). When it finishes,
   find your winning run (`SHOW RUNS IN EXPERIMENT CLASSIFY_DISPUTE_OPT_EXP`). The notebook and
   script use `ITER_9`, the winner from our run; replace it with yours.
8. `sql/13_capture_experiments.sql`, then `CALL SP_CAPTURE_EXPERIMENTS();` to copy experiment
   scores into `AI_EXPERIMENT_RESULTS`
9. `CALL SP_BUILD_WORKLIST(25);` fills `COLLECTIONS_WORKLIST_DAILY`, which the schema-variables
   notebook needs
10. Optional: `sql/14_streamlit_from_workspace.sql` deploys the Streamlit app (replace
    `<YOUR_USER>` first)

> **Known gap:** the cost cell in the AI Function notebook (and the Streamlit app) reads accuracy for
> prompt version `v2_optimized_ITER_9` from `V_CLASSIFIER_ACCURACY`. In our account those rows came
> from a one-off scoring run of the optimized function over `AI_EVAL_SET` that is not scripted here.
> Without them, the optimized row in the cost table shows no accuracy or misrouted count.

## Automations

[`automations/`](automations/) holds two prompts for scheduled Cortex Code runs: a weekday
collections worklist and a weekly dispute-leakage review. The weekly prompt lists the patterns
planted in the generated data, so you can check that the review finds them.

## Reset

Demo objects end in `_DEMO` and can be dropped without affecting the rest:

```sql
DROP FUNCTION IF EXISTS CLASSIFY_DISPUTE_DEMO(VARCHAR);
DROP EXPERIMENT IF EXISTS EVAL_CLASSIFY_DISPUTE_DEMO;
```

To remove everything: `DROP DATABASE OFFICEHOURS_20261027; DROP WAREHOUSE OFFICEHOURS_WH;`

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
