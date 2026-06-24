import logging

logger = logging.getLogger(__name__)


def _resolve(context: dict, path: str):
    """Resolve dot-notation path into a nested dict."""
    parts = path.split('.')
    val = context
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return None
    return val


OPERATORS = {
    'eq': lambda a, b: a == b,
    'neq': lambda a, b: a != b,
    'lt': lambda a, b: float(a) < float(b),
    'lte': lambda a, b: float(a) <= float(b),
    'gt': lambda a, b: float(a) > float(b),
    'gte': lambda a, b: float(a) >= float(b),
    'contains': lambda a, b: (b in a) if isinstance(a, (list, str)) else False,
    'not_contains': lambda a, b: (b not in a) if isinstance(a, (list, str)) else True,
    'in': lambda a, b: (a in b) if isinstance(b, (list, tuple)) else False,
    'not_in': lambda a, b: (a not in b) if isinstance(b, (list, tuple)) else True,
    'is_null': lambda a, b: a is None,
    'is_not_null': lambda a, b: a is not None,
    'starts_with': lambda a, b: str(a).startswith(str(b)) if a is not None else False,
    'ends_with': lambda a, b: str(a).endswith(str(b)) if a is not None else False,
}


class ConditionEvaluator:
    @staticmethod
    def evaluate(conditions: list, context: dict, logic: str = 'AND') -> bool:
        if not conditions:
            return True

        results = []
        for cond in conditions:
            field = cond.get('field', '')
            operator = cond.get('operator', 'eq')
            value = cond.get('value')
            actual = _resolve(context, field)
            op_fn = OPERATORS.get(operator)
            if op_fn is None:
                logger.warning('Unknown workflow condition operator: %s', operator)
                results.append(False)
                continue
            try:
                results.append(bool(op_fn(actual, value)))
            except (TypeError, AttributeError, ValueError):
                results.append(False)

        if logic == 'OR':
            return any(results)
        return all(results)
