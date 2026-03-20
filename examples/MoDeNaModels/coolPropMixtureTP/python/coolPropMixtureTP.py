"""
@file      Mixture density surrogate: N2/O2/Ar as f(T, p, x_N2, x_O2).
@details
           Trains a 2nd-order polynomial in (T, p, x_N2, x_O2) to reproduce
           the mass density of a N2/O2/Ar mixture as returned by CoolProp.
           Argon fraction is computed inside the surrogate C function as:

               x_Ar = 1 - x_N2 - x_O2

           Input ranges:

               T    ∈ [250, 350] K
               p    ∈ [1e5, 2e6] Pa
               x_N2 ∈ [0.70, 0.85]   (free composition input)
               x_O2 ∈ [0.14, 0.25]   (free composition input)
               x_Ar ∈ [0.005, 0.08]  (feasibility constraint only)

           Training uses ExpandedCASTROSampling: T and p are sampled via
           standard Latin Hypercube Sampling; the composition group (x_N2,
           x_O2) is sampled with the CASTRO sequential conditional algorithm;
           the two groups are randomly paired and filtered by greedy maximin
           selection in the full joint (T, p, x_N2, x_O2) space.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

import modena
from modena import BackwardMappingModel, CFunction, ModenaFireTask
import modena.Strategy as Strategy
from modena.ErrorMetrics import RelativeError
from fireworks import FWAction
from fireworks.utilities.fw_utilities import explicit_serialize
from fireworks import FireTaskBase


@explicit_serialize
class MixtureDensityExactSim(ModenaFireTask):
    """
    Evaluates N2/O2/Ar mass density at a single (T, p, x_N2, x_O2) point.

    x_Ar is inferred as ``1 - x_N2 - x_O2``; it is not a model input.
    The result (``rho``, kg/m³) is stored back into ``self['point']``.
    """

    def task(self, fw_spec):
        import CoolProp.CoolProp as CP

        T    = self['point']['T']
        p    = self['point']['p']
        x_N2 = self['point']['x_N2']
        x_O2 = self['point']['x_O2']
        x_Ar = 1.0 - x_N2 - x_O2

        AS = CP.AbstractState('HEOS', 'Nitrogen&Oxygen&Argon')
        AS.set_mole_fractions([x_N2, x_O2, x_Ar])
        AS.update(CP.PT_INPUTS, p, T)
        rho = AS.rhomass()

        self['point']['rho'] = rho
        print(
            f'T={T:.1f} K  p={p:.2e} Pa'
            f'  x_N2={x_N2:.4f}  x_O2={x_O2:.4f}  x_Ar={x_Ar:.4f}'
            f'  ρ = {rho:.4f} kg/m³'
        )


# 2nd-order polynomial in (T, p, x_N2, x_O2) — C(4+2,2) = 15 parameters.
# x_Ar = 1 - x_N2 - x_O2 is computed inside the C function.
f = CFunction(
    Ccode='''
#include "modena.h"
#include "math.h"

void mixtureDensity_N2O2Ar
(
    const modena_model_t* model,
    const double*         inputs,
    double*               outputs
)
{
    {% block variables %}{% endblock %}

    /* Argon mole fraction: enforced by Σ xi = 1 */
    const double x_Ar = 1.0 - x_N2 - x_O2;

    outputs[0] = parameters[0]
               + parameters[1]  * T
               + parameters[2]  * p
               + parameters[3]  * x_N2
               + parameters[4]  * x_O2
               + parameters[5]  * T    * T
               + parameters[6]  * T    * p
               + parameters[7]  * T    * x_N2
               + parameters[8]  * T    * x_O2
               + parameters[9]  * p    * p
               + parameters[10] * p    * x_N2
               + parameters[11] * p    * x_O2
               + parameters[12] * x_N2 * x_N2
               + parameters[13] * x_N2 * x_O2
               + parameters[14] * x_O2 * x_O2;
}
''',
    inputs={
        'T':    {'min': 250.0, 'max': 350.0},   # temperature, K
        'p':    {'min': 1e5,   'max': 2e6},     # pressure, Pa
        'x_N2': {'min': 0.70,  'max': 0.85},   # nitrogen mole fraction
        'x_O2': {'min': 0.14,  'max': 0.25},   # oxygen mole fraction
        # x_Ar is derived — not an independent input
    },
    outputs={
        'rho': {'min': 0.0, 'max': 200.0, 'argPos': 0},   # mass density, kg/m³
    },
    parameters={
        'a0':    {'min': -1e5, 'max': 1e5, 'argPos':  0},
        'aT':    {'min': -1e5, 'max': 1e5, 'argPos':  1},
        'ap':    {'min': -1e5, 'max': 1e5, 'argPos':  2},
        'aN2':   {'min': -1e5, 'max': 1e5, 'argPos':  3},
        'aO2':   {'min': -1e5, 'max': 1e5, 'argPos':  4},
        'aTT':   {'min': -1e5, 'max': 1e5, 'argPos':  5},
        'aTp':   {'min': -1e5, 'max': 1e5, 'argPos':  6},
        'aTN2':  {'min': -1e5, 'max': 1e5, 'argPos':  7},
        'aTO2':  {'min': -1e5, 'max': 1e5, 'argPos':  8},
        'app':   {'min': -1e5, 'max': 1e5, 'argPos':  9},
        'apN2':  {'min': -1e5, 'max': 1e5, 'argPos': 10},
        'apO2':  {'min': -1e5, 'max': 1e5, 'argPos': 11},
        'aN2N2': {'min': -1e5, 'max': 1e5, 'argPos': 12},
        'aN2O2': {'min': -1e5, 'max': 1e5, 'argPos': 13},
        'aO2O2': {'min': -1e5, 'max': 1e5, 'argPos': 14},
    },
)


@explicit_serialize
class MixtureDensityValidationTask(FireTaskBase):
    """
    Loads the trained density surrogate and compares it with CoolProp over
    a held-out (T, p, x_N2, x_O2) grid.  Prints max and mean relative errors.
    """

    required_params = []
    optional_params = []

    def run_task(self, fw_spec):
        import CoolProp.CoolProp as CP
        import numpy as np

        model = modena.SurrogateModel.load('mixtureDensity[fluid=N2O2Ar]')
        cModel = modena.libmodena.modena_model_t(
            model=model,
            parameters=list(model.parameters),
        )

        # Held-out points offset from training distribution
        test_points = [
            (260.0, 3e5,  0.74, 0.22),
            (300.0, 1e6,  0.79, 0.17),
            (340.0, 1.5e6, 0.82, 0.15),
            (275.0, 5e5,  0.76, 0.20),
            (315.0, 1.8e6, 0.80, 0.16),
        ]

        inputs  = [0.0] * cModel.inputs_size
        outputs = [0.0] * cModel.outputs_size

        T_pos   = model.inputs_argPos('T')
        p_pos   = model.inputs_argPos('p')
        n2_pos  = model.inputs_argPos('x_N2')
        o2_pos  = model.inputs_argPos('x_O2')
        rho_pos = model.outputs_argPos('rho')

        print(
            f'\n{"T [K]":>7}  {"p [Pa]":>9}  {"x_N2":>6}  {"x_O2":>6}'
            f'  {"ρ_ref":>10}  {"ρ_sur":>10}  {"err [%]":>8}'
        )
        print('-' * 70)

        errors = []
        for T, p, x_N2, x_O2 in test_points:
            x_Ar = 1.0 - x_N2 - x_O2

            AS = CP.AbstractState('HEOS', 'Nitrogen&Oxygen&Argon')
            AS.set_mole_fractions([x_N2, x_O2, x_Ar])
            AS.update(CP.PT_INPUTS, p, T)
            rho_ref = AS.rhomass()

            inputs[T_pos]  = T
            inputs[p_pos]  = p
            inputs[n2_pos] = x_N2
            inputs[o2_pos] = x_O2
            ret = cModel(inputs)
            rho_sur = ret[rho_pos]

            rel_err = abs(rho_sur - rho_ref) / rho_ref * 100
            errors.append(rel_err)
            print(
                f'{T:>7.1f}  {p:>9.2e}  {x_N2:>6.4f}  {x_O2:>6.4f}'
                f'  {rho_ref:>10.4f}  {rho_sur:>10.4f}  {rel_err:>7.2f}%'
            )

        print('-' * 70)
        print(f'Max relative error : {max(errors):.2f} %')
        print(f'Mean relative error: {np.mean(errors):.2f} %')

        return FWAction()


_COMPOSITION_GROUP = {
    'free': ['x_N2', 'x_O2'],
    'dependent': 'x_Ar',
    'dependentBounds': {'min': 0.005, 'max': 0.08},
}

m = BackwardMappingModel(
    _id='mixtureDensity[fluid=N2O2Ar]',
    surrogateFunction=f,
    exactTask=MixtureDensityExactSim(),
    substituteModels=[],
    initialisationStrategy=Strategy.ExpandedCASTROSampling(
        compositionGroup=_COMPOSITION_GROUP,
        nNewPoints=30,
        seed=42,
    ),
    outOfBoundsStrategy=Strategy.ExtendSpaceExpandedCASTROSampling(
        compositionGroup=_COMPOSITION_GROUP,
        nNewPoints=4,
    ),
    parameterFittingStrategy=Strategy.NonLinFitWithErrorContol(
        crossValidation=Strategy.Holdout(testDataPercentage=0.2),
        acceptanceCriterion=Strategy.MaxError(
            threshold=0.01,              # 1 % relative error
            metric=RelativeError(),
        ),
        optimizer=Strategy.TrustRegionReflective(),
        improveErrorStrategy=Strategy.ExpandedCASTROSampling(
            compositionGroup=_COMPOSITION_GROUP,
            nNewPoints=6,
            seed=None,
        ),
    ),
    nonConvergenceStrategy=Strategy.SkipPoint(),
)
