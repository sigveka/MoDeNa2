"""
Single MongoDB boundary - all MongoEngine calls live here.

Import config first so MODENA_URI is set before modena connects.
"""
import modena_portal.config  # noqa: F401 - side-effect: sets MODENA_URI

from modena.SurrogateModel import SurrogateModel
from modena_portal.data.helpers import get_parameter_table, transpose_fitdata  # noqa: F401 re-export

__all__ = [
    'list_models',
    'list_model_sample_counts',
    'get_model',
    'get_fitdata',
    'get_sample_count',
    'initial_design_size',
    'get_parameter_table',
    'transpose_fitdata',
]


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------

def list_models():
    """Return all models without fitData (lightweight listing)."""
    return list(SurrogateModel.objects.exclude('fitData').select_related())


def list_model_sample_counts() -> dict[str, int]:
    """
    Return {model_id: n_samples} without loading fitData arrays.

    Uses a MongoDB aggregation that reads only the size of the first
    fitData column, which equals the number of training samples.
    """
    col = SurrogateModel._get_collection()
    result = {}
    for doc in col.aggregate([
        {"$project": {
            "pair": {"$arrayElemAt": [
                {"$objectToArray": {"$ifNull": ["$fitData", {}]}}, 0
            ]},
        }},
        {"$project": {
            "n": {"$size": {"$ifNull": ["$pair.v", []]}},
        }},
    ]):
        result[str(doc["_id"])] = doc["n"]
    return result


def get_model(model_id: str):
    """Return a single model by _id, without fitData."""
    return SurrogateModel.objects.exclude('fitData').get(_id=model_id)


def get_fitdata(model_id: str):
    """Return only the fitData field for a model."""
    return SurrogateModel.objects.only('fitData').get(_id=model_id)


def get_sample_count(model_id: str) -> int:
    """Number of stored samples for one model, without loading fitData."""
    return list_model_sample_counts().get(model_id, 0)


def initial_design_size(model) -> int | None:
    """How many of the first stored samples came from the initial design.

    Initialisation runs before anything else is collected, so the first N
    samples are the initial design and the rest arrived later (out-of-bounds
    expansion, error-driven sampling, requests from the portal).  N is known
    for the strategies that fix their points up front; None otherwise.
    """
    try:
        strategy = model.initialisationStrategy()
    except Exception:                                          # noqa: BLE001
        return None
    kind = type(strategy).__name__
    if kind == 'InitialRange':
        return 10           # InitialRange.newPoints() always samples 10 points
    data = {'InitialPoints': 'initialPoints', 'InitialData': 'initialData'}.get(kind)
    points = strategy.get(data) if data else None
    if not points:
        return None
    return len(next(iter(points.values())))




def get_model_full(model_id: str):
    """Return a model with fitData AND its schema fields.

    ``get_fitdata`` uses ``.only('fitData')``, which strips inputs, outputs,
    parameters and surrogateFunction from the document.  That is fine for
    plotting the raw table, but anything that *evaluates* the surrogate needs
    the schema too, so diagnostics must not use it.
    """
    return SurrogateModel.load(model_id)
