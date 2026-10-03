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


#: Significant figures for every number the portal shows.  Full precision is
#: one hover away where it matters (Fit Data table).  Pages used to mix 3, 6,
#: 8 and 17 digits, so equal values looked different from page to page.
SIG_FIGS = 6


def fmt(value) -> str:
    """A number as the portal displays it: SIG_FIGS significant figures."""
    if value is None:
        return '—'
    return f'{value:.{SIG_FIGS}g}'


def plural(n: int, word: str, many: str | None = None) -> str:
    """'1 sample', '3 samples' -- instead of '3 sample(s)'."""
    return f'{n} {word if n == 1 else (many or word + "s")}'


def duration(seconds) -> str:
    """A run time for people: '42 s', '3 min', '1.5 h'."""
    if seconds is None:
        return '—'
    if seconds < 1:
        return '< 1 s'
    if seconds < 90:
        return f'{seconds:.0f} s'
    if seconds < 5400:
        return f'{seconds / 60:.0f} min'
    return f'{seconds / 3600:.1f} h'


def is_fixed(lo, hi) -> bool:
    """Whether a trained range is a single value, for practical purposes.

    Ranges grow by a hair when a point lands on the boundary -- flowRate's D
    is stored as 0.01 … 0.01000001 -- so exact equality misses the case the
    reader cares about: bounds that print the same.
    """
    if lo is None or hi is None:
        return False
    return hi - lo <= 1e-6 * max(abs(lo), abs(hi))


def unit_text(entry) -> str | None:
    """The declared unit of an input or output, or None when undeclared.

    Units are Phase 1a of TODO.md: ``unit`` (coherent SI), with optional
    ``quantity`` and ``displayUnit``.  Undeclared is not dimensionless --
    ``"1"`` is -- so callers show None as "—", never as a blank unit.  Read
    with getattr so the portal shows units as soon as the schema has them.
    """
    unit = getattr(entry, 'unit', None)
    if not unit:
        return None
    quantity = getattr(entry, 'quantity', None)
    return f'{unit} ({quantity})' if quantity else unit


def with_unit(name: str, entry) -> str:
    """'p0 [Pa]' for axis titles and column headers; 'p0' when undeclared."""
    unit = getattr(entry, 'unit', None) if entry is not None else None
    return f'{name} [{unit}]' if unit else name


def ordered_names(mapping) -> list[str]:
    """Input/output names in argPos order (declaration order when absent)."""
    items = list(mapping.items())
    return [k for k, _ in sorted(
        items, key=lambda kv: (getattr(kv[1], 'argPos', None) is None,
                               getattr(kv[1], 'argPos', None) or 0))]


def residual_sample(index: int, n_outputs: int) -> tuple[int, int]:
    """(sample, output position) of residual *index*.

    SurrogateModel.error() yields one residual per output for each sample in
    turn, so residuals are sample-major.
    """
    n_outputs = max(n_outputs, 1)
    return index // n_outputs, index % n_outputs


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
