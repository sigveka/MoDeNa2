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

from os import system
from os.path import abspath, dirname, join

import modena
from modena import ForwardMappingModel, BackwardMappingModel, SurrogateModel, CFunction, ModenaFireTask, IndexSet
import modena.Strategy as Strategy
from fireworks import Firework, Workflow, FWAction
from fireworks.utilities.fw_utilities import explicit_serialize
from blessings import Terminal
from jinja2 import Template


species = IndexSet(
    name  = 'species',
    names = [ 'H2O', 'N2', 'SO2' ],
#     parameters = {
#         'H2O' : { 'muZero' : 1e-6, 'muInf' : 1e-6, 'lambda' : 0.1 },
#         'N2'  : { 'muZero' : 1e-6, 'muInf' : 1e-6, 'lambda' : 0.1 },
#         'SO2' : { 'muZero' : 1e-6, 'muInf' : 1e-6, 'lambda' : 0.1 },
#     }
)


@explicit_serialize
class FlowRateExactSim(ModenaFireTask):
    """
    A FireTask that starts a microscopic code and updates the database.
    """

    def task(self, fw_spec):
        # Write input
        # See http://jinja.pocoo.org/docs/dev/templates/
        Template('''
{{ s['point']['D'] }}
{{ s['point']['rho0'] }}
{{ s['point']['p0'] }}
{{ s['point']['p1Byp0'] }}
        '''.strip()).stream(s=self).dump('in.txt')

        # Execute the application
        # In this simple example, this call stands for a complex microscopic
        # code - such as full 3D CFD simulation.
        # Source code in src/flowRateExact.C
        ret = system(join(abspath(dirname(__file__)),'bin','flowRateExact'))

        # This enables backward mapping capabilities (not needed in this example)
        self.handleReturnCode(ret)

        # Analyse output
        f = open('out.txt', 'r')
        self['point']['flowRate'] = float(f.readline())
        f.close()


# f = CFunction(
#     Ccode= '''
# #include "modena.h"
# #include "math.h"
# 
# void bird_carreau
# (
#     const modena_model_t* model,
#     const double* inputs,
#     double *outputs
# )
# {
#     {% block variables %}{% endblock %}
# 
# 
#     const double muZero = parameters[0];       // viscosity at zero shear rate  
#     const double muInf  = parameters[1];   // viscosity at infinite shear rate
#     const double lambda = parameters[2];                    // relaxation time
#     const double n_     = parameters[3];                        // power index
#     const double a_     = parameters[4];
# 
# 
#     outputs[0] = muInf + (muZero - muInf)*pow(1 + pow(lambda*dgdt, a_), (n_ - 1)/2);
# }
# ''',
#     # These are global bounds for the function
#     inputs={
#         'dgdt': { 'min': -273.15, 'max': 9e99 }, # shear rate
#     },
#     outputs={
#         'muEff': { 'min': 9e99, 'max': -9e99, 'argPos': 0 },
#     },
#     indices = {
#       'A' : species,
#     },
#     parameters={ # nu0 nuInf k n a
#         'muZero[A]' : { 'min': 0.0, 'max': 10.0, 'argPos': 0 },
#         'muInf[A]'  : { 'min': 0.0, 'max': 10.0, 'argPos': 1 },
#         'lambda[A]' : { 'min': 0.0, 'max': 10.0, 'argPos': 2 },
#         'n'         : { 'min': 0.0, 'max': 10.0, 'argPos': 3 },
#         'a'         : { 'min': 0.0, 'max': 10.0, 'argPos': 4 },
#     },
# )

f = CFunction(
    Ccode= '''
#include "modena.h"
#include "math.h"

void bird_carreau
(
    const modena_model_t* model,
    const double* inputs,
    double *outputs
)
{
    {% block variables %}{% endblock %}

    // Jinja2 synthesizes the input and parameter bindings above:
    //     const double dgdt   = inputs[0];
    //     const double muZero = parameters[0];   // zero-shear viscosity
    //     const double muInf  = parameters[1];   // infinite-shear viscosity
    //     const double lambda_ = parameters[2];  // relaxation time (renamed
    //                                            //   to avoid clash with
    //                                            //   the C++ reserved word)
    //     const double n_     = parameters[3];   // power index
    //     const double a_     = parameters[4];

    outputs[0] = muInf
               + (muZero - muInf)
                 * pow(1 + pow(lambda_*dgdt, a_), (n_ - 1)/2);
}
''',
    # Global bounds — argPos is auto-assigned from declaration order for
    # all three variable categories.
    inputs={
        'dgdt': { 'min': -273.15, 'max': 9e99 },
    },
    outputs={
        'muEff': { 'min': 9e99, 'max': -9e99 },
    },
    parameters={ # nu0 nuInf k n a
        'muZero':  { 'min': 0.0, 'max': 10.0 },
        'muInf':   { 'min': 0.0, 'max': 10.0 },
        # Rename `lambda` -> `lambda_` since the framework's Jinja2 template
        # emits `const double <name> = parameters[<i>];` and `lambda` is a
        # C++ reserved word (this file is also compiled by g++ inside
        # OpenFOAM).  `n` and `a` similarly renamed to `n_` and `a_` for
        # consistency and to avoid shadowing common math/loop identifiers.
        'lambda_': { 'min': 0.0, 'max': 10.0 },
        'n_':      { 'min': 0.0, 'max': 10.0 },
        'a_':      { 'min': 0.0, 'max': 10.0 },
    },
)

m = ForwardMappingModel(
    _id               = 'BirdCarreau',
    surrogateFunction = f,
    substituteModels  = [ ],
    parameters        = {
        'muZero':  1e-06,
        'muInf':   1e-06,
        'lambda_': 0.0,
        'n_':      1.0,
        'a_':      2.0,
    },
)

# m = ForwardMappingModel(
#     _id               = 'BirdCarreau[A=H2O]',
#     surrogateFunction = f,
#     substituteModels  = [ ],
#     parameters        = [1, 2],
# )

# m = BackwardMappingModel(
#     _id= 'BirdCarreau',
#     surrogateFunction= f,
#     exactTask= FlowRateExactSim(),
#     substituteModels= [ ],
#     initialisationStrategy= Strategy.InitialPoints(
#         initialPoints=
#         {
#             'T'      : [0.01, 0.01, 0.01, 0.01],
#             'rho0'   : [3.4, 3.5, 3.4, 3.5],
#             'p0'     : [2.8e5, 3.2e5, 2.8e5, 3.2e5],
#             'p1Byp0' : [0.03, 0.03, 0.04, 0.04],
#         },
#     ),
#     outOfBoundsStrategy= Strategy.ExtendSpaceStochasticSampling(
#         nNewPoints= 4
#     ),
#     parameterFittingStrategy= Strategy. NonLinFitWithErrorContol(
#         testDataPercentage= 0.2,
#         maxError= 0.5,
#         improveErrorStrategy= Strategy. NonLinFitWithErrorContol(
#             nNewPoints= 2,
#             constraints = "p0 / p1 > 0"
#         ),
#         maxIterations= 5 # Currently not used
#     ),
# )
