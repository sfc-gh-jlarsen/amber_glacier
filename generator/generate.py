"""Synthetic SAP FI-AR / FSCM history for Northwind Industrial.

Usage (local):     python generator/generate.py [--connection <name>]
Usage (Snowsight): run in a Workspace; get_active_session() is used automatically.
Options: --as-of 2026-10-26 --months 18 --customers 1200 --hard-rate 0.15 --seed 42
"""
import argparse
import logging
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent)) if "__file__" in globals() else None
import dispute_text as dt  # noqa: E402

log = logging.getLogger("generator")
DB, SCHEMA = "OFFICEHOURS_20261027", "SAP_FINANCIALS"

BUKRS = {"US01": ("USA", "USD"), "CA01": ("CAN", "CAD"), "DE01": ("DEU", "EUR"), "MX01": ("MEX", "MXN")}
FX_USD = {"USD": 1.0, "CAD": 0.73, "EUR": 1.08, "MXN": 0.055}
REGIONS = {
    "USA": [("TX", "Houston"), ("AZ", "Phoenix"), ("NM", "Albuquerque"), ("OH", "Columbus"), ("IL", "Chicago"),
            ("GA", "Atlanta"), ("CA", "Fresno"), ("PA", "Pittsburgh"), ("MN", "St. Paul"), ("NC", "Charlotte")],
    "CAN": [("ON", "Toronto"), ("QC", "Montreal"), ("AB", "Calgary"), ("BC", "Vancouver")],
    "DEU": [("BY", "München"), ("NW", "Köln"), ("BW", "Stuttgart"), ("HH", "Hamburg")],
    "MEX": [("NL", "Monterrey"), ("JA", "Guadalajara"), ("CMX", "Ciudad de México")],
}
PROMO_REGIONS = {"TX", "AZ", "NM"}         # planted promo-deduction spike
COLLECTOR_BY_REGION = {"TX": "C3", "AZ": "C3", "NM": "C3", "OH": "C1", "IL": "C1", "PA": "C1", "MN": "C1",
                       "GA": "C2", "NC": "C2", "CA": "C2"}
PREFIX = ["Apex", "Summit", "Keystone", "Ridgeline", "Ironwood", "Bluewater", "Crescent", "Granite", "Pioneer",
          "Sterling", "Harbor", "Northgate", "Cedar", "Falcon", "Liberty", "Meridian", "Oakridge", "Prairie",
          "Redstone", "Silverline", "Trident", "Union", "Vanguard", "Westfield", "Allied", "Beacon", "Cobalt"]
NOUN = ["Fabrication", "Industrial Supply", "Mechanical", "Distribution", "Manufacturing", "Equipment",
        "Process Systems", "Fluid Power", "Construction", "Automotive", "Energy Services", "Packaging"]
SUFFIX = {"USA": ["Inc.", "LLC", "Corp.", "Co."], "CAN": ["Ltd.", "Inc."], "DEU": ["GmbH", "AG"],
          "MEX": ["S.A. de C.V."]}
KUKLA = ["01", "02", "03", "04", "05"]
ZTERM = {"NT30": 30, "NT45": 45, "NT60": 60, "2N10": 30}
DISPUTE_MIX = {"PRICING": .17, "PROMO_DEDUCTION": .10, "SHORT_SHIPMENT": .14, "DAMAGED_GOODS": .12,
               "DUPLICATE_BILLING": .05, "MISSING_POD": .09, "TAX_EXEMPT": .06, "ALREADY_PAID": .13,
               "QUALITY": .08, "OTHER": .06}
DUP_RUN_DATE = None  # set relative to as_of


def get_session(connection):
    try:
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except Exception:
        from snowflake.snowpark import Session
        builder = Session.builder
        return (builder.config("connection_name", connection) if connection else builder).create()


# --------------------------------------------------------------------------- customers
def gen_customers(n, rng, prng):
    rows, knb1, cms, used = [], [], [], set()
    land_choice = rng.choice(list(BUKRS), size=n, p=[.62, .14, .14, .10])
    size = rng.lognormal(0, 1.0, n)                     # relative customer size
    for i in range(n):
        bukrs = land_choice[i]
        land1 = BUKRS[bukrs][0]
        regio, city = REGIONS[land1][rng.integers(len(REGIONS[land1]))]
        while True:
            name = f"{prng.choice(PREFIX)} {prng.choice(NOUN)} {prng.choice(SUFFIX[land1])}"
            if name not in used:
                used.add(name)
                break
            name = None
        kunnr = f"{100000 + i:010d}"
        rows.append(dict(KUNNR=kunnr, NAME1=name, LAND1=land1, REGIO=regio, ORT01=city,
                         KUKLA=prng.choice(KUKLA), ERDAT=date(2018, 1, 1) + timedelta(days=int(rng.integers(0, 2500)))))
        codes = [bukrs] + (["US01"] if bukrs != "US01" and rng.random() < .25 else [])
        for b in codes:
            zt = rng.choice(list(ZTERM), p=[.5, .2, .2, .1])
            busab = COLLECTOR_BY_REGION.get(regio, {"CAN": "C4", "DEU": "C5", "MEX": "C4"}.get(land1, "C2"))
            knb1.append(dict(KUNNR=kunnr, BUKRS=b, AKONT="0000121000", ZTERM=zt, BUSAB=busab))
    cust = pd.DataFrame(rows)
    cust["SIZE"] = size
    cust["AVG_DELAY"] = np.clip(rng.normal(4, 9, n), -8, 45)   # days paid after due, per customer
    knb1 = pd.DataFrame(knb1)
    for _, r in knb1.iterrows():
        c = cust.loc[cust.KUNNR == r.KUNNR].iloc[0]
        risk = "A" if c.AVG_DELAY < 0 else "B" if c.AVG_DELAY < 6 else "C" if c.AVG_DELAY < 15 else "D" if c.AVG_DELAY < 25 else "E"
        cms.append(dict(PARTNER=r.KUNNR, CREDIT_SGMNT=r.BUKRS, RISK_CLASS=risk,
                        CREDIT_LIMIT=round(float(c.SIZE) * 60000 / FX_USD[BUKRS[r.BUKRS][1]], -3),
                        CREDIT_SCORE=int(np.clip(85 - c.AVG_DELAY * 1.6 + rng.normal(0, 6), 5, 99)),
                        WAERS=BUKRS[r.BUKRS][1]))
    return cust, knb1, pd.DataFrame(cms)


# --------------------------------------------------------------------------- invoices + payments
def gen_invoices(cust, knb1, start, as_of, rng):
    days = (as_of - start).days
    k = knb1.merge(cust[["KUNNR", "SIZE", "AVG_DELAY", "REGIO"]], on="KUNNR")
    lam = 6.0 * k.SIZE.clip(0.2, 6) * days / 30.0
    n = rng.poisson(lam)
    idx = np.repeat(k.index.values, n)
    inv = k.loc[idx].reset_index(drop=True)
    inv["BLDAT"] = [start + timedelta(days=int(d)) for d in rng.integers(0, days, len(inv))]
    waers = inv.BUKRS.map(lambda b: BUKRS[b][1])
    usd = rng.lognormal(7.6, 0.9, len(inv)) * inv.SIZE.clip(0.3, 4) ** 0.5
    inv["WAERS"] = waers
    inv["DMBTR"] = (usd / waers.map(FX_USD)).round(2)
    inv["ZBD1T"] = inv.ZTERM.map(ZTERM)
    inv["FAEDT"] = [b + timedelta(days=int(z)) for b, z in zip(inv.BLDAT, inv.ZBD1T)]
    t_frac = np.array([(b - start).days / days for b in inv.BLDAT])
    delay = rng.normal(inv.AVG_DELAY + 11 * t_frac, 8)          # payment behavior worsens over time (DSO creep)
    tail = rng.random(len(inv)) < 0.03 + 0.05 * t_frac           # growing slow-pay tail
    delay = (delay + np.where(tail, rng.exponential(45, len(inv)), 0)).round()
    inv["PAY_DT"] = [max(b + timedelta(days=1), f + timedelta(days=int(d)))
                     for b, f, d in zip(inv.BLDAT, inv.FAEDT, delay)]
    inv = inv.sort_values("BLDAT").reset_index(drop=True)
    inv["BELNR"] = [f"{90000000 + i:010d}" for i in range(len(inv))]
    inv["XBLNR"] = [f"9{4100000 + i}" for i in range(len(inv))]
    inv["BLART"] = "RV"
    return inv


def plant_deterioration(inv, cust, as_of, rng):
    """Three large US customers stop paying on time ~110 days ago."""
    top = cust[cust.LAND1 == "USA"].nlargest(20, "SIZE").sample(3, random_state=7).KUNNR.tolist()
    m = inv.KUNNR.isin(top) & (inv.BLDAT >= as_of - timedelta(days=125))
    inv.loc[m, "PAY_DT"] = [f + timedelta(days=int(d)) for f, d in zip(inv.loc[m, "FAEDT"], rng.integers(70, 120, m.sum()))]
    log.info("Deteriorating customers: %s", top)
    return top


def plant_duplicates(inv, as_of, rng):
    """A bad billing run re-issues 40 invoices on a single day."""
    run = as_of - timedelta(days=41)
    src = inv[(inv.BLDAT >= run - timedelta(days=20)) & (inv.BLDAT < run) & (inv.BUKRS == "US01")].sample(40, random_state=3)
    dup = src.copy()
    dup["BLDAT"] = run
    dup["FAEDT"] = [run + timedelta(days=int(z)) for z in dup.ZBD1T]
    dup["PAY_DT"] = pd.NaT
    start = int(inv.BELNR.max()) + 1
    dup["BELNR"] = [f"{start + i:010d}" for i in range(len(dup))]
    dup["XBLNR"] = [f"9{4100000 + int(b) - 90000000}" for b in dup.BELNR]
    dup["DUP_OF"] = src.XBLNR.values
    out = pd.concat([inv, dup], ignore_index=True)
    out["DUP_OF"] = out.get("DUP_OF")
    return out, run


# --------------------------------------------------------------------------- disputes
def gen_disputes(inv, cust, as_of, promo_start, dup_run, prng, rng, hard_rate):
    cmap = cust.set_index("KUNNR")
    p = np.full(len(inv), 0.035)
    promo = inv.REGIO.isin(PROMO_REGIONS).values & (inv.BLDAT >= promo_start).values
    p[promo] = 0.20
    is_dup = inv.DUP_OF.notna().values
    p[is_dup] = 1.0
    pick = rng.random(len(inv)) < p
    cases, notes, labels = [], [], []
    for n_case, (i, r) in enumerate(inv[pick].iterrows()):
        if is_dup[i]:
            reason = "DUPLICATE_BILLING"
        elif promo[i]:
            reason = prng.choices(["PROMO_DEDUCTION", "PRICING"], [.7, .3])[0]
        else:
            reason = prng.choices(list(DISPUTE_MIX), list(DISPUTE_MIX.values()))[0]
        create = r.BLDAT + timedelta(days=prng.randint(3, 10) if is_dup[i] else prng.randint(8, 50))
        if create > as_of:
            continue
        frac = 1.0 if reason in ("DUPLICATE_BILLING", "ALREADY_PAID", "MISSING_POD", "OTHER", "TAX_EXEMPT") else prng.uniform(.05, .45)
        if reason == "TAX_EXEMPT":
            frac = 0.07
        disp_amt = round(float(r.DMBTR) * frac, 2)
        dur = int(rng.exponential(45))
        close = create + timedelta(days=dur)
        is_open = close > as_of
        stat = ("10" if (as_of - create).days < 5 else "20") if is_open else prng.choice(["30", "40"])
        ext = f"DSP{n_case + 1:07d}"
        c = cmap.loc[r.KUNNR]
        em = dt.make_email(reason, r.XBLNR, disp_amt, r.WAERS, c.LAND1, c.NAME1, prng, hard_rate=hard_rate)
        nid = f"N{len(notes) + 1:09d}"
        notes.append(dict(NOTE_ID=nid, EXT_KEY=ext, KUNNR=r.KUNNR, NOTE_TYPE="EMAIL_IN", NOTE_DATE=create, NOTE_TEXT=em["text"]))
        labels.append(dict(NOTE_ID=nid, REASON_CODE=em["reason"], ROUTE_TO=dt.ROUTE[em["reason"]],
                           INVOICE_REF=em["invoice_ref"], DISPUTED_AMOUNT=em["disputed_amount"],
                           IS_HARD=em["is_hard"], HARD_TYPE=em["hard_type"]))
        last = create
        stale = is_open and prng.random() < 0.35
        if not stale and prng.random() < 0.55:
            d = min(as_of, create + timedelta(days=prng.randint(2, 20)))
            notes.append(dict(NOTE_ID=f"N{len(notes) + 1:09d}", EXT_KEY=ext, KUNNR=r.KUNNR, NOTE_TYPE="COLL_NOTE",
                              NOTE_DATE=d, NOTE_TEXT=dt.make_coll_note(em["reason"], r.XBLNR, prng)))
            last = max(last, d)
        if not stale and prng.random() < 0.25:
            d = min(as_of, create + timedelta(days=prng.randint(10, 30)))
            notes.append(dict(NOTE_ID=f"N{len(notes) + 1:09d}", EXT_KEY=ext, KUNNR=r.KUNNR, NOTE_TYPE="EMAIL_FUP",
                              NOTE_DATE=d, NOTE_TEXT=dt.make_followup(r.XBLNR, prng)))
            last = max(last, d)
        keyed = prng.random()   # what the processor typed into SAP: often blank or wrong
        keyed_reason = "" if keyed < .55 else em["reason"] if keyed < .85 else prng.choice(dt.REASONS)
        cases.append(dict(CASE_GUID=f"{int(rng.integers(0, 2**62)):032x}", EXT_KEY=ext, BUKRS=r.BUKRS, KUNNR=r.KUNNR,
                          XBLNR=r.XBLNR, BELNR=r.BELNR, ORIG_AMT=float(r.DMBTR), DISP_AMT=disp_amt,
                          STAT_ORDERNO=stat, REASON=keyed_reason or None,
                          ROOT_CCODE=None if is_open else em["reason"],
                          RESPONSIBLE=f"PROC_{r.BUSAB}", CREATE_DATE=create,
                          PLAN_END_DATE=create + timedelta(days=30), CLOSE_DATE=None if is_open else close,
                          LAST_ACTIVITY=last, _OPEN=is_open))
    return pd.DataFrame(cases), pd.DataFrame(notes), pd.DataFrame(labels)


def apply_dispute_payments(inv, cases):
    """Open disputes keep the invoice open; closed disputes clear it at close date."""
    c = cases.set_index("BELNR")
    m = inv.BELNR.isin(c.index)
    for i in inv[m].index:
        cs = c.loc[inv.at[i, "BELNR"]]
        inv.at[i, "PAY_DT"] = pd.NaT if cs._OPEN else max(inv.at[i, "PAY_DT"], cs.CLOSE_DATE) if pd.notna(inv.at[i, "PAY_DT"]) else cs.CLOSE_DATE
    return inv


# --------------------------------------------------------------------------- dunning + promises
def dunning_level(days_overdue):
    return np.select([days_overdue > 60, days_overdue > 30, days_overdue > 15, days_overdue > 0], [4, 3, 2, 1], 0)


def gen_dunning(inv, as_of):
    runs = [as_of - timedelta(days=(as_of.weekday()) + 7 * w) for w in range(8)]
    hdr, items = [], []
    pay = pd.to_datetime(inv.PAY_DT)
    for k, d in enumerate(sorted(runs)):
        dts = pd.Timestamp(d)
        open_m = (pd.to_datetime(inv.BLDAT) <= dts) & (pay.isna() | (pay > dts))
        od = (dts - pd.to_datetime(inv.FAEDT[open_m])).dt.days
        sub = inv[open_m].assign(MAHNN=dunning_level(od.values))
        sub = sub[sub.MAHNN > 0]
        laufi = f"W{k + 1:02d}"
        items.append(pd.DataFrame(dict(LAUFD=d, LAUFI=laufi, BUKRS=sub.BUKRS, KUNNR=sub.KUNNR, BELNR=sub.BELNR,
                                       GJAHR=[b.year for b in sub.BLDAT], MAHNN=sub.MAHNN, DMBTR=sub.DMBTR)))
        g = sub.groupby(["BUKRS", "KUNNR"]).agg(MAHNS=("MAHNN", "max"), SALDO=("DMBTR", "sum")).reset_index()
        g["LAUFD"], g["LAUFI"] = d, laufi
        hdr.append(g)
    return pd.concat(hdr, ignore_index=True), pd.concat(items, ignore_index=True), max(runs)


def gen_promises(inv, knb1, as_of, prng, rng):
    pay = pd.to_datetime(inv.PAY_DT)
    rows = []
    for w in range(13):
        d = as_of - timedelta(days=7 * w + 3)
        dts = pd.Timestamp(d)
        pastdue = inv[(pd.to_datetime(inv.FAEDT) < dts) & (pay.isna() | (pay > dts))]
        bal = pastdue.groupby(["BUKRS", "KUNNR", "BUSAB"]).DMBTR.sum().reset_index()
        for _, r in bal.sample(min(len(bal), 30), random_state=w).iterrows():
            pdte = d + timedelta(days=prng.randint(5, 14))
            amt = round(float(r.DMBTR) * prng.uniform(.3, 1.0), 2)
            if pdte > as_of:
                status, paid = "OPEN", 0.0
            else:
                broken = prng.random() < (.55 if r.BUSAB == "C3" else .15)
                status = "BROKEN" if broken else "KEPT"
                paid = round(amt * prng.uniform(0, .4), 2) if broken else amt
            rows.append(dict(PROMISE_ID=f"PTP{len(rows) + 1:07d}", BUKRS=r.BUKRS, KUNNR=r.KUNNR, BUSAB=r.BUSAB,
                             PROMISE_DATE=pdte, PROMISED_AMT=amt, PAID_AMT=paid, STATUS=status))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- SAP tables
def to_sap(inv, as_of, last_dun, dun_items):
    pay = pd.to_datetime(inv.PAY_DT)
    cleared = pay.notna() & (pay <= pd.Timestamp(as_of))
    gjahr = [b.year for b in inv.BLDAT]
    common = pd.DataFrame(dict(
        BUKRS=inv.BUKRS, KUNNR=inv.KUNNR, GJAHR=gjahr, BELNR=inv.BELNR, BUZEI=1, BLART=inv.BLART,
        BLDAT=inv.BLDAT, BUDAT=inv.BLDAT, XBLNR=inv.XBLNR, SHKZG="S", DMBTR=inv.DMBTR, WAERS=inv.WAERS,
        ZFBDT=inv.BLDAT, ZTERM=inv.ZTERM, ZBD1T=inv.ZBD1T, FAEDT=inv.FAEDT))
    # clearing doc: one payment per customer per pay date
    pay_keys = inv.loc[cleared, ["BUKRS", "KUNNR"]].assign(D=pay[cleared].dt.date)
    uniq = pay_keys.drop_duplicates().reset_index(drop=True)
    uniq["AUGBL"] = [f"{1400000000 + i:010d}" for i in range(len(uniq))]
    augbl = pay_keys.merge(uniq, on=["BUKRS", "KUNNR", "D"], how="left").AUGBL.values

    last = dun_items[dun_items.LAUFD == last_dun].set_index("BELNR").MAHNN
    bsid = common[~cleared].copy()
    bsid["MANST"] = bsid.BELNR.map(last).fillna(0).astype(int)
    bsid["MADAT"] = [last_dun if m > 0 else None for m in bsid.MANST]
    bsad = common[cleared].copy()
    bsad["MANST"], bsad["MADAT"] = 0, None
    bsad["AUGBL"], bsad["AUGDT"] = augbl, pay[cleared].dt.date.values

    bkpf_rv = pd.DataFrame(dict(BUKRS=inv.BUKRS, BELNR=inv.BELNR, GJAHR=gjahr, BLART="RV", BLDAT=inv.BLDAT,
                                BUDAT=inv.BLDAT, XBLNR=inv.XBLNR, WAERS=inv.WAERS, USNAM="BATCH_SD",
                                BKTXT=np.where(inv.DUP_OF.notna(), "Billing run BR-DUP", "Billing")))
    pay_amt = bsad.groupby("AUGBL").agg(BUKRS=("BUKRS", "first"), KUNNR=("KUNNR", "first"),
                                        AUGDT=("AUGDT", "first"), DMBTR=("DMBTR", "sum"), WAERS=("WAERS", "first")).reset_index()
    bkpf_dz = pd.DataFrame(dict(BUKRS=pay_amt.BUKRS, BELNR=pay_amt.AUGBL, GJAHR=[d.year for d in pay_amt.AUGDT],
                                BLART="DZ", BLDAT=pay_amt.AUGDT, BUDAT=pay_amt.AUGDT, XBLNR=None,
                                WAERS=pay_amt.WAERS, USNAM="LOCKBOX", BKTXT="Incoming payment"))
    bkpf = pd.concat([bkpf_rv, bkpf_dz], ignore_index=True)

    seg_rv = common[["BUKRS", "BELNR", "GJAHR", "BUZEI", "KUNNR", "SHKZG", "DMBTR", "ZFBDT", "ZTERM", "ZBD1T"]].copy()
    seg_rv["WRBTR"] = seg_rv.DMBTR
    seg_rv["AUGBL"] = pd.Series(index=common.index, dtype=object)
    seg_rv.loc[cleared, "AUGBL"] = augbl
    seg_rv["AUGDT"] = [p.date() if c else None for p, c in zip(pay, cleared)]
    seg_dz = pd.DataFrame(dict(BUKRS=pay_amt.BUKRS, BELNR=pay_amt.AUGBL, GJAHR=[d.year for d in pay_amt.AUGDT],
                               BUZEI=1, KUNNR=pay_amt.KUNNR, SHKZG="H", DMBTR=pay_amt.DMBTR, WRBTR=pay_amt.DMBTR,
                               ZFBDT=pay_amt.AUGDT, ZTERM=None, ZBD1T=None, AUGBL=pay_amt.AUGBL, AUGDT=pay_amt.AUGDT))
    bseg = pd.concat([seg_rv, seg_dz], ignore_index=True)
    bseg["KOART"], bseg["SGTXT"] = "D", None
    return bkpf, bseg, bsid, bsad


def _dates_to_obj(df):
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.date
    return df


def load(session, name, df):
    df = _dates_to_obj(df.copy())
    df = df[[c for c in df.columns if df[c].notna().any()]]  # all-null cols: let the table default to NULL
    df.columns = [c.upper() for c in df.columns]
    session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.{name}").collect()
    session.write_pandas(df, name, database=DB, schema=SCHEMA, auto_create_table=False, overwrite=False,
                         use_logical_type=True)
    log.info("Loaded %-20s %8d rows", name, len(df))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection", default=None, help="connection name in connections.toml (default: your default connection)")
    ap.add_argument("--as-of", default=str(date.today()))
    ap.add_argument("--months", type=int, default=18)
    ap.add_argument("--customers", type=int, default=1200)
    ap.add_argument("--hard-rate", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    as_of = date.fromisoformat(a.as_of)
    start = as_of - timedelta(days=int(a.months * 30.4))
    rng, prng = np.random.default_rng(a.seed), random.Random(a.seed)

    cust, knb1, cms = gen_customers(a.customers, rng, prng)
    inv = gen_invoices(cust, knb1, start, as_of, rng)
    deteriorating = plant_deterioration(inv, cust, as_of, rng)
    inv, dup_run = plant_duplicates(inv, as_of, rng)
    promo_start = as_of - timedelta(days=56)
    cases, notes, labels = gen_disputes(inv, cust, as_of, promo_start, dup_run, prng, rng, a.hard_rate)
    inv = apply_dispute_payments(inv, cases)
    mhnk, mhnd, last_dun = gen_dunning(inv, as_of)
    promises = gen_promises(inv, knb1, as_of, prng, rng)
    bkpf, bseg, bsid, bsad = to_sap(inv, as_of, last_dun, mhnd)

    log.info("as_of=%s invoices=%d open=%d disputes=%d notes=%d hard=%.1f%% promises=%d",
             as_of, len(inv), len(bsid), len(cases), len(notes), 100 * labels.IS_HARD.mean(), len(promises))
    if a.dry_run:
        return
    session = get_session(a.connection)
    session.sql("USE WAREHOUSE OFFICEHOURS_WH").collect()
    fx = pd.DataFrame(dict(WAERS=list(FX_USD), USD_RATE=list(FX_USD.values())))
    session.sql(f"CREATE OR REPLACE TABLE {DB}.{SCHEMA}.FX_RATES (WAERS VARCHAR(3), USD_RATE FLOAT)").collect()
    meta = pd.DataFrame([dict(K="AS_OF", V=str(as_of)), dict(K="DETERIORATING", V=",".join(deteriorating)),
                         dict(K="DUP_RUN_DATE", V=str(dup_run)), dict(K="PROMO_START", V=str(promo_start)),
                         dict(K="HARD_RATE", V=str(a.hard_rate)), dict(K="SEED", V=str(a.seed))])
    session.sql(f"CREATE OR REPLACE TABLE {DB}.{SCHEMA}.GENERATOR_META (K VARCHAR, V VARCHAR)").collect()
    for name, df in [("FX_RATES", fx), ("GENERATOR_META", meta),
                     ("KNA1", cust.drop(columns=["SIZE", "AVG_DELAY"])), ("KNB1", knb1), ("UKMBP_CMS_SGM", cms),
                     ("BKPF", bkpf), ("BSEG", bseg), ("BSID", bsid), ("BSAD", bsad), ("MHNK", mhnk), ("MHND", mhnd),
                     ("UDMCASEATTR00", cases.drop(columns=["_OPEN"])), ("UDM_DISPUTE_NOTES", notes),
                     ("DISPUTE_NOTE_LABELS", labels), ("UDM_COLL_PROMISE", promises)]:
        load(session, name, df)


if __name__ == "__main__":
    main()
