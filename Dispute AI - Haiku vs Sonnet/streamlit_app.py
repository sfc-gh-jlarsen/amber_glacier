"""Dispute AI: architecture, process, accuracy and cost (Haiku vs Sonnet)."""
import os

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dispute AI - Haiku vs Sonnet", layout="wide")
session = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL")).session()
S = "OFFICEHOURS_20261027.SAP_FINANCIALS"


@st.cache_data(ttl=600)
def q(sql: str, params: tuple | None = None) -> pd.DataFrame:
    return session.sql(sql, params=list(params) if params else None).to_pandas()


st.title("Dispute triage with Cortex AI: Haiku vs Sonnet")
st.caption("Northwind Industrial / SAP FSCM dispute correspondence classified into reason codes")
tab_arch, tab_proc, tab_acc, tab_cost = st.tabs(["Architecture", "Process", "Accuracy", "Cost"])

with tab_arch:
    st.graphviz_chart("""
digraph G {
  rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.45; pad=0.2; splines=spline; newrank=true;
  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=16 penwidth=1.6 margin="0.25,0.12"
        fillcolor="#FFFFFF" color="#29B5E8" fontcolor="#1F2D3D"];
  edge [color="#8A99A8" penwidth=1.3 arrowsize=0.8 fontname="Helvetica" fontsize=13 fontcolor="#5B6B7B"];

  subgraph cluster_src { label="SOURCE"; style="rounded,filled"; fillcolor="#F4F6F8"; color="#D5DCE3"; fontname="Helvetica-Bold"; fontsize=14; fontcolor="#5B6B7B";
    sap [label=<<B>SAP S/4HANA</B><BR/><FONT POINT-SIZE="13">FI-AR + FSCM</FONT>> color="#5B6B7B"];
    gen [label=<<B>Python generator</B><BR/><FONT POINT-SIZE="13">history + daily batches</FONT>> color="#5B6B7B"]; }

  subgraph cluster_ing { label="INGEST"; style="rounded,filled"; fillcolor="#EAF6FC"; color="#BFE6F7"; fontname="Helvetica-Bold"; fontsize=14; fontcolor="#11567F";
    stg  [label=<<B>@LANDING stage</B><BR/><FONT POINT-SIZE="13">Parquet</FONT>>];
    pipe [label=<<B>Snowpipe</B><BR/><FONT POINT-SIZE="13">COPY · MATCH_BY_COLUMN_NAME</FONT>>]; }

  subgraph cluster_data { label="DATA"; style="rounded,filled"; fillcolor="#EAF6FC"; color="#BFE6F7"; fontname="Helvetica-Bold"; fontsize=14; fontcolor="#11567F";
    raw [label=<<B>SAP tables</B><BR/><FONT POINT-SIZE="13">BSID · BSAD · BKPF<BR/>UDMCASEATTR00 · UDM_DISPUTE_NOTES</FONT>> shape=cylinder style=filled];
    dt  [label=<<B>DT_AR_OPEN_ITEMS</B><BR/><FONT POINT-SIZE="13">+ aging / DSO views</FONT>>]; }

  subgraph cluster_ai { label="CORTEX AI"; style="rounded,filled"; fillcolor="#FFF8E6"; color="#F5D58A"; fontname="Helvetica-Bold"; fontsize=14; fontcolor="#8A5A00";
    exp [label=<<B>AI Function Studio</B><BR/><FONT POINT-SIZE="13">Evaluate + Optimize (EXPERIMENTs)</FONT>> color="#F2A900"];
    fn  [label=<<B>CLASSIFY_DISPUTE</B><BR/><FONT POINT-SIZE="13">AI FUNCTION · AI_COMPLETE<BR/>structured output</FONT>> color="#F2A900" penwidth=2.2];
    cls [label=<<B>DISPUTE_CLASSIFICATIONS</B>> shape=cylinder style=filled color="#F2A900"]; }

  subgraph cluster_out { label="ACTION"; style="rounded,filled"; fillcolor="#EDF8F1"; color="#B9E3C8"; fontname="Helvetica-Bold"; fontsize=14; fontcolor="#1E6B3D";
    wl   [label=<<B>Collections worklist</B><BR/><FONT POINT-SIZE="13">SP_BUILD_WORKLIST →<BR/>COLLECTIONS_WORKLIST_DAILY</FONT>> color="#2E9E5B" penwidth=2.2];
    auto [label=<<B>Cortex Code automations</B><BR/><FONT POINT-SIZE="13">daily worklist · weekly leakage</FONT>> color="#2E9E5B"]; }

  sap -> stg [style=dashed label="extract"]; gen -> stg;
  stg -> pipe -> raw;
  raw -> dt -> wl;
  raw -> fn [color="#F2A900" penwidth=1.8 label="dispute emails"];
  fn -> cls [color="#F2A900" penwidth=1.8]; cls -> wl [color="#F2A900" penwidth=1.8 label="reason + route"];
  exp -> fn [style=dashed color="#F2A900" label="deploy winner"];
  auto -> wl [style=dotted color="#2E9E5B"]; auto -> fn [style=dotted color="#2E9E5B" constraint=false];
  { rank=same; sap; gen; }
  { rank=same; pipe; exp; }
  { rank=same; raw; fn; }
  { rank=same; dt; cls; }
  { rank=same; wl; auto; }
  dt -> cls [style=invis]; wl -> auto [style=invis];
}
""")
    st.markdown("""
**Why AI here:** dispute reason codes in SAP are blank or wrong on most cases (processors skip the field).
The reason lives in the customer's email. Classifying it routes the dispute to Sales, Logistics, Billing or
Collections, and removes disputed dollars from the collector's call list.
""")
    keyed = q(f"""SELECT IFF(c.REASON IS NULL, 'Blank', IFF(c.REASON = l.REASON_CODE, 'Correct', 'Wrong')) AS KEYED, COUNT(*) N
                FROM {S}.UDMCASEATTR00 c JOIN {S}.UDM_DISPUTE_NOTES n ON n.EXT_KEY = c.EXT_KEY AND n.NOTE_TYPE = 'EMAIL_IN'
                JOIN {S}.DISPUTE_NOTE_LABELS l ON l.NOTE_ID = n.NOTE_ID GROUP BY 1""")
    st.altair_chart(alt.Chart(keyed).mark_arc(innerRadius=60).encode(theta="N", color="KEYED", tooltip=["KEYED", "N"])
                    .properties(title="Reason code as keyed in SAP today", height=260), use_container_width=True)

    st.subheader("Today's call list")
    # Not cached: the cutoff is a schema variable finance can change at any time.
    # Also bypass Snowflake's result cache, which can return the pre-SET result for identical SQL text.
    session.sql("ALTER SESSION SET USE_CACHED_RESULT = FALSE").collect()
    cl = session.sql(f"""SELECT $OFFICEHOURS_20261027.SAP_FINANCIALS.MIN_DAYS_PAST_DUE AS CUTOFF,
                                COUNT(*) AS CUSTOMERS, SUM(ACTIONABLE_USD) AS ACTIONABLE_USD
                         FROM {S}.V_CALL_LIST""").to_pandas()
    a, b, c = st.columns(3)
    a.metric("Past-due cutoff (days)", int(cl.CUTOFF[0]))
    b.metric("Customers to call", f"{int(cl.CUSTOMERS[0]):,}")
    c.metric("Actionable $", f"${float(cl.ACTIONABLE_USD[0] or 0):,.0f}")
    st.caption("Cutoff comes from schema variable `SAP_FINANCIALS.MIN_DAYS_PAST_DUE`. "
               "Change it with `SET SAP_FINANCIALS.MIN_DAYS_PAST_DUE = 90;`, then rerun the app.")

with tab_proc:
    st.markdown("""
1. **AI_COMPLETE + structured output**: JSON schema with enum reason codes, route, invoice, amount, confidence (`SP_RUN_CLASSIFIER`).
2. **Evaluate**: `CREATE EXPERIMENT ... TYPE='AI_FUNCTION_EVALUATION'`, exact_match on a 300-row labeled DATASET.
3. **Optimize**: `TYPE='AI_FUNCTION_OPTIMIZATION'`, GEPA rewrites the function body for each model; Pareto frontier on cost and quality.
4. **AI Function**: winner deployed with `CREATE AI FUNCTION ... FROM EXPERIMENT`; the daily automation calls it.
""")
    exp = q(f"SELECT * FROM {S}.AI_EXPERIMENT_RESULTS ORDER BY STAGE, MODEL")
    if exp.empty:
        st.info("Run sql/13_capture_experiments.sql after the experiments finish to populate this view.")
    else:
        st.dataframe(exp, use_container_width=True, hide_index=True)
        st.altair_chart(alt.Chart(exp).mark_bar().encode(
            x=alt.X("STAGE:N", sort=None), y=alt.Y("SCORE:Q", scale=alt.Scale(domain=[0.8, 1.0])),
            color="MODEL:N", xOffset="MODEL:N", tooltip=list(exp.columns)).properties(height=320), use_container_width=True)

with tab_acc:
    acc = q(f"""SELECT MODEL, PROMPT_VERSION, N, REASON_ACC, EASY_ACC, HARD_ACC, ROUTE_ACC, INVOICE_ACC, AMOUNT_ACC
                FROM {S}.V_CLASSIFIER_ACCURACY ORDER BY RUN_TS""")
    st.dataframe(acc.style.format({c: "{:.1%}" for c in acc.columns if c.endswith("ACC")}), use_container_width=True, hide_index=True)
    runs = acc.MODEL + " | " + acc.PROMPT_VERSION
    pick = st.selectbox("Confusion matrix for", runs.tolist())
    if pick:
        m, pv = pick.split(" | ")
        cm = q(f"""SELECT e.REASON_CODE AS ACTUAL, r.REASON_CODE AS PREDICTED, COUNT(*) N
                   FROM {S}.DISPUTE_CLASSIFICATION_RUNS r JOIN {S}.AI_EVAL_SET e USING (NOTE_ID)
                   WHERE r.MODEL = ? AND r.PROMPT_VERSION = ? GROUP BY 1, 2""", (m, pv))
        st.altair_chart(alt.Chart(cm).mark_rect().encode(x="PREDICTED:N", y="ACTUAL:N", color=alt.Color("N:Q", scale=alt.Scale(type="log")),
                        tooltip=["ACTUAL", "PREDICTED", "N"]).properties(height=420), use_container_width=True)
        miss = q(f"""SELECT e.HARD_TYPE, e.REASON_CODE AS ACTUAL, r.REASON_CODE AS PREDICTED, e.NOTE_TEXT
                     FROM {S}.DISPUTE_CLASSIFICATION_RUNS r JOIN {S}.AI_EVAL_SET e USING (NOTE_ID)
                     WHERE r.MODEL = ? AND r.PROMPT_VERSION = ? AND r.REASON_CODE <> e.REASON_CODE LIMIT 50""", (m, pv))
        st.markdown("**Misses** (all are policy cases: the label follows Northwind AR policy, not a dictionary definition)")
        st.dataframe(miss, use_container_width=True, hide_index=True)

with tab_cost:
    rates = q("""SELECT MODEL_NAME AS MODEL, SUM(TOKEN_CREDITS) CREDITS, SUM(TOKENS) TOKENS,
                        SUM(TOKEN_CREDITS) / NULLIF(SUM(TOKENS), 0) * 1e6 AS CREDITS_PER_1M_TOKENS
                 FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY
                 WHERE FUNCTION_NAME = 'AI_COMPLETE' AND MODEL_NAME IN ('claude-haiku-4-5', 'claude-sonnet-4-6')
                   AND USAGE_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP()) GROUP BY 1""")
    st.caption("Effective credits per 1M tokens come from this account's CORTEX_AISQL_USAGE_HISTORY (lags up to a few hours). "
               "Optimized Haiku tokens = baseline Haiku tokens x the optimizer's cost-vs-seed multiple (estimate).")
    toks = q(f"""SELECT MODEL, AVG(PROMPT_TOKENS + COMPLETION_TOKENS) AS TOKENS_PER_DISPUTE,
                        AVG(IFF(r.REASON_CODE = e.REASON_CODE, 1, 0)) AS ACCURACY
                 FROM {S}.DISPUTE_CLASSIFICATION_RUNS r JOIN {S}.AI_EVAL_SET e USING (NOTE_ID)
                 WHERE PROMPT_VERSION = 'v1_baseline' GROUP BY 1""")
    df = toks.merge(rates[["MODEL", "CREDITS_PER_1M_TOKENS"]], on="MODEL", how="left")
    # Optimized Haiku: longer prompt, so tokens scale by the experiment's cost multiple vs the seed
    opt = q(f"""SELECT (SELECT MAX(EST_COST) FROM {S}.AI_EXPERIMENT_RESULTS WHERE RUN_NAME = 'ITER_9'
                        AND EXPERIMENT = 'CLASSIFY_DISPUTE_OPT_EXP') AS MULT,
                       (SELECT REASON_ACC FROM {S}.V_CLASSIFIER_ACCURACY WHERE PROMPT_VERSION = 'v2_optimized_ITER_9') AS ACC""")
    if len(opt) and opt.MULT.notna().all() and (df.MODEL == "claude-haiku-4-5").any():
        h0 = df[df.MODEL == "claude-haiku-4-5"].iloc[0]
        df = pd.concat([df, pd.DataFrame([dict(MODEL="claude-haiku-4-5 (optimized)",
                                               TOKENS_PER_DISPUTE=h0.TOKENS_PER_DISPUTE * float(opt.MULT[0]),
                                               ACCURACY=float(opt.ACC[0]),
                                               CREDITS_PER_1M_TOKENS=h0.CREDITS_PER_1M_TOKENS)])], ignore_index=True)
    c1, c2 = st.columns(2)
    per_day = c1.slider("Disputes classified per day", 100, 50000, 2000, step=100)
    credit_price = c2.number_input("$ per credit (your contract)", value=2.0, step=0.1)
    df["CREDITS_PER_1K_DISPUTES"] = df.TOKENS_PER_DISPUTE * df.CREDITS_PER_1M_TOKENS / 1000
    df["ANNUAL_CREDITS"] = df.CREDITS_PER_1K_DISPUTES * per_day / 1000 * 365
    df["ANNUAL_USD"] = df.ANNUAL_CREDITS * credit_price
    df["MISCLASSIFIED_PER_YEAR"] = (1 - df.ACCURACY) * per_day * 365
    st.dataframe(df.style.format({"TOKENS_PER_DISPUTE": "{:,.0f}", "ACCURACY": "{:.1%}", "CREDITS_PER_1M_TOKENS": "{:.3f}",
                                  "CREDITS_PER_1K_DISPUTES": "{:.3f}", "ANNUAL_CREDITS": "{:,.0f}", "ANNUAL_USD": "${:,.0f}",
                                  "MISCLASSIFIED_PER_YEAR": "{:,.0f}"}), use_container_width=True, hide_index=True)
    m = df.set_index("MODEL")
    if {"claude-haiku-4-5", "claude-sonnet-4-6"} <= set(m.index) and m.CREDITS_PER_1M_TOKENS.notna().all():
        h, s_ = m.loc["claude-haiku-4-5"], m.loc["claude-sonnet-4-6"]
        a, b, c = st.columns(3)
        a.metric("Sonnet cost multiple vs Haiku", f"{s_.ANNUAL_CREDITS / h.ANNUAL_CREDITS:.1f}x")
        b.metric("Accuracy gap (baseline prompt)", f"{(s_.ACCURACY - h.ACCURACY) * 100:.1f} pts")
        if "claude-haiku-4-5 (optimized)" in m.index:
            o = m.loc["claude-haiku-4-5 (optimized)"]
            c.metric("Optimized Haiku vs Sonnet", f"{(o.ACCURACY - s_.ACCURACY) * 100:+.1f} pts",
                     f"{(1 - o.ANNUAL_USD / s_.ANNUAL_USD) * 100:.0f}% cheaper")
    st.altair_chart(alt.Chart(df).mark_circle(size=400).encode(
        x=alt.X("CREDITS_PER_1K_DISPUTES:Q", title="Credits per 1K disputes"),
        y=alt.Y("ACCURACY:Q", scale=alt.Scale(domain=[0.85, 1.0])), color="MODEL:N",
        tooltip=list(df.columns)).properties(height=320, title="Cost vs accuracy"), use_container_width=True)
