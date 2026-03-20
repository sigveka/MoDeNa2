'''@cond
   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2026 MoDeNa Consortium, All rights reserved.

License
    This file is part of Modena.

    The Modena interface library is free software; you can redistribute it
    and/or modify it under the terms of the GNU Lesser General Public License
    as published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.
@endcond'''
"""
@namespace python.Strategy
@brief     Module providing strategies
@details

@author    Henrik Rusche
@author    Sigve Karolius
@author    Mandar Thombre
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

import abc
import sys
import copy
from datetime import datetime, timezone
import modena
from modena.Registry import ModelRegistry
#from fabric.tasks import Task
from fireworks import Firework, Workflow, FWAction, FireTaskBase, ScriptTask
from fireworks.utilities.fw_serializers import FWSerializable, \
    recursive_serialize, recursive_deserialize, serialize_fw
import fireworks.utilities.fw_serializers as fw_serializers
from fireworks.utilities.fw_utilities import explicit_serialize
from fireworks.utilities.fw_serializers import load_object
from collections import defaultdict
import numpy as np
from numpy import array
import math
from itertools import combinations
from numpy.random import choice, seed, permutation
from modena.ErrorMetrics import AbsoluteError, ErrorMetricBase
import logging
_log = logging.getLogger('modena.strategy')

# Declare classes loaded when using `from modena.Strategy import`
__all__ = (
# --> Base Classes for different types of Strategies
'StrategyBaseClass', 'InitialisationStrategy', 'OutOfBoundsStrategy',
'ImproveErrorStrategy', 'ParameterFittingStrategy',
# Acceptance criteria
'AcceptanceCriterionBase', 'MaxError',
#
'SamplingStrategy',
# Space-filling sampling strategies
'SpaceFillingStrategy', 'LatinHypercube', 'Halton', 'Sobol', 'RandomUniform',
# Constrained composition samplers
'CASTROSampling', 'ExpandedCASTROSampling',
# Residuals optimizers
'ResidualsOptimizer', 'TrustRegionReflective', 'LevenbergMarquardt', 'DogBox',
# Cross-validation strategies
'CrossValidationStrategy', 'Holdout', 'KFold', 'LeaveOneOut', 'LeavePOut',
'Jackknife',
# Initialisation Strategies
'EmptyInitialisationStrategy', 'InitialPoints', 'InitialRange', 'InitialData',
'RerunAllPoints',
# Parameter Estimation Strategies
'NonLinFitWithErrorContol',
# --> Base Classes for different MoDeNa FireTasks
'ModenaFireTask', 'EmptyFireTask',
# MoDeNa Fireworks
'BackwardMappingScriptTask',
# Exceptions
'ParametersNotValid', 'OutOfBounds', 'FatalModelError',
# OOB strategies
'ExtendSpaceStochasticSampling', 'ForbidOutOfBounds', 'ExtendSpaceExpandedCASTROSampling',
# Non-convergence strategies
'NonConvergenceStrategy', 'SkipPoint', 'FizzleOnFailure', 'DefuseWorkflowOnFailure',
)

##
# @addtogroup python_interface_library
# @{

class StrategyBaseClass(defaultdict, FWSerializable):
    """
    @brief   Base class for all strategies
    @details
             The purpose of the base class is to ensure that all strategy types
             used in MoDeNa are embedded correctly into the FireWorks workflow.
    """


    @abc.abstractmethod
    def newPoints(self, model):
        """Method which adds new points to the database."""
        raise NotImplementedError('newPoints not implemented!')


    @abc.abstractmethod
    def workflow(self, model):
        """
        @brief    Method which adds new points to the database.
        @details
                  f
        @param    model modena SurrogateModel object
        """
        raise NotImplementedError('workflow not implemented!')


    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        """
        @brief Required by FireWorks to deserialise objects
        """
        return dict(self)


    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        """
        @brief Required by FireWorks to serialise objects
        """
        return cls(m_dict)


    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


class InitialisationStrategy(StrategyBaseClass):
    """
    @brief    Parent class for the initialisation strategies.
    @details
              The purpose of the initialisation strategy is to initialise the
              surrogate model, i.e. compile the source code and obtain a set of
              validated parameters.
    """

    def __init__(self, *args, **kwargs):
        """
        @brief Constructor
        """
        dict.__init__(self, *args, **kwargs)


    def workflow(self, model):
        """
        @brief    Create a FireWorks Workflow object performing initialisation.
        @details
                  The workflow

        @param model surrogate model object.

        @return Workflow object
        """
        ## Call the newPoints method to receive a list of dictionaries each
        #  dictionary representing one data point.
        p = self.newPoints(model)

        if p:
            wf = model.exactTasks(p)
            wf.append_wf(
                model.parameterFittingStrategy().workflow(model),
                wf.leaf_fw_ids
            )
            return wf

        elif not p and len(model.substituteModels):
            wf = Workflow([ Firework( [ EmptyFireTask() ],
                                      name=f'{model._id} — init (substitute models)') ])
            for sm in model.substituteModels:
                wf.append_wf(
                    sm.initialisationStrategy().workflow(sm),
                    []
                )
            return wf

        else:
            return Workflow([ Firework( [EmptyFireTask()],
                                        name=f'{model._id} — init (no-op)') ])


class OutOfBoundsStrategy(StrategyBaseClass):
    """
    @brief    Base class for the out of bounds strategies.
    @details
              Classes inheriting this class must implement the newPoints
    """
    def __init__(self, *args, **kwargs):
        """Constructor"""
        dict.__init__(self, *args, **kwargs)



    def workflow(self, model, **kwargs):
        """
        @brief    Generating a workflow
        @details
                  The workflow generated
                  1. Extend and sample domain
                  2. Perform detailed simulations
                  3. Perform parameter fitting
        @returns wf Workflow object.
        """
        wf = model.exactTasks(self.newPoints(model, **kwargs))
        wf.append_wf(
            model.parameterFittingStrategy().workflow(model),
            wf.leaf_fw_ids
        )
        return wf


class ImproveErrorStrategy(StrategyBaseClass):
    """
    @brief    Base class for strategies 'fixing' the error of a surrogate model
    @details
              Im
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)


    def workflow(self, model, **kwargs):
        wf = model.exactTasks(self.newPoints(model))
        wf.append_wf(
            model.parameterFittingStrategy().workflow(model),
            wf.leaf_fw_ids
        )
        return wf

class ParameterEstimationStrategy(StrategyBaseClass):
    """
    @brief   Base Class for Parameter Estimation
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)


    def workflow(self, model):
        """
        @brief    Method returning the 'Workflow' to be executed by FireWorks
        @details
                  The Workflow is generated by the ParameterFitting FireTask
                  defined later in this document.
        """
        return Workflow(
            [
                Firework(
                    ParameterFitting(surrogateModelId=model._id),
                    name=f'{model._id} — fitting'
                )
            ]
        )


class ParameterFittingStrategy(StrategyBaseClass):
    """
    @brief   Base Class for creating parameter fitting strategies.
    """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)


    def workflow(self, model):
        return Workflow(
            [
                Firework(
                    ParameterFitting(surrogateModelId=model._id),
                    name=f'{model._id} — fitting'
                )
            ]
        )




class AcceptanceCriterionBase(defaultdict, FWSerializable):
    """
    @brief Base class for surrogate-fit acceptance criteria.

    Subclasses implement `accepts()` to decide whether a CV error is small
    enough to consider the fit valid.  The `metric` property returns the
    error metric used to compute per-sample residuals (default: AbsoluteError).
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    @abc.abstractmethod
    def accepts(self, error: float) -> bool:
        raise NotImplementedError

    @property
    def metric(self) -> ErrorMetricBase:
        return self.get('metric', AbsoluteError())

    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        return dict(self)

    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        return cls(m_dict)

    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


@explicit_serialize
class MaxError(AcceptanceCriterionBase):
    """
    @brief Accept if metric.aggregate(residuals) <= threshold.

    Constructor kwargs:
        threshold (float): maximum acceptable aggregated error.
        metric (ErrorMetricBase, optional): defaults to AbsoluteError().
    """

    def __init__(self, *args, **kwargs):
        AcceptanceCriterionBase.__init__(self, *args, **kwargs)

    def accepts(self, error: float) -> bool:
        return error <= self['threshold']


class SpaceFillingStrategy(defaultdict, FWSerializable):
    """
    @brief Base class for space-filling sampling strategies.

    Subclasses implement `sample(n, d)` returning an (n, d) array of points
    in [0, 1]^d.  Used by SamplingStrategy.samplePoints() as a plugin point.
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    @abc.abstractmethod
    def sample(self, n: int, d: int) -> np.ndarray:
        """Return (n, d) array of sample points in [0, 1]^d."""
        raise NotImplementedError

    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        return dict(self)

    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        return cls(m_dict)

    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


@explicit_serialize
class LatinHypercube(SpaceFillingStrategy):
    """Latin Hypercube sampling via scipy.stats.qmc."""

    def __init__(self, *args, **kwargs):
        SpaceFillingStrategy.__init__(self, *args, **kwargs)

    def sample(self, n: int, d: int) -> np.ndarray:
        from scipy.stats.qmc import LatinHypercube as _LHS
        return _LHS(d=d, seed=self.get('seed', None)).random(n)


@explicit_serialize
class Halton(SpaceFillingStrategy):
    """Halton quasi-random sequence via scipy.stats.qmc."""

    def __init__(self, *args, **kwargs):
        SpaceFillingStrategy.__init__(self, *args, **kwargs)

    def sample(self, n: int, d: int) -> np.ndarray:
        from scipy.stats.qmc import Halton as _H
        return _H(d=d, scramble=self.get('scramble', True),
                  seed=self.get('seed', None)).random(n)


@explicit_serialize
class Sobol(SpaceFillingStrategy):
    """Sobol quasi-random sequence via scipy.stats.qmc.

    n is rounded up to the next power of 2; the returned array is sliced
    back to n rows so the caller always gets exactly n points.
    """

    def __init__(self, *args, **kwargs):
        SpaceFillingStrategy.__init__(self, *args, **kwargs)

    def sample(self, n: int, d: int) -> np.ndarray:
        from scipy.stats.qmc import Sobol as _S
        m = max(1, math.ceil(math.log2(n))) if n > 1 else 1
        return _S(d=d, scramble=self.get('scramble', True),
                  seed=self.get('seed', None)).random_base2(m)[:n]


@explicit_serialize
class RandomUniform(SpaceFillingStrategy):
    """Uniform random sampling in [0, 1]^d."""

    def __init__(self, *args, **kwargs):
        SpaceFillingStrategy.__init__(self, *args, **kwargs)

    def sample(self, n: int, d: int) -> np.ndarray:
        rng = np.random.default_rng(self.get('seed', None))
        return rng.uniform(size=(n, d))


class ResidualsOptimizer(defaultdict, FWSerializable):
    """
    @brief Base class for non-linear least-squares optimizers.

    Subclasses implement `fit(residuals_fn, x0, bounds=None)` which minimises
    the sum of squared residuals and returns the optimised parameter array.
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    @abc.abstractmethod
    def fit(self, residuals_fn, x0, bounds=None) -> np.ndarray:
        """
        Minimise sum-of-squares of residuals_fn.

        Parameters
        ----------
        residuals_fn : callable
            Takes a 1-D parameter array and returns a 1-D residuals array.
        x0 : array-like
            Initial parameter guess.
        bounds : tuple (lb, ub) or None
            Lower and upper bound arrays.  Not all methods support bounds.

        Returns
        -------
        np.ndarray
            Optimised parameters.
        """
        raise NotImplementedError

    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        return dict(self)

    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        return cls(m_dict)

    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


@explicit_serialize
class TrustRegionReflective(ResidualsOptimizer):
    """Trust-Region Reflective optimizer (scipy least_squares, method='trf').

    Supports parameter bounds.  This is the default optimizer used by
    NonLinFitWithErrorContol.
    """

    def __init__(self, *args, **kwargs):
        ResidualsOptimizer.__init__(self, *args, **kwargs)

    def fit(self, residuals_fn, x0, bounds=None) -> np.ndarray:
        from scipy.optimize import least_squares
        kw = dict(fun=residuals_fn, x0=np.asarray(x0, dtype=float),
                  method='trf', ftol=self.get('ftol', 1e-8),
                  xtol=self.get('xtol', 1e-8),
                  max_nfev=self.get('max_nfev', None))
        if bounds is not None:
            kw['bounds'] = bounds
        return least_squares(**kw).x


@explicit_serialize
class LevenbergMarquardt(ResidualsOptimizer):
    """Levenberg-Marquardt optimizer (scipy least_squares, method='lm').

    Does NOT support parameter bounds (scipy limitation).  Bounds passed to
    fit() are silently ignored; use TrustRegionReflective when bounds are
    needed.
    """

    def __init__(self, *args, **kwargs):
        ResidualsOptimizer.__init__(self, *args, **kwargs)

    def fit(self, residuals_fn, x0, bounds=None) -> np.ndarray:
        from scipy.optimize import least_squares
        return least_squares(residuals_fn, np.asarray(x0, dtype=float),
                             method='lm', ftol=self.get('ftol', 1e-8),
                             xtol=self.get('xtol', 1e-8),
                             max_nfev=self.get('max_nfev', None)).x


@explicit_serialize
class DogBox(ResidualsOptimizer):
    """Dog-leg trust-region optimizer (scipy least_squares, method='dogbox').

    Supports parameter bounds.
    """

    def __init__(self, *args, **kwargs):
        ResidualsOptimizer.__init__(self, *args, **kwargs)

    def fit(self, residuals_fn, x0, bounds=None) -> np.ndarray:
        from scipy.optimize import least_squares
        kw = dict(fun=residuals_fn, x0=np.asarray(x0, dtype=float),
                  method='dogbox', ftol=self.get('ftol', 1e-8),
                  xtol=self.get('xtol', 1e-8),
                  max_nfev=self.get('max_nfev', None))
        if bounds is not None:
            kw['bounds'] = bounds
        return least_squares(**kw).x


class SamplingStrategy(StrategyBaseClass):
    """
    @brief    Base class for Sampling strategies (DoE).
    @details
              Sampling
    """


    def samplePoints(self, model, sr, nPoints):
        """
        @brief    Generate "n" sample points in a domain
        @details
                  The sample points are used as inputs to detailed simulations
        @param    model -- SurrogateModel -- Required | Surrogate Model
        @param    sr -- dictionary -- Required |
                  sample range: { 'key1': {'min': float, 'max': float}, ... }
        @param    nPoints -- int -- Required | Number of sample points
        @returns  dictionary
                  {'key1': [ * , ^ , < ] , 'key2': [ * , ^ , < ] , ... }
        """
        sampler = self.get('sampler', LatinHypercube())
        unit_points = sampler.sample(nPoints, len(sr))  # shape (nPoints, d)

        return {
            key: [
                sr[key]['min'] +
                (sr[key]['max'] - sr[key]['min']) * unit_points[i][j]
                for i in range(nPoints)
            ] for j, key in enumerate(sr)
        }


class CrossValidationStrategy(defaultdict, FWSerializable):
    """
    @brief Base class for cross-validation split strategies.

    Subclasses implement `splits(n)` yielding (train_idx, test_idx) pairs.
    `aggregate(fold_errors)` reduces per-fold errors to a single CV error
    (default: max; Jackknife overrides to mean).
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    @abc.abstractmethod
    def splits(self, n: int):
        """Yield (train_idx, test_idx) pairs for n samples."""
        raise NotImplementedError

    def aggregate(self, fold_errors) -> float:
        """Reduce per-fold errors to a single scalar (default: max)."""
        return max(fold_errors)

    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        return dict(self)

    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        return cls(m_dict)

    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


@explicit_serialize
class Holdout(CrossValidationStrategy):
    """
    @brief Single random train/test split (backward-compatible default).

    Constructor kwargs:
        testDataPercentage (float): fraction of samples held out for testing.
    """

    def __init__(self, *args, **kwargs):
        CrossValidationStrategy.__init__(self, *args, **kwargs)

    def splits(self, n: int):
        pct = self.get('testDataPercentage', 0.2)
        n_test = max(1, int(pct * n))
        test_idx = list(choice(n, size=n_test, replace=False))
        test_set = set(test_idx)
        train_idx = [i for i in range(n) if i not in test_set]
        yield train_idx, test_idx


@explicit_serialize
class KFold(CrossValidationStrategy):
    """
    @brief k-fold cross-validation (shuffled).

    Constructor kwargs:
        k (int): number of folds.
    """

    def __init__(self, *args, **kwargs):
        CrossValidationStrategy.__init__(self, *args, **kwargs)

    def splits(self, n: int):
        k = self['k']
        indices = list(permutation(n))
        fold_size = n // k
        for i in range(k):
            start = i * fold_size
            end = start + fold_size if i < k - 1 else n
            test_idx = indices[start:end]
            train_idx = indices[:start] + indices[end:]
            yield train_idx, test_idx


@explicit_serialize
class LeaveOneOut(CrossValidationStrategy):
    """
    @brief Leave-one-out cross-validation (N folds, each test set size 1).
    """

    def __init__(self, *args, **kwargs):
        CrossValidationStrategy.__init__(self, *args, **kwargs)

    def splits(self, n: int):
        for i in range(n):
            train_idx = [j for j in range(n) if j != i]
            test_idx = [i]
            yield train_idx, test_idx


@explicit_serialize
class LeavePOut(CrossValidationStrategy):
    """
    @brief Leave-p-out cross-validation (C(N,p) folds, each test set size p).

    Constructor kwargs:
        p (int): number of samples to hold out per fold.
    """

    def __init__(self, *args, **kwargs):
        CrossValidationStrategy.__init__(self, *args, **kwargs)

    _MAX_FOLDS = 1000

    def splits(self, n: int):
        p = self['p']
        n_folds = math.comb(n, p)
        if n_folds > self._MAX_FOLDS:
            raise ValueError(
                f'LeavePOut(p={p}) on {n} samples would produce {n_folds} folds '
                f'(limit is {self._MAX_FOLDS}). Use KFold or LeaveOneOut instead.'
            )
        for test_tuple in combinations(range(n), p):
            test_idx = list(test_tuple)
            test_set = set(test_idx)
            train_idx = [i for i in range(n) if i not in test_set]
            yield train_idx, test_idx


@explicit_serialize
class Jackknife(CrossValidationStrategy):
    """
    @brief Jackknife (LOO splits, mean aggregation for bias estimation).
    """

    def __init__(self, *args, **kwargs):
        CrossValidationStrategy.__init__(self, *args, **kwargs)

    def splits(self, n: int):
        for i in range(n):
            train_idx = [j for j in range(n) if j != i]
            test_idx = [i]
            yield train_idx, test_idx

    def aggregate(self, fold_errors) -> float:
        return sum(fold_errors) / len(fold_errors)




@explicit_serialize
class InitialPoints(InitialisationStrategy):
    """
    @brief    Initialise by performing detailed simulations at a set of points.
    @details
              The sample data points are specified by the user as a dictionary,
    """

    def __init__(self, *args, **kwargs):
        InitialisationStrategy.__init__(self, *args, **kwargs)


    def newPoints(self, model):
        return self['initialPoints']


@explicit_serialize
class InitialRange(InitialisationStrategy, SamplingStrategy):
    """
    @brief    Initialise by performing detailed simulations inside a range
    @details
              The range specified by the user is sampled using LHS sampling.
    """

    def __init__(self, *args, **kwargs):
        InitialisationStrategy.__init__(self, *args, **kwargs)


    def newPoints(self, model):
        """
        @brief Range
        @param model MoDeNa surrogate model
        """
        sampleRange = self['initialRange']
        return self.samplePoints(model, sampleRange, 10)#self['nNewPoints']


@explicit_serialize
class InitialData(InitialisationStrategy):
    """
    @brief    Initialise a SurrogateModel given a dataset of input-output data
    @details
              The purpose of this strategy is to initialise a surrogate model
              by providing a set of initial data-points, this can be results
              from validated simulations data or experimental data.

              The idea is to instantiate a surrogate model in a domain where
              the input-output behaviour is known and let the framework handle
              the expansion of the surrogate model beyond the initial domain.
    """

    def __init__(self, *args, **kwargs):
        InitialisationStrategy.__init__(self, *args, **kwargs)


    def newPoints(self, model):
        """
        @brief    Function providing the user-specified initial points.
        @details
                  This strategy requires that the data points are given in a
                  dictionary structure.
        @returns  List
        """
        return self['initialData']


    def workflow(self, model):
        """
        """
        # Get initial data
        points = self.newPoints(model)

        # Save initial data in database
        model.updateFitDataFromFwSpec(points)
        model.updateMinMax()
        model.save()

        wf = Workflow( [], name='initialising to dataset')
        wf.append_wf( model.parameterFittingStrategy().workflow(model),
                      wf.leaf_fw_ids)

        return wf


@explicit_serialize
class EmptyInitialisationStrategy(InitialisationStrategy):
    """
    @brief    Empty initialisation strategy, used by Forward Mapping Models.
    @details
              The strategy is used in SurrogateModel.ForwardMappingModel as the
              default initialisation strategy. The reason is that the parent
              class requires a surrogate model to implement an initialisation
              strategy.
    """
    def newPoints(self, model):
        return [ ]


@explicit_serialize
class RerunAllPoints(InitialisationStrategy):
    """
    @brief    Re-run detailed simulations for all previously stored fit data points.
    @details
              This strategy retrieves all input points currently stored in the
              model's fitData and re-submits them as exact tasks, followed by
              parameter fitting. It is useful when the detailed simulation code
              has changed and all results need to be regenerated without
              altering the sampled design space.
    """

    def __init__(self, *args, **kwargs):
        InitialisationStrategy.__init__(self, *args, **kwargs)


    def newPoints(self, model):
        """
        @brief    Return all points currently stored in the model's fitData.
        @details
                  Reconstructs a list of input-point dicts from the column-
                  oriented fitData store, one dict per sample.
        @param    model MoDeNa surrogate model
        @returns  List of dicts, each representing one data point.
        """
        model.reload('fitData')
        keys = list(model.fitData.keys())
        if not keys:
            return []
        n = len(model.fitData[keys[0]])
        return [
            {k: model.fitData[k][i] for k in keys}
            for i in range(n)
        ]


@explicit_serialize
class ExtendSpaceStochasticSampling(OutOfBoundsStrategy, SamplingStrategy):
    """
    @brief    Class for extending the design space using stochastic sampling.
    @details
              Strategy used to extend the domain of a surrogate model.
              All inputs are sampled independently via LHS — use only for
              models with no composition constraints (Σ xi = 1).
    """
    def __init__(self, *args, **kwargs):
        OutOfBoundsStrategy.__init__(self, *args, **kwargs)


    def newPoints(self, model, **kwargs):
        # Get a sampling range around the outside point and create points
        sampleRange, limitPoint = model.extendedRange(kwargs['outsidePoint'])
        sp = self.samplePoints(model, sampleRange, self['nNewPoints']-1)
        return  { k: v + [limitPoint[k]] for k, v in sp.items() }


@explicit_serialize
class ForbidOutOfBounds(OutOfBoundsStrategy):
    """Raise FatalModelError for any OOB event.

    Use for models where ALL inputs are composition-constrained and expanding
    the domain is physically meaningless (e.g. pure-composition viscosity or
    density surrogates with fixed T, p).

    Any OOB query signals a mismatch between the model's declared bounds and
    the application's usage range.  The user must widen the initial bounds in
    the model definition — OOB expansion cannot adjust coupled composition
    bounds without re-solving the entire feasibility simplex.
    """

    def __init__(self, *args, **kwargs):
        OutOfBoundsStrategy.__init__(self, *args, **kwargs)

    def newPoints(self, model, **kwargs):
        outsidePoint = kwargs['outsidePoint']
        oob = {
            k: v for k, v in outsidePoint.items()
            if v < model.inputs[k].min or v > model.inputs[k].max
        }
        raise FatalModelError(
            f"Model '{model._id}': out-of-bounds query is not permitted — "
            f"OOB input(s): "
            + ', '.join(
                f"'{k}'={v:.6g} (bounds=["
                f"{model.inputs[k].min:.6g}, {model.inputs[k].max:.6g}])"
                for k, v in oob.items()
            )
            + ". Widen the initial input bounds in the model definition."
        )


@explicit_serialize
class ExtendSpaceExpandedCASTROSampling(OutOfBoundsStrategy):
    """OOB strategy for mixed scalar + composition-constrained models.

    Scalar inputs (e.g. T, p) may expand when an OOB event is triggered.
    Composition inputs listed in ``compositionGroup`` must never trigger OOB
    — if they do, ``FatalModelError`` is raised with an actionable message
    telling the user to widen the initial composition bounds.

    ``nNewPoints - 1`` joint (scalar, composition) samples are generated in
    the extended scalar domain using LHS for scalars and CASTRO for
    compositions.  The limit point (the actual OOB boundary value for each
    scalar, paired with one valid composition) is appended as the n-th point
    to guarantee coverage of the new extremity.

    Parameters
    ----------
    compositionGroup : dict
        ``{'free': ['x_N2', 'x_O2'], 'dependent': 'x_Ar'}``
        Same semantics as ``ExpandedCASTROSampling`` / ``CASTROSampling``.
    nNewPoints : int
        Total new training points to return, including the limit point.
    nOversample : int, optional
        Oversampling factor for CASTRO and LHS candidates.
        Defaults to ``max(50, 5 * nNewPoints)``.
    seed : int or None, optional
        RNG seed.
    """

    def __init__(self, *args, **kwargs):
        OutOfBoundsStrategy.__init__(self, *args, **kwargs)

    def newPoints(self, model, **kwargs):
        from scipy.stats.qmc import LatinHypercube as _LHS

        outsidePoint = kwargs['outsidePoint']
        group     = self['compositionGroup']
        free_keys = list(group['free'])
        dep_key   = str(group['dependent'])
        comp_set  = set(free_keys) | {dep_key}

        # Guard: composition inputs must never trigger OOB
        for k, v in outsidePoint.items():
            if k in comp_set:
                if v < model.inputs[k].min or v > model.inputs[k].max:
                    raise FatalModelError(
                        f"Model '{model._id}': composition input '{k}' is out of "
                        f"bounds (value={v:.6g}, bounds=["
                        f"{model.inputs[k].min:.6g}, {model.inputs[k].max:.6g}]). "
                        f"OOB expansion cannot adjust composition bounds — widen "
                        f"the initial '{k}' bounds in the model definition."
                    )

        # Extended scalar bounds for OOB scalars; compositions unchanged
        sampleRange, limitPoint = model.extendedRange(outsidePoint)

        n_total  = int(self['nNewPoints'])
        n_sample = max(1, n_total - 1)   # one slot reserved for the limit point
        n_over   = int(self.get('nOversample', max(50, 5 * n_sample)))
        rng      = np.random.default_rng(self.get('seed', None))

        scalar_keys = [k for k in model.inputs.keys() if k not in comp_set]

        # --- Sample scalar inputs via LHS in extended range ---
        if scalar_keys:
            d_s = len(scalar_keys)
            unit_s = _LHS(d=d_s, seed=int(rng.integers(0, 2**31))).random(n_over)
            s_lbs = np.array([sampleRange[k]['min'] for k in scalar_keys])
            s_ubs = np.array([sampleRange[k]['max'] for k in scalar_keys])
            scalar_samples = s_lbs + (s_ubs - s_lbs) * unit_s   # (n_over, d_s)
        else:
            scalar_samples = np.empty((n_over, 0))

        # --- Sample compositions via CASTRO (original model bounds) ---
        comp_bounds = CASTROSampling._get_bounds(model)
        if 'dependentBounds' in group:
            comp_bounds[dep_key] = dict(group['dependentBounds'])
        elif dep_key not in comp_bounds:
            comp_bounds[dep_key] = {'min': 0.0, 'max': 1.0}

        _castro = CASTROSampling(
            compositionGroup=group,
            nNewPoints=n_sample,
            nOversample=n_over,
            seed=int(rng.integers(0, 2**31)),
            useExistingData=False,
        )
        comp_samples = _castro._sample_compositions(
            free_keys, dep_key, comp_bounds, n_sample,
        )  # (n_feas, len(free_keys) + 1)
        free_comp_samples = comp_samples[:, :len(free_keys)]   # drop dependent column

        # --- Pair and select via greedy maximin ---
        n_pairs = min(scalar_samples.shape[0], free_comp_samples.shape[0])
        idx_s = rng.permutation(scalar_samples.shape[0])[:n_pairs]
        idx_c = rng.permutation(free_comp_samples.shape[0])[:n_pairs]

        if scalar_keys:
            joint = np.column_stack([scalar_samples[idx_s], free_comp_samples[idx_c]])
        else:
            joint = free_comp_samples[idx_c]

        all_keys = scalar_keys + free_keys
        existing = CASTROSampling._load_existing(self, model, all_keys)
        selected = CASTROSampling._greedy_maximin(joint, existing, n_sample)

        result = {k: selected[:, j].tolist() for j, k in enumerate(all_keys)}

        # --- Limit point: scalar boundary values + one valid composition ---
        limit_comp = _castro._sample_compositions(free_keys, dep_key, comp_bounds, 1)
        for k in scalar_keys:
            result[k].append(limitPoint[k])
        for j, k in enumerate(free_keys):
            result[k].append(float(limit_comp[0, j]))

        return result


@explicit_serialize
class StochasticSampling(ImproveErrorStrategy, SamplingStrategy):
    """
    @brief    Design of Experiments class, Monte Carlo sampling.
    @details
    """
    def __init__(self, *args, **kwargs):
        ImproveErrorStrategy.__init__(self, *args, **kwargs)


    def newPoints(self, model):
        """
        @brief    Add samples to the current range if needed by ParFit.
        """
        # Get a sampling range from fitData. Note: Cannot use MinMax must not
        # be updated, yet
        sampleRange = {
            k: {
                'min': min(model.fitData[k]),
                'max': max(model.fitData[k])
            } for k in model.inputs.keys()
        }

        return self.samplePoints(model, sampleRange, self['nNewPoints'])


@explicit_serialize
class CASTROSampling(InitialisationStrategy, ImproveErrorStrategy):
    """
    Constrained LHS sampler for pure-composition inputs (Σ xi = 1, per-component bounds).

    Based on the CASTRO algorithm (Schenk & Haranczyk, arXiv:2407.16567):
    sequential conditional sampling with bound permutation and Euclidean-distance
    postprocessing against existing fitData.

    The algorithm loops over every permutation of the free-component order.  For
    each permutation it samples each component sequentially, shrinking the upper
    bound of each dimension by the running partial sum so that only feasible
    compositions (all bounds satisfied AND Σ xi = 1) are kept.  Iterating over
    all permutations avoids the bias that pure sequential sampling introduces
    (later dimensions would otherwise be systematically squeezed).

    After collecting all feasible candidates, ``nNewPoints`` are selected by a
    greedy maximin criterion: each successive point is chosen as the candidate
    farthest from the union of existing ``fitData`` and already-selected points.

    Parameters
    ----------
    compositionGroup : dict
        ``{'free': ['x_N2', 'x_O2', 'x_Ar'], 'dependent': 'x_CO2'}``

        *free*: names of the inputs to sample.
        *dependent*: name of the input computed as ``1 − Σ free``.
        All names must match keys in ``model.inputs``.
    nNewPoints : int
        Number of feasible composition vectors to return.
    nOversample : int, optional
        Candidate vectors generated per permutation before distance selection.
        Defaults to ``max(50, 5 * nNewPoints)``.
    seed : int or None, optional
        RNG seed.  ``None`` means non-deterministic.
    useExistingData : bool, optional
        If ``True`` (default) and ``fitData`` is non-empty, new points are
        selected to maximise distance from existing samples.  Set to ``False``
        to use maximin selection among candidates only.

    Usage
    -----
    As ``initialisationStrategy``::

        BackwardMappingModel(
            ...
            initialisationStrategy=Strategy.CASTROSampling(
                compositionGroup={'free': ['x_N2', 'x_O2'], 'dependent': 'x_Ar'},
                nNewPoints=20,
            ),
        )

    As ``improveErrorStrategy`` inside ``NonLinFitWithErrorContol``::

        Strategy.NonLinFitWithErrorContol(
            ...
            improveErrorStrategy=Strategy.CASTROSampling(
                compositionGroup={'free': ['x_N2', 'x_O2'], 'dependent': 'x_Ar'},
                nNewPoints=5,
            ),
        )
    """

    def __init__(self, *args, **kwargs):
        InitialisationStrategy.__init__(self, *args, **kwargs)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_bounds(model):
        """Return ``{name: {'min': float, 'max': float}}`` for every input."""
        return {k: {'min': v.min, 'max': v.max} for k, v in model.inputs.items()}

    def _sample_compositions(self, free_keys, dep_key, bounds, n_desired):
        """
        Run the CASTRO sequential conditional sampler with bound permutation.

        Returns an ``(n_feasible, len(free_keys) + 1)`` array.  Columns are
        ordered as ``[free_keys[0], ..., free_keys[-1], dep_key]``.
        Raises ``RuntimeError`` if no feasible point is found.
        """
        from itertools import permutations as _perms

        d = len(free_keys)
        lbs = np.array([bounds[k]['min'] for k in free_keys])
        ubs = np.array([bounds[k]['max'] for k in free_keys])
        dep_lb = bounds[dep_key]['min']
        dep_ub = bounds[dep_key]['max']

        n_over = int(self.get('nOversample', max(50, 5 * n_desired)))
        rng = np.random.default_rng(self.get('seed', None))

        all_feasible = []

        for perm in _perms(range(d)):
            # Sequential sampling in permuted order with adaptive upper bounds.
            # samples[:, dim] stores the value for the original dimension `dim`.
            samples = np.zeros((n_over, d))
            partial = np.zeros(n_over)
            alive = np.ones(n_over, dtype=bool)

            for step in range(d):
                dim = perm[step]
                lo = lbs[dim]
                # Effective upper bound: tighten by remaining budget
                hi_eff = np.minimum(ubs[dim], 1.0 - partial)
                # Rows where even the lower bound exceeds the remaining budget
                # are infeasible from this point on.
                alive &= (lo <= hi_eff)
                if not alive.any():
                    break

                u = rng.uniform(size=n_over)
                samples[:, dim] = np.where(
                    alive,
                    lo + (hi_eff - lo) * u,
                    0.0,
                )
                partial += samples[:, dim]

            if not alive.any():
                continue

            feasible = samples[alive]           # (n_feas, d), original column order
            dep_vals = 1.0 - feasible.sum(axis=1)
            ok = (dep_vals >= dep_lb) & (dep_vals <= dep_ub)
            if not ok.any():
                continue

            all_feasible.append(np.column_stack([feasible[ok], dep_vals[ok]]))

        if not all_feasible:
            raise RuntimeError(
                'CASTROSampling: no feasible compositions found. '
                'Verify that per-component bounds are compatible with Σ xi = 1.'
            )
        return np.vstack(all_feasible)

    @staticmethod
    def _greedy_maximin(candidates, reference, n_select):
        """
        Greedily select ``n_select`` rows from ``candidates`` that are
        maximally distant from ``reference`` (existing + already selected).

        Parameters
        ----------
        candidates : (n_cand, d) ndarray
        reference  : (n_ref, d) ndarray or None
        n_select   : int

        Returns
        -------
        (n_select, d) ndarray
        """
        from scipy.spatial.distance import cdist

        n_cand = candidates.shape[0]
        if n_select >= n_cand:
            return candidates

        if reference is None or reference.shape[0] == 0:
            # No reference — seed with the point closest to the centroid,
            # then greedily maximise pairwise distances.
            centroid = candidates.mean(axis=0, keepdims=True)
            seed_idx = int(cdist(candidates, centroid).argmin())
            ref = candidates[[seed_idx]]
            pool = list(range(n_cand))
            pool.remove(seed_idx)
            selected = [seed_idx]
        else:
            ref = reference.copy()
            pool = list(range(n_cand))
            selected = []

        for _ in range(n_select - len(selected)):
            if not pool:
                break
            d_to_ref = cdist(candidates[pool], ref).min(axis=1)
            best_local = int(np.argmax(d_to_ref))
            best = pool[best_local]
            selected.append(best)
            ref = np.vstack([ref, candidates[best]])
            pool.pop(best_local)

        return candidates[np.array(selected)]

    def _load_existing(self, model, all_keys):
        """
        Return an ``(n_exist, len(all_keys))`` array of previously collected
        fitData, or ``None`` if fitData is absent or incomplete.
        """
        if not self.get('useExistingData', True):
            return None
        try:
            model.reload('fitData')
            fd = model.fitData
            if not fd or not all(k in fd for k in all_keys):
                return None
            n = len(fd[all_keys[0]])
            if n == 0:
                return None
            return np.array([[fd[k][i] for k in all_keys] for i in range(n)])
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def newPoints(self, model):
        """
        Generate ``nNewPoints`` feasible composition vectors.

        The dependent component is **not** a model input — it is computed
        inside the surrogate C function as ``1 − Σ free``.  Its bounds are
        taken from ``compositionGroup['dependentBounds']`` (if provided) or
        from ``model.inputs`` (if the dependent key happens to be registered
        there), defaulting to ``[0, 1]``.

        Returns
        -------
        dict
            ``{input_name: [float, ...]}`` containing only the *free* inputs,
            ready to pass directly to ``model.exactTasks()``.
        """
        group = self['compositionGroup']
        free_keys = list(group['free'])
        dep_key = str(group['dependent'])
        n_desired = int(self.get('nNewPoints', 10))

        bounds = self._get_bounds(model)

        # Dependent-component bounds: explicit config > model.inputs > default
        if 'dependentBounds' in group:
            bounds[dep_key] = dict(group['dependentBounds'])
        elif dep_key not in bounds:
            bounds[dep_key] = {'min': 0.0, 'max': 1.0}

        # Feasibility guard
        all_keys = free_keys + [dep_key]
        sum_min = sum(bounds[k]['min'] for k in all_keys)
        sum_max = sum(bounds[k]['max'] for k in all_keys)
        if sum_min > 1.0:
            raise ValueError(
                f'CASTROSampling: Σ(min) = {sum_min:.4f} > 1 — '
                'lower bounds alone exceed 1; composition is infeasible.'
            )
        if sum_max < 1.0:
            raise ValueError(
                f'CASTROSampling: Σ(max) = {sum_max:.4f} < 1 — '
                'upper bounds cannot reach 1; composition is infeasible.'
            )

        # Generate candidates — shape (n_feas, len(free_keys) + 1)
        # The last column is the dependent component value; used only for
        # feasibility filtering, not returned.
        candidates = self._sample_compositions(free_keys, dep_key, bounds, n_desired)
        free_candidates = candidates[:, :len(free_keys)]

        # Distance selection in the free-composition subspace
        existing = self._load_existing(model, free_keys)
        selected = self._greedy_maximin(free_candidates, existing, n_desired)

        return {k: selected[:, j].tolist() for j, k in enumerate(free_keys)}


@explicit_serialize
class ExpandedCASTROSampling(InitialisationStrategy, ImproveErrorStrategy):
    """
    Constrained sampler for mixed inputs: unconstrained scalars (e.g. T, p)
    plus a composition group (Σ xi = 1, per-component bounds).

    The unconstrained inputs are sampled independently via Latin Hypercube
    Sampling inside their ``[min, max]`` bounds.  The composition group is
    sampled with the CASTRO sequential conditional algorithm (see
    ``CASTROSampling`` for the algorithmic details).  The two groups are then
    randomly paired into joint candidate vectors and ``nNewPoints`` are
    selected by greedy maximin in the full joint input space.

    Parameters
    ----------
    compositionGroup : dict
        ``{'free': ['x_N2', 'x_O2'], 'dependent': 'x_Ar'}``
        Same semantics as in ``CASTROSampling``.
    nNewPoints : int
        Number of joint input vectors to return.
    nOversample : int, optional
        Candidates generated per permutation for the composition group AND
        the number of LHS points drawn for the unconstrained group.
        Defaults to ``max(50, 5 * nNewPoints)``.
    seed : int or None, optional
        RNG seed.
    useExistingData : bool, optional
        Select points away from existing ``fitData`` (default ``True``).

    Notes
    -----
    All inputs **not** listed in ``compositionGroup['free']`` or
    ``compositionGroup['dependent']`` are treated as unconstrained.  No
    ``freeInputs`` list is required; it is derived automatically.

    Usage
    -----
    ::

        BackwardMappingModel(
            ...
            initialisationStrategy=Strategy.ExpandedCASTROSampling(
                compositionGroup={
                    'free': ['x_N2', 'x_O2', 'x_Ar'],
                    'dependent': 'x_CO2',
                },
                nNewPoints=30,
            ),
        )
    """

    def __init__(self, *args, **kwargs):
        InitialisationStrategy.__init__(self, *args, **kwargs)

    def newPoints(self, model):
        """
        Generate ``nNewPoints`` feasible joint input vectors.

        Returns
        -------
        dict
            ``{input_name: [float, ...]}`` covering all model inputs.
        """
        from scipy.stats.qmc import LatinHypercube as _LHS

        group = self['compositionGroup']
        free_keys = list(group['free'])
        dep_key = str(group['dependent'])

        n_desired = int(self.get('nNewPoints', 10))
        n_over = int(self.get('nOversample', max(50, 5 * n_desired)))
        rng = np.random.default_rng(self.get('seed', None))

        bounds = CASTROSampling._get_bounds(model)

        # Dependent bounds: explicit config > model.inputs > default
        if 'dependentBounds' in group:
            bounds[dep_key] = dict(group['dependentBounds'])
        elif dep_key not in bounds:
            bounds[dep_key] = {'min': 0.0, 'max': 1.0}

        # Unconstrained inputs: everything not in the composition group
        # dep_key may or may not be in model.inputs; exclude it either way.
        comp_set = set(free_keys) | {dep_key}
        free_input_keys = [k for k in model.inputs.keys() if k not in comp_set]

        # --- Sample unconstrained inputs via LHS ---
        if free_input_keys:
            d_free = len(free_input_keys)
            unit_free = _LHS(d=d_free, seed=int(rng.integers(0, 2**31))).random(n_over)
            free_lbs = np.array([bounds[k]['min'] for k in free_input_keys])
            free_ubs = np.array([bounds[k]['max'] for k in free_input_keys])
            free_samples = free_lbs + (free_ubs - free_lbs) * unit_free  # (n_over, d_free)
        else:
            free_samples = np.empty((n_over, 0))

        # --- Sample composition group via CASTRO ---
        # Reuse CASTROSampling's helpers via a temporary instance
        _castro = CASTROSampling(
            compositionGroup=group,
            nNewPoints=n_desired,
            nOversample=n_over,
            seed=int(rng.integers(0, 2**31)),
            useExistingData=False,   # distance selection happens below, in joint space
        )

        all_comp_keys = free_keys + [dep_key]
        sum_min = sum(bounds[k]['min'] for k in all_comp_keys)
        sum_max = sum(bounds[k]['max'] for k in all_comp_keys)
        if sum_min > 1.0:
            raise ValueError(
                f'ExpandedCASTROSampling: Σ(min) = {sum_min:.4f} > 1 — '
                'composition lower bounds exceed 1.'
            )
        if sum_max < 1.0:
            raise ValueError(
                f'ExpandedCASTROSampling: Σ(max) = {sum_max:.4f} < 1 — '
                'composition upper bounds cannot reach 1.'
            )

        comp_samples = _castro._sample_compositions(
            free_keys, dep_key, bounds, n_desired
        )  # (n_comp_feas, len(free_keys) + 1)
        # Drop dep column — it is computed in C, not a model input
        free_comp_samples = comp_samples[:, :len(free_keys)]

        # --- Pair unconstrained and composition samples ---
        n_pairs = min(free_samples.shape[0], free_comp_samples.shape[0])
        idx_free = rng.permutation(free_samples.shape[0])[:n_pairs]
        idx_comp = rng.permutation(free_comp_samples.shape[0])[:n_pairs]

        if free_input_keys:
            joint = np.column_stack([free_samples[idx_free], free_comp_samples[idx_comp]])
        else:
            joint = free_comp_samples[idx_comp]

        # Column order: free_input_keys + free_keys (dep excluded)
        all_keys = free_input_keys + free_keys

        # --- Distance selection in joint space ---
        existing = CASTROSampling._load_existing(self, model, all_keys)
        selected = CASTROSampling._greedy_maximin(joint, existing, n_desired)

        return {k: selected[:, j].tolist() for j, k in enumerate(all_keys)}


@explicit_serialize
class Test(ParameterFittingStrategy):


    def __init__(self, *args, **kwargs):
        """
        """
        ParameterFittingStrategy.__init__(self, *args, **kwargs)


    def validationSets(self, n, testIndices):
        for i in range(n):
            if i not in testIndices:
                 yield i


    def split(self, nSamples):
        """
        s = [ ( ( training_set ), validation_point ), ... ]
        """
        s = list(range(nSamples)) # validation samples
        training_samples = (tuple(s[0:i] + s[i+1:]) for (i,si) in enumerate(s))
        return ( training_samples, s )


    def fit(self, model, testIndices):
        """
        """
        test_set = set(testIndices)
        # ------------------------------ Function --------------------------- #
        def errorFit(parameters):
            cModel = modena.libmodena.modena_model_t(
                model=model,
                parameters=list(parameters)
            )
            return np.array(list(model.error(
                cModel,
                idxGenerator=(
                    i for i in range(model.nSamples) if i not in test_set
                ),
                checkBounds=False,
            )))
        # ------------------------------------------------------------------- #

        new_parameters = model.parameters[:]
        if not len(new_parameters):
            new_parameters = [None] * len(model.surrogateFunction.parameters)
            for k, v in model.surrogateFunction.parameters.items():
                new_parameters[v.argPos] = (v.min + v.max)/2

        max_parameters = [None]*len(new_parameters)
        min_parameters = [None]*len(new_parameters)
        for k, v in model.surrogateFunction.parameters.items():
            min_parameters[v.argPos] = v.min
            max_parameters[v.argPos] = v.max

        new_parameters = list(TrustRegionReflective().fit(
            errorFit,
            np.array(new_parameters, dtype=float),
            bounds=(min_parameters, max_parameters),
        ))

        return new_parameters


    def validate(self, model, parameters, testIndices):
        """
        """

        # ------------------------------ Function --------------------------- #
        def errorTest(parameters):

            def fitData(testIndices):
                for i in testIndices:
                     yield i

            # Instantiate the surrogate model
            cModel = modena.libmodena.modena_model_t(model,parameters=list(parameters))

            return max(abs(i) for i in model.error(cModel,idxGenerator=fitData(testIndices),checkBounds=False))
        # ------------------------------------------------------------------- #
        return errorTest(parameters)



    def newPointsFWAction(self, model, **kwargs):
        """
        * Get training and validation sets
        * Regression
        * Validation
        * if valid, return empty workflow, else perform DoE.
        """

        training_sets, validation_sets = self.split(model.nSamples)

        parameters = [ self.fit(model, [v_set] ) for v_set in validation_sets ]
        errors = [ self.validate(model, pi, [vi] ) for (pi, vi) in zip(parameters, validation_sets) ]

        maxError = min(errors)
        new_parameters = parameters[errors.index(maxError)]

        _log.info('Maximum Error = %g', maxError)
        if maxError > self['maxError']:
            _log.warning('Parameters not valid, adding samples.')
            _log.debug('current parameters = [%s]', ', '.join(f'{k:g}' for k in new_parameters))

            # Update database
            model.save()

            return FWAction(detours=self['improveErrorStrategy'].workflow(model))

        else:
            _log.debug('old parameters = [%s]', ', '.join(f'{k:g}' for k in model.parameters))
            _log.info('new parameters = [%s]', ', '.join(f'{k:g}' for k in new_parameters))

            model["parameters"] = new_parameters
            model.updateMinMax()
            model.last_fitted = datetime.now(timezone.utc)
            model.save()
            ModelRegistry().update_lock(model)

            # return nothing to restart normal operation
            return FWAction()



@explicit_serialize
class NonLinFitWithErrorContol(ParameterFittingStrategy):
    """
    @brief    Parameter fitting class, non-linear least squares regression.
    @details
              The Strategy
    """

    def __init__(self, *args, **kwargs):
        """
        @todo access tuple correctly
        """
        #if '_fw_name' in args[0]:
        #    ParameterFittingStrategy.__init__(self, *args, **kwargs)

        #if not kwargs.has_key('improveErrorStrategy'):
        #    raise Exception('Need improveErrorStrategy')
        #if not isinstance(
        #    kwargs['improveErrorStrategy'], ImproveErrorStrategy
        #):
        #    raise TypeError('Need improveErrorStrategy')

        ParameterFittingStrategy.__init__(self, *args, **kwargs)


    def newPointsFWAction(self, model, **kwargs):
        # Make sure we get new samples in deterministic manner
        seed(model.nSamples)

        # Backward-compat: prefer explicit crossValidation / acceptanceCriterion
        # keys; fall back to legacy testDataPercentage / maxError keys so that
        # existing MongoDB documents continue to work without migration.
        cv = self.get('crossValidation', None)
        if cv is None:
            pct = self.get('testDataPercentage', 0.2)
            cv = Holdout(testDataPercentage=pct)

        criterion = self.get('acceptanceCriterion', None)
        if criterion is None:
            threshold = self.get('maxError', 0.1)
            criterion = MaxError(threshold=threshold)

        # Common parameter initialisation
        init_parameters = model.parameters[:]
        if not len(init_parameters):
            init_parameters = [None] * len(model.surrogateFunction.parameters)
            for k, v in model.surrogateFunction.parameters.items():
                init_parameters[v.argPos] = (v.min + v.max) / 2

        max_parameters = [None] * len(init_parameters)
        min_parameters = [None] * len(init_parameters)
        for k, v in model.surrogateFunction.parameters.items():
            min_parameters[v.argPos] = v.min
            max_parameters[v.argPos] = v.max

        def _fit(train_idx):
            """Fit on train_idx; return optimised parameter list."""
            train_list = list(train_idx)

            def errorFit(parameters):
                # TODO: modena_model_t is reconstructed (malloc + copy) on every
                #   optimizer callback.  To avoid this, the C API would need a
                #   modena_model_set_parameters() function that updates parameters
                #   in-place on an existing modena_model_t.  Until then this cost
                #   is unavoidable without changing src/src/model.c and the Python
                #   binding.
                cModel = modena.libmodena.modena_model_t(
                    model=model, parameters=list(parameters)
                )
                return np.array(list(model.error(
                    cModel,
                    idxGenerator=iter(train_list),
                    checkBounds=False,
                    metric=criterion.metric,
                )))

            optimizer = self.get('optimizer', TrustRegionReflective())
            return list(optimizer.fit(
                errorFit,
                np.array(init_parameters, dtype=float),
                bounds=(min_parameters, max_parameters),
            ))

        # Cross-validation loop
        # TODO: parallelize folds with ProcessPoolExecutor.  The current barrier
        #   is that _fit() closes over modena_model_t, which is not picklable.
        #   To enable Pool.map, restructure _fit to accept only plain serializable
        #   data (parameter bounds, fitData arrays) and re-initialise modena_model_t
        #   inside the worker.
        fold_errors = []
        best_params = None
        best_err = float('inf')

        for train_idx, test_idx in cv.splits(model.nSamples):
            params = _fit(train_idx)
            cModel = modena.libmodena.modena_model_t(
                model=model, parameters=params
            )
            residuals = list(model.error(
                cModel,
                idxGenerator=iter(test_idx),
                checkBounds=False,
                metric=criterion.metric,
            ))
            err = criterion.metric.aggregate(residuals)
            fold_errors.append(err)
            if err < best_err:
                best_err, best_params = err, params

        cv_error = cv.aggregate(fold_errors)
        _log.info('CV error = %.4g', cv_error)

        if not criterion.accepts(cv_error):
            _log.warning('Parameters not valid, adding samples.')
            _log.debug('current parameters = [%s]', ', '.join(f'{k:g}' for k in best_params))

            model.save()
            return FWAction(detours=self['improveErrorStrategy'].workflow(model))

        else:
            _log.debug('old parameters = [%s]', ', '.join(f'{k:g}' for k in model.parameters))

            # Refit on full dataset after CV acceptance
            new_parameters = _fit(list(range(model.nSamples)))
            _log.info('new parameters = [%s]', ', '.join(f'{k:g}' for k in new_parameters))

            model.parameters = new_parameters
            model.updateMinMax()
            model.last_fitted = datetime.now(timezone.utc)
            model.save()
            ModelRegistry().update_lock(model)

            # return nothing to restart normal operation
            return FWAction()


@explicit_serialize
class NonLinFitToPointWithSmallestError(ParameterFittingStrategy):
    """
    Performs parameter fitting of a set of samples and returns the parameters
    that yield the smallest error.

    @todo The strategy does **not** allow for error to be improved, but this
          can be changed in the future.
    """

    def __init__(self, *args, **kwargs):

        # TODO: access tuple correctly
        #if '_fw_name' in args[0]:
        #    ParameterFittingStrategy.__init__(self, *args, **kwargs)

        #if not kwargs.has_key('improveErrorStrategy'):
        #    raise Exception('Need improveErrorStrategy')
        #if not isinstance(
        #    kwargs['improveErrorStrategy'], ImproveErrorStrategy
        #):
        #    raise TypeError('Need improveErrorStrategy')

        ParameterFittingStrategy.__init__(self, *args, **kwargs)


    def newPointsFWAction(self, model, **kwargs):

        new_parameters = model.parameters[:]
        if not len(new_parameters):
            new_parameters = [None] * len(model.surrogateFunction.parameters)
            for k, v in model.surrogateFunction.parameters.items():
                new_parameters[v.argPos] = (v.min + v.max)/2

        max_parameters = [None]*len(new_parameters)
        min_parameters = [None]*len(new_parameters)
        for k, v in model.surrogateFunction.parameters.items():
            min_parameters[v.argPos] = v.min
            max_parameters[v.argPos] = v.max

        maxError = 1000
        for i in range(model.nSamples):
            testPoint = [i]
            test_set = set(testPoint)

            # -------------------------- Function --------------------------- #
            def errorTest(parameters, _testPoint=testPoint):
                # Instantiate the surrogate model
                cModel = modena.libmodena.modena_model_t(
                    model,
                    parameters=list(parameters)
                )

                return max(
                    abs(r) for r in model.error(
                        cModel,
                        idxGenerator=iter(_testPoint),
                        checkBounds=False
                    )
                )

            # -------------------------- Function --------------------------- #
            def errorFit(parameters, _test_set=test_set):
                # Instantiate the surrogate model
                cModel = modena.libmodena.modena_model_t(
                    model=model,
                    parameters=list(parameters)
                )

                return np.array(list(
                    model.error(
                        cModel,
                        idxGenerator=(
                            j for j in range(model.nSamples)
                            if j not in _test_set
                        ),
                        checkBounds=False
                    )
                ))
            # --------------------------------------------------------------- #

            fitted_params = list(TrustRegionReflective().fit(
                errorFit,
                np.array(new_parameters, dtype=float),
                bounds=(min_parameters, max_parameters),
            ))

            parameterError = errorTest(fitted_params)
            if parameterError < maxError:
                maxError = parameterError
                new_parameters = fitted_params

        _log.info('Maximum Error = %g', maxError)
        _log.debug('old parameters = [%s]', ', '.join(f'{k:g}' for k in model.parameters))
        _log.info('new parameters = [%s]', ', '.join(f'{k:g}' for k in new_parameters))

        # Update database
        # TODO: This is not save if the model is updated by another fitting
        #                                         task running concurrently
        model.parameters = new_parameters
        model.updateMinMax()
        model.last_fitted = datetime.now(timezone.utc)
        model.save()
        ModelRegistry().update_lock(model)

        del parameterError
        del max_parameters
        del min_parameters

        # return nothing to restart normal operation
        return FWAction()


@explicit_serialize
class Initialisation(FireTaskBase):
    """
    @brief    Defines a computational, i.e. Firetask, performing initialisation
    @details
              The firework loads the surrogate model and serialises the
              initialisation strategy.

    @author Henrik Rusche
    """

    def __init__(self, *args, **kwargs):
        FireTaskBase.__init__(self, *args, **kwargs)

        if 'surrogateModel' in kwargs:
            if isinstance(kwargs['surrogateModel'], modena.SurrogateModel):
                self['surrogateModelId'] = kwargs['surrogateModel']['_id']
                del self['surrogateModel']


    def run_task(self, fw_spec):
        """
        @brief    Method called by Fireworks in order to run the Firetask
        @params   fw_spec (dict) parameters passed to the Firetask
        """
        try:
            _log.info('Performing initialisation')
            model = modena.SurrogateModel.load(self['surrogateModelId'])
            return FWAction(
                detours=model.initialisationStrategy().workflow(model)
            )
        except Exception:
            import traceback
            traceback.print_exc()
            return FWAction(defuse_workflow=True)


@explicit_serialize
class ParameterFitting(FireTaskBase):
    """
    @brief    Defines the computational task performing parameter estimation
    @details
              The purpose of this class is to load the "parameter estimation
              strategy" from a surrogate model.

    @author Henrik Rusche
    """

    def __init__(self, *args, **kwargs):
        FireTaskBase.__init__(self, *args, **kwargs)

        if 'surrogateModel' in kwargs:
            if isinstance(kwargs['surrogateModel'], modena.SurrogateModel):
                self['surrogateModelId'] = kwargs['surrogateModel']['_id']
                del self['surrogateModel']


    def run_task(self, fw_spec):
        """
        @brief    Method called by Fireworks in order to run the Firetask
        @params   fw_spec (dict) parameters passed to the Firetask
        """
        try:
            model = modena.SurrogateModel.load(self['surrogateModelId'])
            _log.info('Performing parameter fitting for model %s', model._id)
            model.updateFitDataFromFwSpec(fw_spec)
            action = model.parameterFittingStrategy().newPointsFWAction(model)
            # When fitting succeeds (no detours needed), push the model ID into
            # fw_spec so the upstream BackwardMappingScriptTask can tell freeze()
            # exactly which models were retrained in this detour chain — avoiding
            # loading and compiling every model in the database.
            if not action.detours:
                action.mod_spec = (action.mod_spec or []) + [
                    {'_push': {'_modena_fitted_models': self['surrogateModelId']}}
                ]
            return action
        except Exception as e:
            import traceback
            traceback.print_exc()
            return FWAction(defuse_workflow=True)


class OutOfBounds(Exception):
    def __init__(self, *args, **kwargs):
        _log.info('%s out-of-bounds, executing outOfBoundsStrategy for model %s',
                  args[0], args[1]._id)
        super().__init__(*args, **kwargs)


class ParametersNotValid(Exception):
    pass


class TerminateWorkflow(Exception):
    pass


class ModifyWorkflow(Exception):
    pass


class FatalModelError(Exception):
    """Raised when a model operation fails in a way that cannot be recovered.

    Caught by ``executeAndCatchExceptions()`` and converted to
    ``FWAction(defuse_workflow=True)`` with a clear ERROR log.

    Model authors may raise this from their own ``task()`` or OOB strategy
    ``newPoints()`` when continuing the workflow is pointless — for example,
    when a composition input goes out of bounds and no valid expansion exists.
    """
    pass


class NonConvergenceStrategy(defaultdict, FWSerializable):
    """Base class for strategies that handle exact simulation failures.

    Subclasses implement ``handle(exc, model_id, point)`` and return an
    ``FWAction`` (or raise to let FireWorks mark the firework FIZZLED).

    Attach to a ``BackwardMappingModel`` via::

        m = BackwardMappingModel(
            _id='myModel',
            ...
            nonConvergenceStrategy=FizzleOnFailure(),
        )

    The default (when the field is absent) is ``SkipPoint()``.
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    @abc.abstractmethod
    def handle(self, exc, model_id: str, point: dict):
        """Handle a simulation failure.

        Args:
            exc:       The exception raised by the exact simulation.
            model_id:  The surrogate model ``_id``.
            point:     The input point dict that caused the failure.

        Returns:
            ``FWAction`` — or raises to fizzle the firework.
        """
        raise NotImplementedError

    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        return dict(self)

    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        return cls(m_dict)

    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


@explicit_serialize
class SkipPoint(NonConvergenceStrategy):
    """Log a warning and skip the failing point.

    The firework completes normally (no data pushed for this point).
    All sibling exact simulations continue, and the fitting step runs
    with fewer training points.  This is the default strategy.
    """

    def __init__(self, *args, **kwargs):
        NonConvergenceStrategy.__init__(self, *args, **kwargs)

    def handle(self, exc, model_id: str, point: dict):
        _log.warning(
            'Exact simulation SKIPPED for model %s at point %s: %s',
            model_id, point, exc,
        )
        return FWAction()


@explicit_serialize
class FizzleOnFailure(NonConvergenceStrategy):
    """Re-raise the exception so FireWorks marks the firework FIZZLED.

    Use this when any simulation failure is unexpected and should be
    investigated — the workflow stops and the error is clearly visible
    in the FireWorks state.
    """

    def __init__(self, *args, **kwargs):
        NonConvergenceStrategy.__init__(self, *args, **kwargs)

    def handle(self, exc, model_id: str, point: dict):
        _log.error(
            'Exact simulation FIZZLED for model %s at point %s: %s',
            model_id, point, exc,
        )
        raise exc


@explicit_serialize
class DefuseWorkflowOnFailure(NonConvergenceStrategy):
    """Defuse the entire workflow on any simulation failure.

    Use only when a single failure makes further simulation pointless
    (e.g. a shared resource is unavailable).  This was the pre-3.x
    default behaviour.
    """

    def __init__(self, *args, **kwargs):
        NonConvergenceStrategy.__init__(self, *args, **kwargs)

    def handle(self, exc, model_id: str, point: dict):
        _log.error(
            'Exact simulation FAILED for model %s at point %s — defusing workflow: %s',
            model_id, point, exc,
        )
        return FWAction(defuse_workflow=True)


@explicit_serialize
class ModenaFireTask(FireTaskBase):
    """
    @brief    Defines a computational task for detailed simulations.
    @details
    """

    def find_binary(self, name: str) -> str:
        """
        Locate an exact-simulation binary by name.

        Delegates to ModelRegistry.find_binary(), passing the .py file of the
        concrete FireTask subclass as the caller_file for the package-relative
        fallback (dirname(caller_file)/bin/<name>).

        Args:
            name:  Binary filename, e.g. 'flowRateExact'.

        Returns:
            Absolute path to the binary.

        Raises:
            FileNotFoundError: if not found in any configured or package-relative path.
        """
        import inspect
        from modena.Registry import ModelRegistry
        caller_file = inspect.getfile(type(self))
        return ModelRegistry().find_binary(name, caller_file=caller_file)

    def executeAndCatchExceptions(self, op, text):
        """
        @brief    Method executing tasks and catching callbacks
        @details
                  The
        """
        try:
            op()

        except OutOfBounds as e:
            model = e.args[1]
            _log.info('%s out-of-bounds, executing outOfBoundsStrategy for model %s',
                      text, model._id)

            # Continue with exact tasks, parameter estimation and (finally) this
            # task in order to resume normal operation
            wf = model.outOfBoundsStrategy().workflow(
                model,
                outsidePoint=model.outsidePoint
            )
            wf.append_wf(
                Workflow([Firework(self, name=f'{model._id} — resume after OOB')],
                         name=f'{model._id} — resume after OOB'),
                wf.leaf_fw_ids
            )
            raise ModifyWorkflow(FWAction(detours=wf))

        except ParametersNotValid as e:
            model = e.args[1]
            _log.info('%s is not initialised, executing initialisationStrategy for model %s',
                      text, model._id)

            # Continue with exact tasks, parameter estimation and (finally) this
            # task in order to resume normal operation
            wf = model.initialisationStrategy().workflow(model)
            wf.append_wf(
                Workflow([Firework(self, name=f'{model._id} — resume after init')],
                         name=f'{model._id} — resume after init'),
                wf.leaf_fw_ids
            )
            raise ModifyWorkflow(FWAction(detours=wf))

        except FatalModelError as e:
            _log.error('Fatal model error — defusing workflow: %s', e)
            raise ModifyWorkflow(FWAction(defuse_workflow=True))


    def run_task(self, fw_spec):
        """
        @brief    Method called by Fireworks in order to run the Firetask
        @params   fw_spec (dict) parameters passed to the Firetask
        @details
                  The Firetask performs **one** detailed simulation.

                  The Firetask reads the input, i.e. "point" from the "fw_spec"
                  input.

                  The execution of the simulation is wrapped inside a lambda
                  function and sent to the method executeAndCatchExceptions
                  which captures and handles error callbacks.

        @returns  FWAction object telling Fireworks how to proceed.
        """
        _model = None   # sentinel — used by the except handler below
        try:
            _log.info('Performing exact simulation (microscopic code recipe) for model %s',
                      self['modelId'])

            p = self['point']

            _log.info('point = {%s}', ', '.join(f'{k}: {v:g}' for k, v in p.items()))

            _model = modena.SurrogateModel.load(self['modelId'])
            oldP = copy.copy(p)
            for m in _model.substituteModels:
                self.executeAndCatchExceptions(
                    lambda: p.update(m.callModel(p)),
                    'Substituted Model'
                )

            if not len(p) == len(oldP):
                _log.info('values added by substitution = {%s}',
                          ', '.join(f'{k}: {v:g}' for k, v in p.items() if k not in oldP))

            self.executeAndCatchExceptions(
                lambda: self.task(fw_spec),
                'Model'
            )
            return FWAction(mod_spec=[{'_push': self['point']}])

        except ModifyWorkflow as e:
            return e.args[0]

        except Exception as e:
            import traceback
            traceback.print_exc()
            strategy = (
                _model.nonConvergenceStrategy()
                if _model is not None
                else SkipPoint()
            )
            return strategy.handle(
                e,
                self.get('modelId', '?'),
                self.get('point', {}),
            )


    def handleReturnCode(self, returnCode):
        """
        @brief    Handle return code caught in executeAndCatchExceptions
        @params   returnCode (integer) error code from simulation
        @details
                  The method is called with an integer, i.e. the error code, as
                  the argument and raises the appropriate Python exception if
                  the error code is MoDeNa-related.

                  | Error code | Exception                 |
                  | ---------- | ------------------------- |
                  | 200        | Model is Out of bounds    |
                  | 201        | Model is not in database  |
                  | 202        | Parameters not validated  |

        """
        if returnCode > 0:
            _log.error('return code = %s', returnCode)

        if returnCode == 200:
            try:
                # TODO
                # Finding the 'failing' model using the outsidePoint will fail
                # eventually fail when running in parallel. Need to pass id of
                # calling FireTask. However, this requires additional code in the
                # library as well as cooperation of the recipie

                model = modena.SurrogateModel.loadFailing()
            except Exception:
                raise TerminateWorkflow(
                    'Exact task raised OutOfBounds signal, '
                  + 'but failing model could not be determined',
                    returnCode
                )

            raise OutOfBounds(
                'Exact task raised OutOfBounds signal',
                model,
                returnCode
            )

        elif returnCode == 201:
            try:
                model = modena.SurrogateModel.loadFromModule()
            except Exception:
                raise TerminateWorkflow(
                    'Exact task raised LoadFromModule signal, '
                  + 'but failing model could not be determined',
                    returnCode
                )
            raise ParametersNotValid(
                'Exact task raised LoadFromModule signal',
                model,
                returnCode
            )

        elif returnCode == 202:
            try:
                model = modena.SurrogateModel.loadParametersNotValid()
            except Exception:
                raise TerminateWorkflow(
                    'Exact task raised ParametersNotValid, '
                  + 'but failing model could not be determined',
                    returnCode
                )
            raise ParametersNotValid(
                'Exact task raised ParametersNotValid',
                model,
                returnCode
            )

        elif returnCode > 0:
            raise TerminateWorkflow(
                'An unknow error occurred calling exact simulation',
                returnCode
            )


@explicit_serialize
class EmptyFireTask(FireTaskBase):
    def run_task(self, fw_spec):
        pass

@explicit_serialize
class BackwardMappingScriptTask(ModenaFireTask, ScriptTask):
    """
    @brief  FireTask that starts a macroscopic code and catches its return code
    @author Henrik Rusche
    """
    required_params = ['script']
    optional_params = ['preserve_launch_dir']

    def run_task(self, fw_spec):
        """
        """
        # import os
        # print(fw_spec)
        # fw_spec['_launch_dir'] = os.path.abspath(os.curdir)
        # fw_spec['_pass_job_info'] = True
        #print(fw_spec['job_info'])
        try:
            _log.info('Performing backward mapping simulation (macroscopic code recipe)')
            self.executeAndCatchExceptions(
                lambda: self.task(fw_spec),
                'Model'
            )
            _log.info('Success')
            fitted_models = fw_spec.get('_modena_fitted_models', [])
            ModelRegistry().freeze(model_ids=fitted_models)

        except ModifyWorkflow as e:
            return e.args[0]

        except Exception as e:
            _log.error('%s', e)
            import traceback
            traceback.print_exc()
            return FWAction(defuse_workflow=True)

        return FWAction()


    def task(self, fw_spec):
        """
        @brief  Member function running the detailed simulation

        @param  fw_spec  dict received from FireWork
        """

        self['defuse_bad_rc'] = True

        # Execute the macroscopic code by calling function in base class
        ret = ScriptTask.run_task(self, fw_spec)
        self.handleReturnCode(ret.stored_data['returncode'])


# @explicit_serialize
# class ModenaRemoteTask(ModenaFireTask, Task):
#     """
#     @brief  FireTask that starts a macroscopic code and catches its return code
#     @author Henrik Rusche
#     """
#     required_params = ['server', 'user']
#     optional_params = []
# 
#     def run_task(self, fw_spec):
#         """
#         """
#         try:
#             print(
#                 term.yellow
#                 + 'Performing backward mapping simulation '
#                 + '(macroscopic code recipe)'
#                 + term.normal
#             )
#             self.executeAndCatchExceptions(
#                 lambda: self.task(fw_spec),
#                 'Model'
#             )
#             print(term.green + 'Success - We are done' + term.normal)
# 
#         except ModifyWorkflow as e:
#             return e.args[0]
# 
#         except Exception as e:
#             print(term.red + e.args[0] + term.normal)
#             import traceback
#             traceback.print_exc()
#             return FWAction(defuse_workflow=True)
# 
#         return FWAction()
# 
# 
#     def run(self, fw_spec):
# 
#         self['defuse_bad_rc'] = True
# 
#         # Execute the macroscopic code by calling function in base class
#         ret = ScriptTask.run_task(self, fw_spec)
#         self.handleReturnCode(ret.stored_data['returncode'])

##
# @} # end of python_interface_library
# vim: filetype=python fileencoding=utf-8 syntax=on colorcolumn=79
# vim: ff=unix tabstop=4 softtabstop=0 expandtab shiftwidth=4 smarttab
# vim: nospell spelllang=en_us
