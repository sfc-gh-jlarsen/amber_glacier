# Live demo: set up the "Weekly Dispute Leakage & Aging Drift Review" automation

In Cortex Code Desktop, ask:

> Create a weekly automation called "Weekly Dispute Leakage Review" that runs Mondays at 08:00 in this project, using the prompt below.

Or paste this prompt directly into the Automations panel (frequency: weekly, Monday 08:00):

---

Weekly Dispute Leakage & Aging Drift Review for Northwind Industrial (SAP AR). Use OFFICEHOURS_20261027.SAP_FINANCIALS on warehouse OFFICEHOURS_WH. Read only; do not create, alter or drop anything.

1. Aging drift: compare SELECT * FROM TABLE(AR_AGING_ASOF(CURRENT_DATE())) with TABLE(AR_AGING_ASOF(CURRENT_DATE() - 7)) by customer (join KNA1 for name). List customers whose 61+ day balance grew by more than $25K, and customers who moved into an older bucket for the first time. Flag any that are over their credit limit (UKMBP_CMS_SGM.CREDIT_LIMIT).
2. Dispute leakage: from V_DISPUTES_CLASSIFIED where STATUS = 'OPEN', total DISP_AMT_USD by AI_REASON and age band (0-15, 16-30, 31-60, 60+ days). Call out the largest reason x age cell.
3. Stale disputes: open disputes with DAYS_SINCE_ACTIVITY > 30, grouped by AI_ROUTE_TO, top 10 by amount with customer name.
4. Pattern check: is any region or reason spiking? Compare the last 8 weeks of dispute creation by REGION x AI_REASON against the prior 8 weeks and report anything that more than doubled.
5. Trend: DSO today vs 4 weeks ago from V_DSO_DAILY.
6. Recommendations: which disputes to escalate to Sales vs Logistics this week, and which collector group needs coaching (broken promises from UDM_COLL_PROMISE).

Write an HTML report to reports/weekly_leakage_<YYYY-MM-DD>.html with a summary at the top, one chart per section (inline SVG, no external libraries), and the tables. End with a one-line status: "Leakage review: $<x> in open disputes, <n> stale, top driver <reason/region>."

---

**What it should find (planted in the data):** the three US accounts sliding into 61-90, the TX/AZ/NM promo-deduction spike since the price change ~8 weeks ago, the ~40 duplicate-billing disputes from one billing run, the stale disputes, and collector group C3's ~50% broken-promise rate.
