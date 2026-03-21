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


