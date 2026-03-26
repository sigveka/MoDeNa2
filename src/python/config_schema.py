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

    Modena is free software; you can redistribute it and/or modify it under
    the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 3 of the License, or (at your option)
    any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.
@endcond'''

from __future__ import annotations

"""
@file
Pydantic v2 models for modena model ``config.toml`` files.

Each model package may ship a ``config.toml`` alongside its Python module.
Call ``modena.utils.load_model_config(__file__)`` to parse and validate it.

Schema overview
---------------
The top-level ``config.toml`` sections mirror the constructor arguments of
:class:`~modena.SurrogateModel.BackwardMappingModel`:

.. code-block:: toml

    [surrogate]           # bounds for CFunction inputs/outputs/parameters
    [strategy]            # initialisationStrategy / outOf… / parameterFitting…
    [simulation]          # arbitrary solver parameters (passed to the exact task)
    [[materials]]         # list of material-specific entries
    [misc]                # user-defined extra data

Strategy type names match the Python class names in :mod:`modena.Strategy`
exactly (PascalCase).  Declaration order determines ``argPos`` for outputs and
parameters — do **not** reorder after model creation.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------ #
# Surrogate section                                                    #
# ------------------------------------------------------------------ #

class BoundSpec(BaseModel):
    """Min/max bounds for one input, output, or parameter."""
    model_config = ConfigDict(extra='forbid')
    min: float
    max: float


class SurrogateConfig(BaseModel):
    """``[surrogate]`` section.

    Declaration order of ``outputs`` and ``parameters`` determines argPos
    (0, 1, 2, …).  Do not reorder after a model has been registered.
    """
    model_config = ConfigDict(extra='forbid')
    inputs:     dict[str, BoundSpec] = Field(default_factory=dict)
    outputs:    dict[str, BoundSpec] = Field(default_factory=dict)
    parameters: dict[str, BoundSpec] = Field(default_factory=dict)

    def inputs_dict(self) -> dict[str, dict]:
        """CFunction-compatible inputs dict (no argPos on inputs)."""
        return {k: {'min': v.min, 'max': v.max}
                for k, v in self.inputs.items()}

    def outputs_dict(self) -> dict[str, dict]:
        """CFunction-compatible outputs dict with auto-assigned argPos."""
        return {k: {'min': v.min, 'max': v.max, 'argPos': i}
                for i, (k, v) in enumerate(self.outputs.items())}

    def parameters_dict(self) -> dict[str, dict]:
        """CFunction-compatible parameters dict with auto-assigned argPos."""
        return {k: {'min': v.min, 'max': v.max, 'argPos': i}
                for i, (k, v) in enumerate(self.parameters.items())}


# ------------------------------------------------------------------ #
# Sampler sub-strategies                                               #
# ------------------------------------------------------------------ #

class LatinHypercubeConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['LatinHypercube'] = 'LatinHypercube'
    seed: int | None = None


class HaltonConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['Halton'] = 'Halton'
    seed: int | None = None
    scramble: bool = True


class SobolConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['Sobol'] = 'Sobol'
    seed: int | None = None
    scramble: bool = True


class RandomUniformConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['RandomUniform'] = 'RandomUniform'
    seed: int | None = None


SamplerConfig = Annotated[
    Union[LatinHypercubeConfig, HaltonConfig, SobolConfig, RandomUniformConfig],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# Optimizer sub-strategies                                             #
# ------------------------------------------------------------------ #

class TrustRegionReflectiveConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['TrustRegionReflective'] = 'TrustRegionReflective'
    ftol: float = 1e-8
    xtol: float = 1e-8
    max_nfev: int | None = None


class LevenbergMarquardtConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['LevenbergMarquardt'] = 'LevenbergMarquardt'
    ftol: float = 1e-8
    xtol: float = 1e-8


class DogBoxConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['DogBox'] = 'DogBox'
    ftol: float = 1e-8
    xtol: float = 1e-8


OptimizerConfig = Annotated[
    Union[TrustRegionReflectiveConfig, LevenbergMarquardtConfig, DogBoxConfig],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# Cross-validation sub-strategies                                      #
# ------------------------------------------------------------------ #

class HoldoutConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['Holdout'] = 'Holdout'
    testDataPercentage: float = 0.2


class KFoldConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['KFold'] = 'KFold'
    k: int


class LeaveOneOutConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['LeaveOneOut'] = 'LeaveOneOut'


class LeavePOutConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['LeavePOut'] = 'LeavePOut'
    p: int


class JackknifeConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['Jackknife'] = 'Jackknife'


CrossValidationConfig = Annotated[
    Union[
        HoldoutConfig, KFoldConfig, LeaveOneOutConfig,
        LeavePOutConfig, JackknifeConfig,
    ],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# ImproveError sub-strategies                                          #
# ------------------------------------------------------------------ #

class StochasticSamplingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['StochasticSampling'] = 'StochasticSampling'
    nNewPoints: int
    sampler: SamplerConfig | None = None


class CASTROSamplingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['CASTROSampling'] = 'CASTROSampling'
    compositionGroup: dict[str, Any]
    nNewPoints: int
    nOversample: int | None = None
    seed: int | None = None
    useExistingData: bool = True


class ExpandedCASTROSamplingConfig(BaseModel):
    """``ExpandedCASTROSampling`` — LHS for scalar inputs, CASTRO for compositions."""
    model_config = ConfigDict(extra='forbid')
    type: Literal['ExpandedCASTROSampling'] = 'ExpandedCASTROSampling'
    compositionGroup: dict[str, Any]
    nNewPoints: int
    nOversample: int | None = None
    seed: int | None = None


ImproveErrorStrategyConfig = Annotated[
    Union[StochasticSamplingConfig, CASTROSamplingConfig, ExpandedCASTROSamplingConfig],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# Error metrics and acceptance criterion                               #
# ------------------------------------------------------------------ #

class RelativeErrorConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['RelativeError'] = 'RelativeError'


class AbsoluteErrorConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['AbsoluteError'] = 'AbsoluteError'


class NormalizedErrorConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['NormalizedError'] = 'NormalizedError'


MetricConfig = Annotated[
    Union[RelativeErrorConfig, AbsoluteErrorConfig, NormalizedErrorConfig],
    Field(discriminator='type'),
]


class MaxErrorConfig(BaseModel):
    """``MaxError`` acceptance criterion — accepts if metric.aggregate ≤ threshold."""
    model_config = ConfigDict(extra='forbid')
    type: Literal['MaxError'] = 'MaxError'
    threshold: float
    metric: MetricConfig | None = None


# ------------------------------------------------------------------ #
# Parameter fitting strategy                                           #
# ------------------------------------------------------------------ #

class NonLinFitWithErrorContolConfig(BaseModel):
    """``NonLinFitWithErrorContol`` configuration.

    The shorthand ``testDataPercentage`` + ``maxError`` keys are passed through
    directly to the Strategy class, which handles backward-compat internally.
    """
    model_config = ConfigDict(extra='forbid')
    type: Literal['NonLinFitWithErrorContol'] = 'NonLinFitWithErrorContol'
    testDataPercentage:  float | None                   = None
    maxError:            float | None                   = None
    maxIterations:       int   | None                   = None
    crossValidation:     CrossValidationConfig | None   = None
    acceptanceCriterion: MaxErrorConfig | None          = None
    improveErrorStrategy: ImproveErrorStrategyConfig | None = None
    optimizer:           OptimizerConfig | None         = None


# Only one concrete fitting strategy exists; keep as Annotated for
# forward-compatibility if new ones are added later.
ParameterFittingStrategyConfig = NonLinFitWithErrorContolConfig


# ------------------------------------------------------------------ #
# Initialisation strategies                                            #
# ------------------------------------------------------------------ #

class InitialPointsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['InitialPoints'] = 'InitialPoints'
    initialPoints: dict[str, list[float]]


class InitialRangeConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['InitialRange'] = 'InitialRange'
    # {input_name: {min: ..., max: ...}}
    initialRange: dict[str, dict[str, float]]


class CASTROInitConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['CASTROSampling'] = 'CASTROSampling'
    compositionGroup: dict[str, Any]
    nNewPoints: int
    nOversample: int | None = None
    seed: int | None = None


InitialisationStrategyConfig = Annotated[
    Union[
        InitialPointsConfig, InitialRangeConfig,
        CASTROInitConfig, ExpandedCASTROSamplingConfig,
    ],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# Out-of-bounds strategies                                             #
# ------------------------------------------------------------------ #

class ExtendSpaceStochasticSamplingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['ExtendSpaceStochasticSampling'] = 'ExtendSpaceStochasticSampling'
    nNewPoints: int
    sampler: SamplerConfig | None = None


class ForbidOutOfBoundsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['ForbidOutOfBounds'] = 'ForbidOutOfBounds'


class ExtendSpaceExpandedCASTROSamplingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['ExtendSpaceExpandedCASTROSampling'] = 'ExtendSpaceExpandedCASTROSampling'
    compositionGroup: dict[str, Any]
    nNewPoints: int
    nOversample: int | None = None
    seed: int | None = None


OutOfBoundsStrategyConfig = Annotated[
    Union[
        ExtendSpaceStochasticSamplingConfig,
        ForbidOutOfBoundsConfig,
        ExtendSpaceExpandedCASTROSamplingConfig,
    ],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# Non-convergence strategy                                             #
# ------------------------------------------------------------------ #

class SkipPointConfig(BaseModel):
    """Skip a failing exact simulation and continue fitting."""
    model_config = ConfigDict(extra='forbid')
    type: Literal['SkipPoint'] = 'SkipPoint'


class FizzleOnFailureConfig(BaseModel):
    """Re-raise on failure → FireWorks marks firework FIZZLED."""
    model_config = ConfigDict(extra='forbid')
    type: Literal['FizzleOnFailure'] = 'FizzleOnFailure'


NonConvergenceStrategyConfig = Annotated[
    Union[SkipPointConfig, FizzleOnFailureConfig],
    Field(discriminator='type'),
]


# ------------------------------------------------------------------ #
# Strategy section                                                     #
# ------------------------------------------------------------------ #

class StrategyConfig(BaseModel):
    """``[strategy]`` section."""
    model_config = ConfigDict(extra='forbid')
    initialisationStrategy:   InitialisationStrategyConfig
    outOfBoundsStrategy:      OutOfBoundsStrategyConfig
    parameterFittingStrategy: ParameterFittingStrategyConfig
    nonConvergenceStrategy:   NonConvergenceStrategyConfig | None = None


# ------------------------------------------------------------------ #
# Material entry                                                       #
# ------------------------------------------------------------------ #

class MaterialConfig(BaseModel):
    """One entry in the ``[[materials]]`` array.

    ``name`` is required.  All other fields are package-specific (e.g.
    ``lattice_const``, ``mass``, ``potential_file`` for LAMMPS models) and
    are accessible as attributes (Pydantic ``extra='allow'``).
    """
    model_config = ConfigDict(extra='allow')
    name: str


# ------------------------------------------------------------------ #
# Simulate section                                                     #
# ------------------------------------------------------------------ #

class SimulateConfig(BaseModel):
    """``[simulate]`` section of ``modena.toml``.

    Declares the simulation task run by ``modena simulate`` and any keyword
    arguments forwarded to its constructor.

    Example ``modena.toml``::

        [simulate]
        target = "twoTank.TwoTankModel"

        [simulate.kwargs]
        end_time = 10.0
    """
    model_config = ConfigDict(extra='forbid')
    target: str | None = None
    kwargs: dict[str, Any] | None = None


# ------------------------------------------------------------------ #
# Top-level model config                                               #
# ------------------------------------------------------------------ #

class ModelConfig(BaseModel):
    """Root model for a ``config.toml`` file.

    All sections are optional so that a minimal config can define only what
    it needs (e.g. ``[strategy]`` only, leaving bounds hardcoded in Python).
    """
    model_config = ConfigDict(extra='forbid')
    surrogate:   SurrogateConfig  | None      = None
    strategy:    StrategyConfig   | None      = None
    simulation:  dict[str, Any]   | None      = None
    simulate:    SimulateConfig   | None      = None
    materials:   list[MaterialConfig] | None  = None
    parameters:  list[float]      | None      = None
    misc:        dict[str, Any]   | None      = None
