"""
Pure in-memory helper functions - no MongoDB/modena dependency.

These are separated so they can be unit-tested without a database connection.
"""


def get_parameter_table(model) -> list[dict]:
    """
    Build a list-of-dicts table of the model's fitted parameters.

    Post Phase 3, ``model.parameters`` is a dict keyed by declared name;
    ``surrogateFunction.parameters`` provides the bounds and argPos
    (dict-key insertion order).  Rows are returned in argPos order with
    keys: name, value, min, max, argPos.
    """
    sf_params = model.surrogateFunction.parameters  # MapField[name -> MinMax]
    fitted = model.parameters or {}                 # DictField[name -> float]

    rows = []
    for arg_pos, (name, entry) in enumerate(sf_params.items()):
        rows.append({
            'name': name,
            'value': fitted.get(name),
            'min': entry.min,
            'max': entry.max,
            'argPos': arg_pos,
        })
    return rows


def transpose_fitdata(fitdata: dict) -> list[dict]:
    """
    Convert {col: [val, ...]} → [{col: val, ...}] for DataTable rows.

    Guards against empty fitData.
    """
    if not fitdata:
        return []
    keys = list(fitdata.keys())
    n = len(fitdata[keys[0]])
    return [{k: fitdata[k][i] for k in keys} for i in range(n)]
