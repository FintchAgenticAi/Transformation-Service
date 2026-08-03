"""TR_002 — Trim Whitespace."""


def apply(data: dict, params: dict) -> dict:
    """
    Trim leading/trailing spaces from a text field.

    params:
      column_name (required): field name in data to trim
    """
    result = dict(data)
    column = params.get("column_name")
    if not column:
        raise ValueError("TR_002 requires param 'column_name'")

    if column in result and result[column] is not None:
        result[column] = str(result[column]).strip()
    return result
