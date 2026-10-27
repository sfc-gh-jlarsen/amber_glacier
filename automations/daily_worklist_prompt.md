Daily Collections Worklist for Northwind Industrial (SAP AR). Snowflake connection: the active one. Use database OFFICEHOURS_20261027, schema SAP_FINANCIALS, warehouse OFFICEHOURS_WH. Read-mostly: only call the two procedures below; do not create or drop objects.

1. CALL SP_CLASSIFY_NEW_DISPUTES(500); record how many new disputes were classified.
2. CALL SP_BUILD_WORKLIST(25);
3. Query COLLECTIONS_WORKLIST_DAILY for RUN_DATE = CURRENT_DATE() and V_AR_OPEN_ITEMS / V_DISPUTES_CLASSIFIED / UDM_COLL_PROMISE to compute:
   - Total past-due USD, split into actionable (no open dispute) vs in dispute.
   - In-dispute USD by AI_ROUTE_TO (Sales / Logistics / Billing / Collections): that money will not be collected by calling.
   - Top 3 customers by ACTIONABLE_USD across all collector groups, with their talk track.
   - Promises to pay that broke in the last 7 days, by collector group.
   - New disputes classified today, by AI_REASON.
4. Write a short brief to reports/daily_worklist_<YYYY-MM-DD>.md in this project. Lead with a 3-line summary, then one table per bullet above. Plain language for an AR manager; no SQL in the brief.
5. Finish with a one-line status: "Worklist: <n> rows, <m> disputes classified, $<x> actionable past due."
