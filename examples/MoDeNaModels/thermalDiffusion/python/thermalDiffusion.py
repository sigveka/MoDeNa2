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

"""
@file
Temperature-dependent thermal conductivity surrogate model.

The exact simulator evaluates the power-law correlation

    k(T) = k_ref * (T / T_ref)^n

with k_ref = 1.0 W/(m·K), T_ref = 300 K, n = 0.6.  This represents an
expensive material-property calculation (DFT, molecular dynamics, experiment).

The surrogate is a quadratic polynomial in T fitted by the MoDeNa
backward-mapping loop over the temperature range [273, 1500] K.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   FEniCS
"""

from fireworks.utilities.fw_utilities import explicit_serialize
from modena import BackwardMappingModel, CFunction, ModenaFireTask
import modena.Strategy as Strategy
from modena.utils import load_model_config, build_strategy

_CFG = load_model_config(__file__)
_sim = _CFG.simulation or {}


# --------------------------------------------------------------------------- #
# Exact task
# --------------------------------------------------------------------------- #

@explicit_serialize
class ThermalConductivityExact(ModenaFireTask):
    """
    Evaluates thermal conductivity at a single temperature point.

    Represents an expensive material-property calculation.  In this example
    it computes the power-law correlation k(T) = k_ref * (T / T_ref)^n.
    """

    def task(self, fw_spec):
        T     = self['point']['T']
        k_ref = _sim.get('k_ref', 1.0)    # W/(m·K) at T_ref
        T_ref = _sim.get('T_ref', 300.0)  # K
        n     = _sim.get('n',     0.6)
        self['point']['k'] = k_ref * (T / T_ref) ** n


# --------------------------------------------------------------------------- #
# Surrogate function (quadratic polynomial)
# --------------------------------------------------------------------------- #

f = CFunction(
    Ccode=r'''
#include "modena.h"

void thermalDiffusion_k
(
    const modena_model_t *model,
    const double         *inputs,
    double               *outputs
)
{
    {% block variables %}{% endblock %}

    outputs[0] = parameters[0]
               + parameters[1] * T
               + parameters[2] * T * T;
}
''',
    inputs=_CFG.surrogate.inputs_dict(),
    outputs=_CFG.surrogate.outputs_dict(),
    parameters=_CFG.surrogate.parameters_dict(),
)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

m = BackwardMappingModel(
    _id='thermalDiffusion',
    surrogateFunction=f,
    exactTask=ThermalConductivityExact(),
    substituteModels=[],
    **build_strategy(_CFG.strategy),
)
