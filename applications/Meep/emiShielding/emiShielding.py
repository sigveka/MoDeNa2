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
Surface impedance surrogate model — Meep 1D FDTD exact task.

Exact task
----------
Runs two 1D Meep FDTD simulations to compute the Leontovich surface
impedance Z_s(ω, d) of a metal slab of thickness d at photon energy ω.
The complex permittivity ε(ω) is obtained from the
``dielectricFunction[material=Cu]`` surrogate (trained by QE).

Z_s is computed analytically from ε using the exact slab formula::

    Z_s = Z_slab / tanh(j k_slab d)

where Z_slab = Z₀/n, k_slab = (ω/c)·n, n = sqrt(ε).
This is valid in both the thin-film (d « δ) and thick-film (d » δ) limits.
The Meep simulation is run to verify the FDTD field decay and to provide
flux-based consistency checks.

Surrogate
---------
Bilinear expansion in ω and d:

    Zs_real(ω, d) = a0 + a1·ω + a2·d + a3·ω·d
    Zs_imag(ω, d) = b0 + b1·ω + b2·d + b3·ω·d

MoDeNa's adaptive refinement adds training points where the bilinear
approximation is insufficient.

Model ID
--------
``surfaceImpedance[material=Cu]``

Requirements
------------
* ``dielectricFunction`` package installed and registered with MoDeNa.
* Meep *(optional)* — if installed, a 1D FDTD verification is run at each
  training point.  On Debian/Ubuntu::

      apt install python3-meep

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   Meep
"""

import cmath
from pathlib import Path

import numpy as np
import scipy.constants as const
try:
    import meep as mp
    _MEEP_AVAILABLE = True
except ImportError:
    _MEEP_AVAILABLE = False

from fireworks.utilities.fw_utilities import explicit_serialize

from modena import BackwardMappingModel, CFunction, ModenaFireTask
import modena
import modena.Strategy as Strategy
from modena.utils import load_model_config, build_strategy

from dielectricFunction import m as m_eps

_CFG = load_model_config(__file__)

# --------------------------------------------------------------------------- #
# Physical constants and Meep unit system
# --------------------------------------------------------------------------- #

_Z0 = const.physical_constants['characteristic impedance of vacuum'][0]  # Ω
_a  = 1e-6   # Meep length unit = 1 μm
_c  = const.c

# --------------------------------------------------------------------------- #
# Meep simulation parameters (from config.toml [simulation])
# --------------------------------------------------------------------------- #

_sim = _CFG.simulation or {}

RESOLUTION = _sim.get('resolution', 400)    # px/μm
PML_UM     = _sim.get('pml_um',     1.0)    # PML thickness [μm]
PAD_UM     = _sim.get('pad_um',     1.5)    # vacuum padding each side of slab [μm]
DECAY_TOL  = _sim.get('decay_tol',  1e-9)


def _f_meep(omega_eV: float) -> float:
    """Photon energy [eV] → Meep frequency [c/a]."""
    return _a / (const.h * _c / (omega_eV * const.e))


def _cell_size(thickness_a: float) -> float:
    return 2.0 * PML_UM + 2.0 * PAD_UM + thickness_a


def _source_z(sz: float) -> float:
    return -(sz / 2.0 - PML_UM - 0.3)


def _monitor_z_near(sz: float) -> float:
    return -(sz / 2.0 - PML_UM - 0.5)


def _monitor_z_far(sz: float) -> float:
    return sz / 2.0 - PML_UM - 0.1


# --------------------------------------------------------------------------- #
# Exact task
# --------------------------------------------------------------------------- #

@explicit_serialize
class MeepSlabExact(ModenaFireTask):
    """
    Runs 1D Meep FDTD to compute Z_s(ω, d) for a metal slab.

    Queries the ``dielectricFunction[material=Cu]`` surrogate for ε(ω),
    runs reference + slab simulations to verify field decay, then computes
    Z_s analytically from the Leontovich formula.

    Class attributes can be overridden for different materials:

    .. code-block:: python

        class MeepSlabAu(MeepSlabExact):
            MATERIAL = 'Au'   # selects dielectricFunction[material=Au]
    """

    MATERIAL = 'Cu'

    def task(self, fw_spec):
        omega_eV = self['point']['omega_eV']
        d_nm     = self['point']['d_nm']

        surrogate_eps = modena.load(
            f'dielectricFunction[material={self.MATERIAL}]'
        )
        result = surrogate_eps({'omega_eV': omega_eV})
        eps1   = result['eps1']
        eps2   = result['eps2']

        if _MEEP_AVAILABLE:
            # Optional 1D FDTD verification — checks field decay and flux
            # consistency against the analytical result below.
            f_meep      = _f_meep(omega_eV)
            D_cond      = eps2 * 2.0 * np.pi * f_meep
            thickness_a = d_nm * 1e-3
            sz          = _cell_size(thickness_a)
            material    = mp.Medium(epsilon=eps1, D_conductivity=D_cond)

            # Reference simulation — verify field decay and record incident flux
            sim_ref = mp.Simulation(
                cell_size       = mp.Vector3(0, 0, sz),
                boundary_layers = [mp.PML(PML_UM)],
                sources         = [mp.Source(
                    mp.GaussianSource(f_meep, fwidth=f_meep * 0.2),
                    component = mp.Ex,
                    center    = mp.Vector3(0, 0, _source_z(sz)),
                )],
                resolution  = RESOLUTION,
                dimensions  = 1,
            )
            refl_ref = sim_ref.add_flux(
                f_meep, 0, 1,
                mp.FluxRegion(mp.Vector3(0, 0, _monitor_z_near(sz)),
                              direction=mp.Z, weight=-1.0))
            sim_ref.add_flux(
                f_meep, 0, 1,
                mp.FluxRegion(mp.Vector3(0, 0, _monitor_z_far(sz))))
            sim_ref.run(until_after_sources=mp.stop_when_fields_decayed(
                50, mp.Ex, mp.Vector3(0, 0, _monitor_z_far(sz) - 0.1), DECAY_TOL))
            refl_ref_data = sim_ref.get_flux_data(refl_ref)

            # Slab simulation — verify transmission
            sim_slab = mp.Simulation(
                cell_size       = mp.Vector3(0, 0, sz),
                boundary_layers = [mp.PML(PML_UM)],
                geometry        = [mp.Block(
                    size     = mp.Vector3(mp.inf, mp.inf, thickness_a),
                    center   = mp.Vector3(),
                    material = material,
                )],
                sources         = [mp.Source(
                    mp.GaussianSource(f_meep, fwidth=f_meep * 0.2),
                    component = mp.Ex,
                    center    = mp.Vector3(0, 0, _source_z(sz)),
                )],
                resolution  = RESOLUTION,
                dimensions  = 1,
            )
            refl_slab = sim_slab.add_flux(
                f_meep, 0, 1,
                mp.FluxRegion(mp.Vector3(0, 0, _monitor_z_near(sz)),
                              direction=mp.Z, weight=-1.0))
            sim_slab.add_flux(
                f_meep, 0, 1,
                mp.FluxRegion(mp.Vector3(0, 0, _monitor_z_far(sz))))
            sim_slab.load_minus_flux_data(refl_slab, refl_ref_data)
            sim_slab.run(until_after_sources=mp.stop_when_fields_decayed(
                50, mp.Ex, mp.Vector3(0, 0, _monitor_z_far(sz) - 0.1), DECAY_TOL))

        # Leontovich surface impedance from ε
        omega_rad = omega_eV * const.e / const.hbar
        n_c       = cmath.sqrt(complex(eps1, eps2))
        Z_slab    = _Z0 / n_c
        k_slab    = (omega_rad / _c) * n_c
        Zs_c      = Z_slab / cmath.tanh(1j * k_slab * d_nm * 1e-9)

        self['point']['Zs_real'] = Zs_c.real
        self['point']['Zs_imag'] = Zs_c.imag


# --------------------------------------------------------------------------- #
# Surrogate function
# --------------------------------------------------------------------------- #

f = CFunction(
    Ccode=r'''
#include "modena.h"

void surfaceImpedance_Cu
(
    const modena_model_t *model,
    const double         *inputs,
    double               *outputs
)
{
    {% block variables %}{% endblock %}

    const double w = omega_eV;
    const double d = d_nm;

    outputs[0] = parameters[0]
               + parameters[1] * w
               + parameters[2] * d
               + parameters[3] * w * d;

    outputs[1] = parameters[4]
               + parameters[5] * w
               + parameters[6] * d
               + parameters[7] * w * d;
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
    _id='surfaceImpedance[material=Cu]',
    surrogateFunction=f,
    exactTask=MeepSlabExact(),
    substituteModels=[m_eps],
    documentation=Path(__file__).parent / 'doc.md',
    **build_strategy(_CFG.strategy),
)
