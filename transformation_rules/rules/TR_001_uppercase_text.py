"""TR_001 — Uppercase Text."""


def apply(data: dict, params: dict) -> dict:
    """
    Convert a text field to uppercase.

    params:
      column_name (required): field name in data to uppercase
    """
    result = dict(data)
    column = params.get("column_name")
    if not column:
        raise ValueError("TR_001 requires param 'column_name'")

    if column in result and result[column] is not None:
        result[column] = str(result[column]).upper()
    return result
