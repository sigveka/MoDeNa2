"""
@file      CO2 density surrogate model backed by CoolProp.
@details
           Trains a 3rd-order bivariate polynomial in (T, P) to reproduce the
           density of CO2 as returned by CoolProp.PropsSI.  The surrogate
           replaces the CoolProp call in macroscopic simulation codes.

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
class CoolPropExactSim(ModenaFireTask):
    """
    Evaluates CO2 density at a single (T, P) point using CoolProp and
    stores the result in the surrogate model's fitData.
    """

    def task(self, fw_spec):
        import CoolProp.CoolProp as CP

        T = self['point']['T']
        P = self['point']['P']
        rho = CP.PropsSI('D', 'T', T, 'P', P, 'CO2')
        self['point']['rho'] = rho
        print(f'T = {T:.1f} K   P = {P:.0f} Pa   rho = {rho:.4f} kg/m³')


# 3rd-order bivariate polynomial in T and P (10 parameters).
# The Jinja2 {{ block variables }} placeholder is mandatory — MoDeNa fills it
# with "const double T = inputs[0]; const double P = inputs[1];" etc.
f = CFunction(
    Ccode='''
#include "modena.h"
#include "math.h"

void density_CO2
(
    const modena_model_t* model,
    const double*         inputs,
    double*               outputs
)
{
    {% block variables %}{% endblock %}

    outputs[0] = parameters[0]
               + parameters[1] * T
               + parameters[2] * P
               + parameters[3] * T * T
               + parameters[4] * T * P
               + parameters[5] * P * P
               + parameters[6] * T * T * T
               + parameters[7] * T * T * P
               + parameters[8] * T * P * P
               + parameters[9] * P * P * P;
}
''',
    inputs={
        'T': {'min': 250.0, 'max': 350.0},   # K
        'P': {'min': 1e5,   'max': 2e6},      # Pa (below CO2 critical: 7.377 MPa)
    },
    outputs={
        'rho': {'min': 0.0, 'max': 200.0, 'argPos': 0},  # kg/m³
    },
    parameters={
        'a00': {'min': -1e10, 'max': 1e10, 'argPos': 0},
        'a10': {'min': -1e10, 'max': 1e10, 'argPos': 1},
        'a01': {'min': -1e10, 'max': 1e10, 'argPos': 2},
        'a20': {'min': -1e10, 'max': 1e10, 'argPos': 3},
        'a11': {'min': -1e10, 'max': 1e10, 'argPos': 4},
        'a02': {'min': -1e10, 'max': 1e10, 'argPos': 5},
        'a30': {'min': -1e10, 'max': 1e10, 'argPos': 6},
        'a21': {'min': -1e10, 'max': 1e10, 'argPos': 7},
        'a12': {'min': -1e10, 'max': 1e10, 'argPos': 8},
        'a03': {'min': -1e10, 'max': 1e10, 'argPos': 9},
    },
)

@explicit_serialize
class CoolPropValidationTask(FireTaskBase):
    """
    Loads the trained density surrogate, evaluates it at a test grid, and
    compares with CoolProp reference values.  Prints a summary table.
    """

    required_params = []
    optional_params = []

    def run_task(self, fw_spec):
        import CoolProp.CoolProp as CP
        import numpy as np

        model = modena.SurrogateModel.load('density[fluid=CO2]')
        cModel = modena.libmodena.modena_model_t(
            model=model,
            parameters=list(model.parameters),
        )

        # Test grid — deliberately offset from training points
        T_test = [270.0, 290.0, 320.0, 345.0]
        P_test  = [3e5,  8e5,   1.5e6,  1.8e6]

        inputs  = [0.0] * cModel.inputs_size()
        outputs = [0.0] * cModel.outputs_size()

        T_pos   = model.inputs_argPos('T')
        P_pos   = model.inputs_argPos('P')
        rho_pos = model.outputs_argPos('rho')

        print(f'\n{"T [K]":>8}  {"P [Pa]":>10}  {"rho_ref":>10}  {"rho_sur":>10}  {"err [%]":>8}')
        print('-' * 55)

        errors = []
        for T in T_test:
            for P in P_test:
                rho_ref = CP.PropsSI('D', 'T', T, 'P', P, 'CO2')

                inputs[T_pos] = T
                inputs[P_pos] = P
                ret = cModel(inputs)
                rho_sur = ret[rho_pos]

                rel_err = abs(rho_sur - rho_ref) / rho_ref * 100
                errors.append(rel_err)
                print(f'{T:>8.1f}  {P:>10.0f}  {rho_ref:>10.4f}  {rho_sur:>10.4f}  {rel_err:>7.2f}%')

        print('-' * 55)
        print(f'Max relative error : {max(errors):.2f} %')
        print(f'Mean relative error: {np.mean(errors):.2f} %')

        return FWAction()


m = BackwardMappingModel(
    _id='density[fluid=CO2]',
    surrogateFunction=f,
    exactTask=CoolPropExactSim(),
    substituteModels=[],
    initialisationStrategy=Strategy.InitialPoints(
        initialPoints={
            # 3 × 3 grid covering the training domain
            'T': [260.0, 260.0, 260.0, 305.0, 305.0, 305.0, 350.0, 350.0, 350.0],
            'P': [1e5,   1e6,   2e6,   1e5,   1e6,   2e6,   1e5,   1e6,   2e6],
        },
    ),
    outOfBoundsStrategy=Strategy.ExtendSpaceStochasticSampling(
        nNewPoints=4,
        sampler=Strategy.LatinHypercube(),
    ),
    parameterFittingStrategy=Strategy.NonLinFitWithErrorContol(
        crossValidation=Strategy.Holdout(testDataPercentage=0.2),
        acceptanceCriterion=Strategy.MaxError(
            threshold=0.02,          # 2 % relative error
            metric=RelativeError(),
        ),
        optimizer=Strategy.TrustRegionReflective(),
        improveErrorStrategy=Strategy.StochasticSampling(
            nNewPoints=4,
            sampler=Strategy.LatinHypercube(),
        ),
    ),
)
