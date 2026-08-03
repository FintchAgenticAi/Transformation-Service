"""
Common rule contract for all transformation rules.

Every rule file must expose:

    def apply(data: dict, params: dict) -> dict:
        ...

- data: working record (dict of field -> value)
- params: values from transformation_rule_parameters
- return: updated data dict
"""

from typing import Callable

# Type alias for documentation / type hints
ApplyFn = Callable[[dict, dict], dict]


def apply_contract(data: dict, params: dict) -> dict:
    """Reference signature only — real rules implement their own apply()."""
    raise NotImplementedError("Each rule must implement apply(data, params)")
