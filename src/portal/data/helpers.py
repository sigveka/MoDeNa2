"""
Pure in-memory helper functions - no MongoDB/modena dependency.

These are separated so they can be unit-tested without a database connection.
"""


def get_parameter_table(model) -> list[dict]:
    """
    Build a list-of-dicts table joining model.parameters (positional list)
    with surrogateFunction.parameters (MapField, each entry has argPos).

    Returns rows sorted by argPos with keys: name, value, min, max, argPos.
    """
    sf_params = model.surrogateFunction.parameters  # MapField[name -> MinMaxArgPos]
    model_values = model.parameters                # ListField[float] - indexed by argPos

    rows = []
    for name, entry in sf_params.items():
        arg_pos = entry.argPos
        value = model_values[arg_pos] if arg_pos < len(model_values) else None
        rows.append({
            'name': name,
            'value': value,
            'min': entry.min,
            'max': entry.max,
            'argPos': arg_pos,
        })

    rows.sort(key=lambda r: r['argPos'])
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
