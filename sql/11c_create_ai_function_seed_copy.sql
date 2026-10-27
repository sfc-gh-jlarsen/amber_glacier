CREATE OR REPLACE AI FUNCTION OFFICEHOURS_20261027.SAP_FINANCIALS.CLASSIFY_DISPUTE_SEED(NOTE_TEXT VARCHAR)
RETURNS VARCHAR
COMMENT = 'Classify an AR dispute email into a Northwind SAP dispute reason code'
AS
$$
    SELECT AI_COMPLETE(
    model=>'claude-haiku-4-5',
    messages=>ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
            'role', 'system',
            'content', 'You are an accounts receivable dispute analyst. Read the customer correspondence and classify the primary dispute reason. Reason codes: PRICING (invoiced price differs from contract/PO price); PROMO_DEDUCTION (customer deducted for a promotion, rebate, trade allowance, co-op or MDF); SHORT_SHIPMENT (fewer goods received than invoiced); DAMAGED_GOODS (goods arrived damaged); DUPLICATE_BILLING (invoiced twice for the same delivery); MISSING_POD (customer asks for proof of delivery); TAX_EXEMPT (tax charged to an exempt customer); ALREADY_PAID (customer says the invoice is already paid); QUALITY (goods do not meet specification); OTHER (anything else). Respond with exactly one reason code.'
        ),
        OBJECT_CONSTRUCT(
            'role', 'user',
            'content', 'Customer correspondence:

' || NOTE_TEXT
        )
    ),
    response_format=>PARSE_JSON('{
    "type": "json",
    "schema": {
        "type": "object",
        "properties": {
            "reason_code": {
                "type": "string",
                "description": "One of PRICING, PROMO_DEDUCTION, SHORT_SHIPMENT, DAMAGED_GOODS, DUPLICATE_BILLING, MISSING_POD, TAX_EXEMPT, ALREADY_PAID, QUALITY, OTHER"
            }
        },
        "required": [
            "reason_code"
        ],
        "additionalProperties": false
    }
}')
):reason_code::VARCHAR
$$;
