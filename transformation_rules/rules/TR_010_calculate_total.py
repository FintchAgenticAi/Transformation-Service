"""TR_010 — Calculate Total (A + B = C)."""


def apply(data: dict, params: dict) -> dict:
    """
    Compute total = amount + tax.

    params:
      amount_field (default: amount) — input A
      tax_field    (default: tax)    — input B
      total_field  (default: total)  — output C
    """
    result = dict(data)
    amount_field = params.get("amount_field") or "amount"
    tax_field = params.get("tax_field") or "tax"
    total_field = params.get("total_field") or "total"

    if amount_field not in result:
        raise ValueError(f"TR_010 missing input field '{amount_field}'")
    if tax_field not in result:
        raise ValueError(f"TR_010 missing input field '{tax_field}'")

    amount = float(result[amount_field])
    tax = float(result[tax_field])
    result[total_field] = amount + tax
    return result
