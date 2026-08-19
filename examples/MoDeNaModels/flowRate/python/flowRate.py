'''@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2016 MoDeNa Consortium, All rights reserved.

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

"""
@file      Implementation of flow rate model.
@author    Henrik Rusche
@copyright 2014-2016, MoDeNa Project. GNU Public License.
@ingroup   twoTank
"""

import modena
from modena import ForwardMappingModel, BackwardMappingModel, SurrogateModel, CFunction, ModenaFireTask
import modena.Strategy as Strategy
from fireworks import Firework, Workflow, FWAction
from fireworks.utilities.fw_utilities import explicit_serialize
from jinja2 import Template


# ********************************* Class ********************************** #
@explicit_serialize
class FlowRateExactSim(ModenaFireTask):
    """
    A FireTask that starts a microscopic code and updates the database.
    """

    def task(self, fw_spec):
        # Write input.  The legacy microscopic code reads from in.txt.
        # See http://jinja.pocoo.org/docs/dev/templates/
        Template('''
{{ s['point']['D'] }}
{{ s['point']['rho0'] }}
{{ s['point']['p0'] }}
{{ s['point']['p1Byp0'] }}
        '''.strip()).stream(s=self).dump('in.txt')

        # Execute the application.  In this simple example the binary stands
        # for a complex microscopic code such as a full 3D CFD simulation.
        # ``run_binary`` locates the executable, captures stdout/stderr into
        # the modena logger, and dispatches return codes 200/201/202 through
        # ``handleReturnCode`` automatically.  Source in src/flowRateExact.C.
        self.run_binary('flowRateExact')

        # Analyse output
        with open('out.txt', 'r') as f:
            self['point']['flowRate'] = float(f.readline())


f = CFunction(
    Ccode= '''
#include "modena.h"
#include "math.h"

void two_tank_flowRate
(
    const modena_model_t* model,
    const double* inputs,
    double *outputs
)
{
    {% block variables %}{% endblock %}

    // The Jinja2 template above synthesizes:
    //   const double D      = inputs[0];
    //   const double rho0   = inputs[1];
    //   const double p0     = inputs[2];
    //   const double p1Byp0 = inputs[3];
    //   const double P0     = parameters[0];   // named binding for the parameter
    //   const double P1     = parameters[1];
    //
    // Reference parameters by their declared names instead of raw indices —
    // reordering the `parameters={}` dict below then never risks a silent
    // corruption of an existing fit.

    outputs[0] = M_PI*pow(D, 2.0)*P1*sqrt(P0*rho0*p0);
}
''',
    # Global bounds for the function.  argPos is auto-assigned from dict
    # insertion order for all three categories (inputs, outputs, parameters);
    # supplying it explicitly is now rejected with a TypeError.
    inputs={
        'D':      { 'min': 0, 'max': 9e99 },
        'rho0':   { 'min': 0, 'max': 9e99 },
        'p0':     { 'min': 0, 'max': 9e99 },
        'p1Byp0': { 'min': 0, 'max': 1.0 },
    },
    outputs={
        'flowRate': { 'min': 9e99, 'max': -9e99 },
    },
    parameters={
        'P0': { 'min': 0.0, 'max': 10.0 },
        'P1': { 'min': 0.0, 'max': 10.0 },
    },
)



m = BackwardMappingModel(
    _id= r'flowRate',
    surrogateFunction= f,
    exactTask= FlowRateExactSim(),
    substituteModels= [ ],
    initialisationStrategy= Strategy.InitialPoints(
        initialPoints=
        {
            'D': [0.01, 0.01, 0.01, 0.01],
            'rho0': [3.4, 3.5, 3.4, 3.5],
            'p0': [2.8e5, 3.2e5, 2.8e5, 3.2e5],
            'p1Byp0': [0.03, 0.03, 0.04, 0.04],
        },
    ),
    outOfBoundsStrategy= Strategy.ExtendSpaceStochasticSampling(
        nNewPoints= 4,
        sampler= Strategy.LatinHypercube(),
    ),
    parameterFittingStrategy= Strategy.NonLinFitWithErrorContol(
        crossValidation= Strategy.Holdout(testDataPercentage=0.2),
        acceptanceCriterion= Strategy.MaxError(threshold=0.5),
        optimizer= Strategy.TrustRegionReflective(),
        # StochasticSampling is the only ImproveErrorStrategy: it is what
        # collects more points when the fit is rejected.  This used to name
        # NonLinFitWithErrorContol -- a ParameterFittingStrategy, whose
        # newPoints() is the unimplemented base method -- so a rejected fit
        # would have raised NotImplementedError.  Latent because flowRate
        # fits to ~2e-07 against a threshold of 0.5, so the branch never ran.
        improveErrorStrategy= Strategy.StochasticSampling(
            nNewPoints= 2,
        ),
        maxIterations= 5 # Currently not used
    ),
)

