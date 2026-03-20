"""
@file      Mixture viscosity surrogate: N2/O2/Ar at fixed T and P.
@details
           Trains a 2nd-order bivariate polynomial in the free mole fractions
           (x_N2, x_O2) to reproduce the dynamic viscosity of a N2/O2/Ar
           mixture as returned by CoolProp.  Argon fraction is computed
           inside the surrogate C function as:

               x_Ar = 1 - x_N2 - x_O2

           Composition bounds correspond to typical dry air variations:

               x_N2 ∈ [0.70, 0.85]
               x_O2 ∈ [0.14, 0.25]
               x_Ar ∈ [0.005, 0.08]   (feasibility constraint only)

           Training uses CASTROSampling (Schenk & Haranczyk, 2024): sequential
           conditional LHS with bound permutation and greedy maximin selection.
           This guarantees space-filling coverage of the constrained simplex
           without naive rejection sampling.

           Evaluation conditions are fixed at T = 300 K, P = 1e5 Pa.

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


# Fixed evaluation conditions for this composition-only surrogate
_T_FIXED = 300.0   # K
_P_FIXED = 1e5     # Pa


@explicit_serialize
class MixtureViscosityExactSim(ModenaFireTask):
    """
    Evaluates N2/O2/Ar dynamic viscosity at a single composition point.

    x_Ar is inferred as ``1 - x_N2 - x_O2``; it is not a model input.
    The result (``eta``, Pa·s) is stored back into ``self['point']``.
    """

    def task(self, fw_spec):
        import CoolProp.CoolProp as CP

        x_N2 = self['point']['x_N2']
        x_O2 = self['point']['x_O2']
        x_Ar = 1.0 - x_N2 - x_O2

        AS = CP.AbstractState('HEOS', 'Nitrogen&Oxygen&Argon')
        AS.set_mole_fractions([x_N2, x_O2, x_Ar])
        AS.update(CP.PT_INPUTS, _P_FIXED, _T_FIXED)
        eta = AS.viscosity()

        self['point']['eta'] = eta
        print(
            f'x_N2={x_N2:.4f}  x_O2={x_O2:.4f}  x_Ar={x_Ar:.4f}'
            f'  η = {eta:.4e} Pa·s'
        )


# 2nd-order polynomial in (x_N2, x_O2) — 6 parameters.
# x_Ar = 1 - x_N2 - x_O2 is computed inside the C function; it is not an input.
f = CFunction(
    Ccode='''
#include "modena.h"
#include "math.h"

void mixtureViscosity_N2O2Ar
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
               + parameters[1] * x_N2
               + parameters[2] * x_O2
               + parameters[3] * x_N2 * x_N2
               + parameters[4] * x_N2 * x_O2
               + parameters[5] * x_O2 * x_O2;
}
''',
    inputs={
        'x_N2': {'min': 0.70, 'max': 0.85},   # nitrogen mole fraction
        'x_O2': {'min': 0.14, 'max': 0.25},   # oxygen mole fraction
        # x_Ar is derived — not an independent input
    },
    outputs={
        'eta': {'min': 0.0, 'max': 1e-3, 'argPos': 0},   # dynamic viscosity, Pa·s
    },
    parameters={
        'a00': {'min': -1e-4, 'max': 1e-4, 'argPos': 0},
        'a10': {'min': -1e-4, 'max': 1e-4, 'argPos': 1},
        'a01': {'min': -1e-4, 'max': 1e-4, 'argPos': 2},
        'a20': {'min': -1e-4, 'max': 1e-4, 'argPos': 3},
        'a11': {'min': -1e-4, 'max': 1e-4, 'argPos': 4},
        'a02': {'min': -1e-4, 'max': 1e-4, 'argPos': 5},
    },
)


@explicit_serialize
class MixtureViscosityValidationTask(FireTaskBase):
    """
    Loads the trained viscosity surrogate and compares it with CoolProp over
    a held-out composition grid.  Prints max and mean relative errors.
    """

    required_params = []
    optional_params = []

    def run_task(self, fw_spec):
        import CoolProp.CoolProp as CP
        import numpy as np

        model = modena.SurrogateModel.load('mixtureViscosity[fluid=N2O2Ar]')
        cModel = modena.libmodena.modena_model_t(
            model=model,
            parameters=list(model.parameters),
        )

        # Held-out grid: 3×3 in (x_N2, x_O2), excluding training compositions
        x_N2_test = [0.72, 0.78, 0.83]
        x_O2_test = [0.15, 0.19, 0.24]

        inputs  = [0.0] * cModel.inputs_size
        outputs = [0.0] * cModel.outputs_size

        n2_pos  = model.inputs_argPos('x_N2')
        o2_pos  = model.inputs_argPos('x_O2')
        eta_pos = model.outputs_argPos('eta')

        print(f'\n{"x_N2":>6}  {"x_O2":>6}  {"x_Ar":>6}'
              f'  {"η_ref [μPa·s]":>14}  {"η_sur [μPa·s]":>14}  {"err [%]":>8}')
        print('-' * 70)

        errors = []
        for x_N2 in x_N2_test:
            for x_O2 in x_O2_test:
                x_Ar = 1.0 - x_N2 - x_O2
                if x_Ar < 0:
                    continue

                AS = CP.AbstractState('HEOS', 'Nitrogen&Oxygen&Argon')
                AS.set_mole_fractions([x_N2, x_O2, x_Ar])
                AS.update(CP.PT_INPUTS, _P_FIXED, _T_FIXED)
                eta_ref = AS.viscosity()

                inputs[n2_pos] = x_N2
                inputs[o2_pos] = x_O2
                ret = cModel(inputs)
                eta_sur = ret[eta_pos]

                rel_err = abs(eta_sur - eta_ref) / eta_ref * 100
                errors.append(rel_err)
                print(
                    f'{x_N2:>6.4f}  {x_O2:>6.4f}  {x_Ar:>6.4f}'
                    f'  {eta_ref*1e6:>14.4f}  {eta_sur*1e6:>14.4f}  {rel_err:>7.2f}%'
                )

        print('-' * 70)
        print(f'Max relative error : {max(errors):.2f} %')
        print(f'Mean relative error: {np.mean(errors):.2f} %')

        return FWAction()


m = BackwardMappingModel(
    _id='mixtureViscosity[fluid=N2O2Ar]',
    surrogateFunction=f,
    exactTask=MixtureViscosityExactSim(),
    substituteModels=[],
    initialisationStrategy=Strategy.CASTROSampling(
        compositionGroup={
            'free': ['x_N2', 'x_O2'],
            'dependent': 'x_Ar',
            'dependentBounds': {'min': 0.005, 'max': 0.08},
        },
        nNewPoints=20,
        seed=42,
    ),
    outOfBoundsStrategy=Strategy.ForbidOutOfBounds(),
    parameterFittingStrategy=Strategy.NonLinFitWithErrorContol(
        crossValidation=Strategy.Holdout(testDataPercentage=0.2),
        acceptanceCriterion=Strategy.MaxError(
            threshold=0.005,             # 0.5 % relative error
            metric=RelativeError(),
        ),
        optimizer=Strategy.TrustRegionReflective(),
        improveErrorStrategy=Strategy.CASTROSampling(
            compositionGroup={
                'free': ['x_N2', 'x_O2'],
                'dependent': 'x_Ar',
                'dependentBounds': {'min': 0.005, 'max': 0.08},
            },
            nNewPoints=5,
            seed=None,
        ),
    ),
)
