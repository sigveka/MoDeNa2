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
@file      Implementation of flow rate model with substituted ideal gas.
@author    Henrik Rusche
@copyright 2014-2016, MoDeNa Project. GNU Public License.
@ingroup   twoTank
"""

import subprocess
import modena
from modena import BackwardMappingModel, CFunction, ModenaFireTask
import modena.Strategy as Strategy
from modena.utils import load_model_config, build_strategy
from fireworks.utilities.fw_utilities import explicit_serialize
from jinja2 import Template
import idealGas

_CFG = load_model_config(__file__)


# ********************************* Class ********************************** #
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
        ret = subprocess.call([self.find_binary('flowRateExact')])

        # This enables backward mapping capabilities (not needed in this example)
        self.handleReturnCode(ret)

        # Analyse output
        f = open('out.txt', 'r')
        self['point']['flowRate'] = float(f.readline())
        f.close()


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

    //const double D = inputs[0];
    //const double rho0 = inputs[1];
    //const double p0 = inputs[2];
    //const double p1 = p0*inputs[3];

    const double P0 = parameters[0];
    const double P1 = parameters[1];

    outputs[0] = M_PI*pow(D, 2.0)*P1*sqrt(P0*rho0*p0);
}
''',
    inputs=_CFG.surrogate.inputs_dict(),
    outputs=_CFG.surrogate.outputs_dict(),
    parameters=_CFG.surrogate.parameters_dict(),
)

m = BackwardMappingModel(
    _id= 'flowRate',
    surrogateFunction= f,
    exactTask= FlowRateExactSim(),
    substituteModels= [ idealGas.m ],
    **build_strategy(_CFG.strategy),
)
