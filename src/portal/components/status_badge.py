"""Status badge component for surrogate model training state."""
from pathlib import Path
import dash_bootstrap_components as dbc


def status_badge(model):
    """
    Return a dbc.Badge indicating model training status:
      - Untrained (red)   - parameters list is empty
      - Library missing (orange) - fitted but .so not found
      - Trained (green)   - fitted and library present
    """
    if not model.parameters:
        return dbc.Badge("Untrained", color="danger")

    lib = getattr(model.surrogateFunction, 'libraryName', None)
    if lib and Path(lib).is_file():
        return dbc.Badge("Trained", color="success")

    return dbc.Badge("Library missing", color="warning")


def status_string(model) -> str:
    """Return plain-text status for DataTable display."""
    if not model.parameters:
        return "Untrained"
    lib = getattr(model.surrogateFunction, 'libraryName', None)
    if lib and Path(lib).is_file():
        return "Trained"
    return "Library missing"
