"""
Unit tests for data/queries.py helper functions.

These tests exercise only the pure in-memory logic (get_parameter_table,
transpose_fitdata) and do NOT require a MongoDB connection.

Run:
    python -m pytest src/portal/data/test_queries.py -v
"""
import pytest


# ---------------------------------------------------------------------------
# transpose_fitdata
# ---------------------------------------------------------------------------

from modena_portal.data.helpers import transpose_fitdata


def test_transpose_empty():
    assert transpose_fitdata({}) == []


def test_transpose_single_col():
    data = {'x': [1.0, 2.0, 3.0]}
    rows = transpose_fitdata(data)
    assert rows == [{'x': 1.0}, {'x': 2.0}, {'x': 3.0}]


def test_transpose_multi_col():
    data = {'x': [1, 2], 'y': [10, 20], 'z': [100, 200]}
    rows = transpose_fitdata(data)
    assert len(rows) == 2
    assert rows[0] == {'x': 1, 'y': 10, 'z': 100}
    assert rows[1] == {'x': 2, 'y': 20, 'z': 200}


# ---------------------------------------------------------------------------
# get_parameter_table - tested with a mock model object
# ---------------------------------------------------------------------------

from modena_portal.data.helpers import get_parameter_table


class _Entry:
    def __init__(self, argPos, min_, max_):
        self.argPos = argPos
        self.min = min_
        self.max = max_


class _SurrogateFunction:
    def __init__(self, params):
        self.parameters = params


class _Model:
    def __init__(self, sf_params, values):
        self.surrogateFunction = _SurrogateFunction(sf_params)
        self.parameters = values


def test_parameter_table_basic():
    sf_params = {
        'R': _Entry(0, 0.0, 9e99),
    }
    model = _Model(sf_params, [287.0])
    rows = get_parameter_table(model)
    assert len(rows) == 1
    assert rows[0] == {
        'name': 'R',
        'value': 287.0,
        'min': 0.0,
        'max': 9e99,
        'argPos': 0,
    }


def test_parameter_table_sorted_by_argpos():
    sf_params = {
        'P1': _Entry(1, 0.0, 10.0),
        'P0': _Entry(0, 0.0, 10.0),
    }
    model = _Model(sf_params, [1.0, 2.0])
    rows = get_parameter_table(model)
    assert rows[0]['name'] == 'P0'
    assert rows[0]['value'] == 1.0
    assert rows[1]['name'] == 'P1'
    assert rows[1]['value'] == 2.0


def test_parameter_table_missing_value():
    # model.parameters is shorter than argPos - should return None
    sf_params = {
        'P0': _Entry(0, 0.0, 10.0),
        'P1': _Entry(1, 0.0, 10.0),
    }
    model = _Model(sf_params, [5.0])  # only one value, P1 is missing
    rows = get_parameter_table(model)
    assert rows[0]['value'] == 5.0
    assert rows[1]['value'] is None


def test_parameter_table_empty():
    model = _Model({}, [])
    assert get_parameter_table(model) == []
