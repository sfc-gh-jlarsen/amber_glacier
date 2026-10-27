-- SAP FI-AR / FSCM tables. Column names follow SAP field names; comments give the English meaning.
USE SCHEMA OFFICEHOURS_20261027.SAP_FINANCIALS;

CREATE OR REPLACE TABLE KNA1 (            -- Customer master (general)
  KUNNR VARCHAR(10) PRIMARY KEY,           -- customer number
  NAME1 VARCHAR, LAND1 VARCHAR(3),         -- name, country
  REGIO VARCHAR(3), ORT01 VARCHAR,         -- region/state, city
  KUKLA VARCHAR(2),                        -- customer classification (industry)
  ERDAT DATE                               -- created on
);

CREATE OR REPLACE TABLE KNB1 (            -- Customer master (company code)
  KUNNR VARCHAR(10), BUKRS VARCHAR(4),     -- customer, company code
  AKONT VARCHAR(10),                       -- reconciliation account
  ZTERM VARCHAR(4),                        -- payment terms (NT30, NT45, NT60, 2N10)
  BUSAB VARCHAR(2),                        -- accounting clerk = collector group
  PRIMARY KEY (KUNNR, BUKRS)
);

CREATE OR REPLACE TABLE UKMBP_CMS_SGM (   -- Credit management segment
  PARTNER VARCHAR(10), CREDIT_SGMNT VARCHAR(4),
  CREDIT_LIMIT NUMBER(15,2), RISK_CLASS VARCHAR(3),  -- A (low) .. E (high)
  CREDIT_SCORE NUMBER(3), WAERS VARCHAR(3)
);

CREATE OR REPLACE TABLE BKPF (            -- Accounting document header
  BUKRS VARCHAR(4), BELNR VARCHAR(10), GJAHR NUMBER(4),
  BLART VARCHAR(2),                        -- doc type: RV invoice, DZ payment, DG credit memo
  BLDAT DATE, BUDAT DATE,                  -- document / posting date
  XBLNR VARCHAR(16),                       -- reference (customer-facing invoice no.)
  WAERS VARCHAR(3), USNAM VARCHAR(12), BKTXT VARCHAR
);

CREATE OR REPLACE TABLE BSEG (            -- Accounting document line items (customer lines only)
  BUKRS VARCHAR(4), BELNR VARCHAR(10), GJAHR NUMBER(4), BUZEI NUMBER(3),
  KOART VARCHAR(1),                        -- account type (D = customer)
  KUNNR VARCHAR(10), SHKZG VARCHAR(1),     -- debit S / credit H
  DMBTR NUMBER(15,2), WRBTR NUMBER(15,2),  -- amount local / document currency
  ZFBDT DATE, ZTERM VARCHAR(4), ZBD1T NUMBER(3), -- baseline date, terms, net days
  AUGBL VARCHAR(10), AUGDT DATE,           -- clearing document / date
  SGTXT VARCHAR
);

-- Open (BSID) and cleared (BSAD) customer items share a layout
CREATE OR REPLACE TABLE BSID (
  BUKRS VARCHAR(4), KUNNR VARCHAR(10), GJAHR NUMBER(4), BELNR VARCHAR(10), BUZEI NUMBER(3),
  BLART VARCHAR(2), BLDAT DATE, BUDAT DATE, XBLNR VARCHAR(16),
  SHKZG VARCHAR(1), DMBTR NUMBER(15,2), WAERS VARCHAR(3),
  ZFBDT DATE, ZTERM VARCHAR(4), ZBD1T NUMBER(3),
  FAEDT DATE,                              -- net due date (ZFBDT + ZBD1T)
  MANST NUMBER(1),                         -- dunning level 0-4
  MADAT DATE,                              -- last dunned
  LOAD_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE OR REPLACE TABLE BSAD LIKE BSID;
ALTER TABLE BSAD ADD COLUMN AUGBL VARCHAR(10);
ALTER TABLE BSAD ADD COLUMN AUGDT DATE;     -- cleared on

CREATE OR REPLACE TABLE MHNK (            -- Dunning run: customer header
  LAUFD DATE, LAUFI VARCHAR(6), BUKRS VARCHAR(4), KUNNR VARCHAR(10),
  MAHNS NUMBER(1), SALDO NUMBER(15,2)      -- highest level, dunned balance
);
CREATE OR REPLACE TABLE MHND (            -- Dunning run: items
  LAUFD DATE, LAUFI VARCHAR(6), BUKRS VARCHAR(4), KUNNR VARCHAR(10),
  BELNR VARCHAR(10), GJAHR NUMBER(4), MAHNN NUMBER(1), DMBTR NUMBER(15,2)
);

CREATE OR REPLACE TABLE UDMCASEATTR00 (   -- FSCM dispute case attributes
  CASE_GUID VARCHAR(32), EXT_KEY VARCHAR(12),   -- case id (e.g. DSP0000123)
  BUKRS VARCHAR(4), KUNNR VARCHAR(10),
  XBLNR VARCHAR(16), BELNR VARCHAR(10),         -- disputed invoice
  ORIG_AMT NUMBER(15,2), DISP_AMT NUMBER(15,2), -- original / disputed amount
  STAT_ORDERNO VARCHAR(2),                      -- 10 New, 20 In Process, 30 Resolved, 40 Closed
  REASON VARCHAR(20),                           -- reason code as keyed by user (often blank / wrong)
  ROOT_CCODE VARCHAR(20),                       -- root cause code
  RESPONSIBLE VARCHAR(12),                      -- processor
  CREATE_DATE DATE, PLAN_END_DATE DATE, CLOSE_DATE DATE,
  LAST_ACTIVITY DATE
);

CREATE OR REPLACE TABLE UDM_DISPUTE_NOTES ( -- Case correspondence (customer emails, collector notes)
  NOTE_ID VARCHAR(16), EXT_KEY VARCHAR(12), KUNNR VARCHAR(10),
  NOTE_TYPE VARCHAR(10),                    -- EMAIL_IN, COLL_NOTE
  NOTE_DATE DATE, NOTE_TEXT VARCHAR,
  LOAD_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Ground truth from the generator (what the email actually means). Demo-only; SAP would not have this.
CREATE OR REPLACE TABLE DISPUTE_NOTE_LABELS (
  NOTE_ID VARCHAR(16), REASON_CODE VARCHAR(20), ROUTE_TO VARCHAR(12),
  INVOICE_REF VARCHAR(16), DISPUTED_AMOUNT NUMBER(15,2), IS_HARD BOOLEAN, HARD_TYPE VARCHAR(30)
);

CREATE OR REPLACE TABLE UDM_COLL_PROMISE (  -- Promise-to-pay
  PROMISE_ID VARCHAR(12), BUKRS VARCHAR(4), KUNNR VARCHAR(10), BUSAB VARCHAR(2),
  PROMISE_DATE DATE, PROMISED_AMT NUMBER(15,2), PAID_AMT NUMBER(15,2),
  STATUS VARCHAR(10)                         -- KEPT, BROKEN, OPEN
);
