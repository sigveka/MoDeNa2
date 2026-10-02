"""Status badge component for surrogate model training state.

One rule, used by the Overview, Library and Detail pages alike.  It was
written out three times, which is how the copies could drift.
"""
from pathlib import Path
import dash_bootstrap_components as dbc

_COLOURS = {'Untrained': 'danger', 'Library missing': 'warning', 'Trained': 'success'}


def status_string(model) -> str:
    """Return the model's training status as plain text:

      - "Untrained"        no fitted parameters
      - "Library missing"  fitted, but the compiled surrogate library is not
                           on this machine (and loading could not rebuild it)
      - "Trained"          fitted and the library is present
    """
    if not model.parameters:
        return "Untrained"
    lib = getattr(model.surrogateFunction, 'libraryName', None)
    if lib and Path(lib).is_file():
        return "Trained"
    return "Library missing"


def status_badge(model):
    """The same status as a coloured dbc.Badge."""
    status = status_string(model)
    return dbc.Badge(status, color=_COLOURS[status])
