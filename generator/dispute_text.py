"""Labeled dispute-correspondence generator.

Every email is written from a known reason code, so the label is ground truth.
A configurable share of emails are deliberately "hard" (multi-reason, misleading
keywords, PROMO-vs-PRICING and POD-vs-SHORT edge cases, quoted prior threads).
That share is the knob used to calibrate model accuracy into the target band.
"""
import random

POLICY_SHARE = 0.85  # share of hard cases that are policy-driven
# Mix of policy types, calibrated from pilot runs: mispick and compliance trip both models,
# restock and unapplied cash separate Haiku from Sonnet.
POLICY_WEIGHTS = {"POLICY_MISPICK": .12, "POLICY_RESTOCK": .25, "POLICY_COMPLIANCE": .22,
                  "POLICY_UNAPPLIED": .23, "POLICY_FREIGHT": .05, "POLICY_POD_QTY": .03}
REASONS = [
    "PRICING", "PROMO_DEDUCTION", "SHORT_SHIPMENT", "DAMAGED_GOODS", "DUPLICATE_BILLING",
    "MISSING_POD", "TAX_EXEMPT", "ALREADY_PAID", "QUALITY", "OTHER",
]
ROUTE = {
    "PRICING": "SALES", "PROMO_DEDUCTION": "SALES",
    "SHORT_SHIPMENT": "LOGISTICS", "DAMAGED_GOODS": "LOGISTICS", "MISSING_POD": "LOGISTICS",
    "QUALITY": "LOGISTICS",
    "DUPLICATE_BILLING": "BILLING", "TAX_EXEMPT": "BILLING",
    "ALREADY_PAID": "COLLECTIONS", "OTHER": "COLLECTIONS",
}

FIRST = ["Maria", "James", "Priya", "Tom", "Linda", "Kevin", "Ana", "Jürgen", "Carlos", "Sophie",
         "Raj", "Emily", "Luis", "Heike", "Derek", "Nicole", "Omar", "Grace", "Marco", "Tanya"]
LAST = ["Lopez", "Nguyen", "Schmidt", "Patel", "Brown", "Garcia", "Müller", "Kim", "O'Neil", "Rossi",
        "Fischer", "Hernandez", "Walsh", "Chen", "Becker", "Ramirez"]
TITLES = ["AP Specialist", "Accounts Payable", "AP Manager", "Controller", "Purchasing Lead",
          "Receiving Supervisor", "Finance Coordinator"]
PRODUCTS = ["hydraulic fittings", "steel brackets", "PVC conduit", "bearing assemblies", "filter cartridges",
            "gasket kits", "fasteners (M8)", "control valves", "copper tubing", "safety gloves"]

OPEN = ["Hi,", "Hello,", "Good morning,", "Hi team,", "To whom it may concern,", "Hello AR team,", "Hi there,", ""]
CLOSE = ["Thanks,", "Regards,", "Thank you,", "Best,", "Please advise.", "Appreciate your help,", "Thx"]

# Each body: (template, mentions_invoice, mentions_amount). Slots: inv amt po prod qty qty2 date pct
EASY = {
    "PRICING": [
        "Invoice {inv} is billed at a unit price that does not match our contract. PO {po} shows the agreed price for {prod}; we have short-paid {amt}, the difference.",
        "We are disputing {amt} on invoice {inv}. The price per unit on the invoice is higher than the price on our purchase order {po}.",
        "Your invoice {inv} reflects the old price list. Our contract pricing for {prod} took effect last quarter. Please issue a credit for {amt}.",
        "Price discrepancy on {inv}: invoiced price exceeds the quoted price we accepted. Variance is {amt}. Please correct and rebill.",
    ],
    "PROMO_DEDUCTION": [
        "We deducted {amt} from invoice {inv} for the Q3 promotional allowance agreed with your sales rep.",
        "Payment for {inv} is net of a {amt} trade promotion deduction (co-op advertising). Backup from the promo agreement is attached.",
        "Per the rebate program for {prod}, we took a {amt} deduction against {inv}. Please apply the promo credit on your side.",
        "Deduction of {amt} on {inv} is for the end-cap display allowance / MDF your team approved. Deal ID referenced in the remittance.",
    ],
    "SHORT_SHIPMENT": [
        "We were invoiced for {qty} units of {prod} on {inv} but only received {qty2}. We will pay for what was delivered and are disputing {amt}.",
        "Shipment for PO {po} arrived short one pallet. Invoice {inv} bills the full quantity. Disputed amount {amt}.",
        "Receiving counted {qty2} cases versus {qty} on the packing list for {inv}. Please credit {amt} for the missing product.",
        "Only part of the order arrived. The rest of the {prod} never showed up. We are holding {amt} on invoice {inv}.",
    ],
    "DAMAGED_GOODS": [
        "The {prod} on invoice {inv} arrived damaged: crushed cartons and bent parts. Photos attached. We are disputing {amt}.",
        "Freight was damaged in transit (noted on the delivery receipt). We refused the damaged items from {inv}; please credit {amt}.",
        "Several units from PO {po} were broken on arrival and unusable. Disputing {amt} on {inv} until we receive replacements or credit.",
        "Pallet was wet and the {prod} rusted through. Damage claim on {inv} for {amt}.",
    ],
    "DUPLICATE_BILLING": [
        "We have been billed twice for the same shipment. Invoice {inv} duplicates an invoice we already received and paid for PO {po}.",
        "{inv} appears to be a duplicate of an earlier invoice with identical quantities and amount ({amt}). Please cancel the duplicate.",
        "Same delivery, two invoices. We will only pay one. Please void {inv} ({amt}).",
        "Your system issued a second invoice for the same order on PO {po}. Disputing {inv} for {amt} as a duplicate.",
    ],
    "MISSING_POD": [
        "We have no record of receiving the goods on invoice {inv}. Please send a signed proof of delivery before we can pay {amt}.",
        "Receiving cannot locate this delivery. Can you provide the signed BOL / POD for {inv}?",
        "Before we release payment on {inv} we need proof of delivery; our dock has no receipt for PO {po}.",
        "Please provide POD documentation for {inv}. Without a signed delivery receipt we cannot approve {amt}.",
    ],
    "TAX_EXEMPT": [
        "Invoice {inv} includes sales tax of {amt}, but we are tax exempt. Our exemption certificate is on file; please reissue without tax.",
        "We should not be charged tax on {inv}. Resale certificate attached. Disputing the {amt} tax line.",
        "Tax was applied incorrectly on {inv}. We are a non-profit / exempt entity. Please remove {amt}.",
        "Our exemption certificate was renewed. Please credit the {amt} of tax billed on {inv}.",
    ],
    "ALREADY_PAID": [
        "Invoice {inv} was paid on {date} by ACH. Remittance attached. Please check your cash application and remove it from our statement.",
        "Our records show {inv} paid in full ({amt}) on {date}. Check number in the remittance. Please stop the dunning letters.",
        "This invoice is already paid. Payment of {amt} went out {date}. Please reconcile {inv}.",
        "We paid {inv} last month; it looks like the payment was applied to the wrong invoice on your side.",
    ],
    "QUALITY": [
        "The {prod} on {inv} fail our incoming inspection: out of spec tolerances. Quality report attached. Disputing {amt} pending RMA.",
        "Product from PO {po} does not meet the specification (wrong material grade). We are rejecting the lot and disputing {amt} on {inv}.",
        "High defect rate on the {prod} shipped under {inv}. Our QA team quarantined the batch. Holding {amt}.",
        "The parts work but the finish is defective and our customer rejected them. Please arrange a return; we dispute {amt} on {inv}.",
    ],
    "OTHER": [
        "We need a copy of invoice {inv}; we never received it in our AP inbox. Please resend to our new AP address.",
        "Please update our remit-to and bill-to address before we can process {inv}. Our vendor setup changed.",
        "Invoice {inv} is missing our PO number so our system rejected it. Please reissue with PO {po}.",
        "We are moving to a new ERP and payments will be delayed two weeks. No issue with {inv} itself.",
    ],
}

# Hard cases: (true_reason, hard_type, template). The *true* reason is the primary issue.
HARD = [
    ("DAMAGED_GOODS", "MISLEADING_KEYWORD",
     "We are not paying full price for product that arrived broken. Half the {prod} on {inv} were cracked when we opened the cartons. Taking {amt} off."),
    ("DAMAGED_GOODS", "MISLEADING_KEYWORD",
     "The pricing on {inv} is fine, that's not the issue. The issue is the freight carrier dropped the pallet and the {prod} are bent. Disputing {amt}."),
    ("ALREADY_PAID", "MISLEADING_KEYWORD",
     "Please don't send us a duplicate statement again. {inv} was paid on {date}, {amt} by wire. Your cash app team needs to find it."),
    ("PROMO_DEDUCTION", "PROMO_VS_PRICING",
     "Invoice {inv} shows the list price but our PO {po} was placed under the September price-protection allowance. Short-paid {amt}, the allowance amount."),
    ("PRICING", "PROMO_VS_PRICING",
     "We expected the promotional pricing to have ended and our standard contract price to apply. Instead {inv} is billed above contract. Difference {amt}."),
    ("PROMO_DEDUCTION", "PROMO_VS_PRICING",
     "Deducted {pct}% from {inv} ({amt}). That is the volume rebate tier we hit this quarter, which your rep said would be applied to the price."),
    ("MISSING_POD", "POD_VS_SHORT",
     "We can't confirm we received everything on {inv}. Our receiving log is incomplete. Can you send the signed delivery receipt so we can match it?"),
    ("SHORT_SHIPMENT", "POD_VS_SHORT",
     "The POD you sent for {inv} is signed, but it shows {qty2} pallets and you billed {qty}. We only pay for what was signed for. Disputing {amt}."),
    ("DUPLICATE_BILLING", "MULTI_REASON",
     "{inv} is a duplicate of an invoice we already paid for PO {po}. Separately, a few cartons in that shipment were dented, but we're not claiming for that. Please void the duplicate ({amt})."),
    ("QUALITY", "MULTI_REASON",
     "Holding {amt} on {inv}. The {prod} fail spec (hardness out of tolerance). Also, I think the delivery was a day late, but the real problem is the quality."),
    ("TAX_EXEMPT", "MULTI_REASON",
     "Two things on {inv}: the PO number is missing, which is annoying but fine. The bigger problem is you charged us {amt} tax and we are exempt. Please reissue without tax."),
    ("SHORT_SHIPMENT", "QUOTED_THREAD",
     "Following up below.\n\n> From: AR Team\n> We show {inv} as past due. Was this paid?\n\nNo, it was not paid, because we only got {qty2} of the {qty} units. We'll pay for what arrived. Disputing {amt}."),
    ("ALREADY_PAID", "QUOTED_THREAD",
     "See below.\n\n> Original message: we are disputing the price on {inv}.\n\nIgnore my earlier note. Sales sorted out the price and we paid the full {amt} on {date}. Please check your cash application."),
    ("PRICING", "IMPLICIT",
     "Your rep told us {prod} would be ${unit} each going forward. {inv} doesn't reflect that. Short-paid {amt}."),
    ("OTHER", "IMPLICIT",
     "We'd love to pay {inv}. We just need it sent to the right place first; it keeps going to an old mailbox."),
]

# Policy cases: the label follows Northwind's AR policy, which a generic prompt does not state.
# These are what genuinely separates models (and what prompt optimization can learn from labels).
POLICY = [
    ("SHORT_SHIPMENT", "POLICY_MISPICK",
     "You shipped the wrong item on {inv}: we ordered {prod} and received a different SKU. We can't use it. Not paying {amt} until the correct product arrives."),
    ("SHORT_SHIPMENT", "POLICY_MISPICK",
     "Mispick on PO {po}: half the cartons on {inv} are a different part number. Please send what we ordered; disputing {amt}."),
    ("PRICING", "POLICY_FREIGHT",
     "Invoice {inv} includes a freight charge of {amt}. Our terms are FOB destination / prepaid freight. Please remove it."),
    ("PRICING", "POLICY_FREIGHT",
     "We were charged a fuel surcharge and expedite fee on {inv} ({amt}) that nobody approved. Please credit."),
    ("PRICING", "POLICY_RESTOCK",
     "We returned the {prod} under RMA and you charged a {pct}% restocking fee on {inv} ({amt}). That was not in our agreement."),
    ("OTHER", "POLICY_COMPLIANCE",
     "Per our vendor compliance program, we deducted {amt} from {inv} for a late delivery / ASN non-compliance chargeback."),
    ("OTHER", "POLICY_COMPLIANCE",
     "Deduction of {amt} on {inv}: labeling non-compliance fine per our routing guide. Details are in the supplier portal."),
    ("SHORT_SHIPMENT", "POLICY_POD_QTY",
     "Please send the signed POD for {inv}. Our receiver only counted {qty2} of {qty} cases, so we're holding {amt}."),
    ("ALREADY_PAID", "POLICY_UNAPPLIED",
     "We sent a payment of {amt} referencing PO {po} instead of {inv}. It should be sitting unapplied on your side; please apply it."),
    ("SHORT_SHIPMENT", "POLICY_MISPICK",
     "The part numbers on the cartons for {inv} don't match the PO. Receiving rejected the {prod}; disputing {amt} until replacements ship."),
    ("SHORT_SHIPMENT", "POLICY_MISPICK",
     "Wrong size was sent on {inv}: we need the 3/4 inch {prod}, you shipped 1/2 inch. Holding {amt}."),
    ("OTHER", "POLICY_COMPLIANCE",
     "Chargeback {amt} on {inv}: shipment arrived outside the delivery window in our retailer allowance program."),
    ("OTHER", "POLICY_COMPLIANCE",
     "We applied an on-time-in-full penalty of {pct}% ({amt}) against {inv}, per the supplier scorecard terms."),
    ("PRICING", "POLICY_FREIGHT",
     "The delivered cost on {inv} is higher than quoted because shipping was added ({amt}). Our quote was delivered pricing."),
    ("PRICING", "POLICY_FREIGHT",
     "Please remove the {amt} pallet and handling fee on {inv}; it isn't in our agreement."),
    ("PRICING", "POLICY_RESTOCK",
     "Restocking charge of {amt} on {inv} for the returned {prod}. Your rep waived this when we agreed to the return."),
    ("ALREADY_PAID", "POLICY_UNAPPLIED",
     "Our remittance for last week's payment listed the wrong invoice numbers. {inv} is covered by that payment ({amt}); please re-apply the cash."),
    ("ALREADY_PAID", "POLICY_UNAPPLIED",
     "We took a credit memo you issued in August against {inv}. That credit covers {amt} of this balance."),
    ("MISSING_POD", "POLICY_POD_QTY",
     "Can you send the signed POD for {inv}? Our receiver isn't sure the whole order came in, and AP won't release {amt} without it."),
]

DE_EASY = {
    "PRICING": "Der Preis auf Rechnung {inv} entspricht nicht unserem Rahmenvertrag. Wir kürzen um {amt}.",
    "SHORT_SHIPMENT": "Lieferung zu Rechnung {inv} war unvollständig. Es fehlen Teile; wir beanstanden {amt}.",
    "DAMAGED_GOODS": "Die Ware zu Rechnung {inv} kam beschädigt an. Fotos anbei. Reklamation über {amt}.",
    "DUPLICATE_BILLING": "Rechnung {inv} wurde doppelt gestellt. Bitte stornieren ({amt}).",
    "ALREADY_PAID": "Rechnung {inv} wurde am {date} bereits bezahlt ({amt}). Bitte Zahlungseingang prüfen.",
    "QUALITY": "Die Teile zu {inv} entsprechen nicht der Spezifikation. Wir halten {amt} zurück.",
}
ES_EASY = {
    "PRICING": "El precio en la factura {inv} no coincide con nuestro contrato. Descontamos {amt}.",
    "MISSING_POD": "No tenemos registro de recepción de la factura {inv}. Favor de enviar la prueba de entrega firmada.",
    "TAX_EXEMPT": "La factura {inv} incluye IVA por {amt} pero estamos exentos. Favor de refacturar.",
    "PROMO_DEDUCTION": "Descontamos {amt} de la factura {inv} por la promoción acordada con su vendedor.",
    "DAMAGED_GOODS": "La mercancía de la factura {inv} llegó dañada. Reclamamos {amt}.",
    "ALREADY_PAID": "La factura {inv} ya fue pagada el {date} por {amt}. Favor de verificar.",
}

COLL_NOTES = [
    "Called AP ({name}). Says {inv} is on hold pending {issue}. Follow up {day}.",
    "Left VM for {name}. Sent statement copy.",
    "Customer confirmed dispute on {inv}. Routed to {route}.",
    "Spoke with {name}, promised payment of undisputed balance by {day}.",
    "Emailed {route} for backup docs on {inv}. No response yet.",
]
ISSUE = {"PRICING": "price correction", "PROMO_DEDUCTION": "promo backup", "SHORT_SHIPMENT": "short ship credit",
         "DAMAGED_GOODS": "damage claim", "DUPLICATE_BILLING": "duplicate void", "MISSING_POD": "POD",
         "TAX_EXEMPT": "tax cert", "ALREADY_PAID": "cash app research", "QUALITY": "RMA", "OTHER": "AP setup"}

FUP = ["Any update on {inv}?", "Following up again on this dispute.", "Still waiting to hear back on {inv}.",
       "Please advise status. We'd like to close this out."]


def _fmt_amt(amt, waers, rng):
    if waers == "EUR":
        s = f"{amt:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return rng.choice([f"EUR {s}", f"{s} EUR", f"€{s}"])
    if waers == "MXN":
        return rng.choice([f"MXN {amt:,.2f}", f"${amt:,.2f} MXN"])
    sym = "CAD " if waers == "CAD" else "$"
    return rng.choice([f"{sym}{amt:,.2f}", f"{amt:,.2f} {waers}", f"{sym}{amt:,.0f}"])


def make_email(reason, inv, amt, waers, land1, company, rng: random.Random, hard_rate=0.15, force_hard=None):
    """Return dict(text, reason, invoice_ref, disputed_amount, is_hard, hard_type)."""
    slots = dict(
        inv=inv, amt=_fmt_amt(amt, waers, rng), po=f"PO-{rng.randint(40000, 89999)}",
        prod=rng.choice(PRODUCTS), qty=(q := rng.randint(20, 400)), qty2=max(1, q - rng.randint(5, q // 2 + 5)),
        date=f"{rng.randint(1, 12)}/{rng.randint(1, 28)}", pct=rng.choice([2, 3, 5]),
        unit=f"{rng.uniform(4, 60):.2f}",
    )
    is_hard = force_hard if force_hard is not None else (rng.random() < hard_rate)
    hard_type = None
    if is_hard and rng.random() < POLICY_SHARE:
        ptype = rng.choices(list(POLICY_WEIGHTS), list(POLICY_WEIGHTS.values()))[0]
        reason, hard_type, body = rng.choice([p for p in POLICY if p[1] == ptype])
    elif is_hard:
        cands = [h for h in HARD if h[0] == reason] or HARD
        reason, hard_type, body = rng.choice(cands)
    elif land1 == "DEU" and reason in DE_EASY and rng.random() < 0.35:
        body = DE_EASY[reason]
    elif land1 == "MEX" and reason in ES_EASY and rng.random() < 0.35:
        body = ES_EASY[reason]
    else:
        body = rng.choice(EASY[reason])
    text_body = body.format(**slots)
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    sig = f"{name}\n{rng.choice(TITLES)}, {company}"
    text = "\n\n".join(p for p in [rng.choice(OPEN), text_body, f"{rng.choice(CLOSE)}\n{sig}"] if p)
    if rng.random() < 0.08:  # light noise: lowercase / missing punctuation, as real email has
        text = text.replace(". ", " ").lower() if rng.random() < 0.5 else text.replace(",", "")
    return dict(
        text=text, reason=reason,
        invoice_ref=inv if inv in text else None,
        disputed_amount=round(amt, 2) if ("{amt}" in body) else None,
        is_hard=is_hard, hard_type=hard_type,
    )


def make_coll_note(reason, inv, rng):
    t = rng.choice(COLL_NOTES)
    return t.format(name=rng.choice(FIRST), inv=inv, issue=ISSUE[reason], route=ROUTE[reason].title(),
                    day=rng.choice(["Mon", "Tue", "Wed", "Thu", "Fri"]))


def make_followup(inv, rng):
    return rng.choice(FUP).format(inv=inv)
