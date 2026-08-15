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
Structural shielding effectiveness surrogate model — NGSolve 3D FEM exact task.

Exact task
----------
Runs a full-wave 3D frequency-domain FEM (NGSolve + Netgen) to compute the
shielding effectiveness SE(ω) of a metallic enclosure with an aperture.
The metal walls use Leontovich impedance boundary conditions with Z_s(ω, d)
obtained from the ``surfaceImpedance[material=Cu]`` surrogate, so the metal
skin depth is never resolved in the 3D mesh.

Surrogate
---------
Quadratic polynomial in ω:

    SE_dB(ω) = c0 + c1·ω + c2·ω²

Model ID
--------
``structuralSE[geometry=enclosure]``

Requirements
------------
* NGSolve and Netgen::

      pip install ngsolve netgen-mesher

* ``emiShielding`` package installed and registered with MoDeNa.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   NGSolve
"""

from pathlib import Path
import numpy as np
import scipy.constants as const
from fireworks.utilities.fw_utilities import explicit_serialize

from modena import BackwardMappingModel, CFunction, ModenaFireTask
import modena
import modena.Strategy as Strategy
from modena.utils import load_model_config, build_strategy

from emiShielding import m as m_slab

_CFG = load_model_config(__file__)
_sim = _CFG.simulation or {}

_c = const.c


# --------------------------------------------------------------------------- #
# Exact task
# --------------------------------------------------------------------------- #

@explicit_serialize
class NGSolveExact(ModenaFireTask):
    """
    Runs NGSolve 3D frequency-domain FEM to compute SE(ω) for a metallic
    enclosure with an aperture.

    Geometry (Netgen CSG):
        Cubic enclosure (BOX_MM side) with a square aperture (APT_MM side)
        on one face.  A PML shell (PML_MM thick) surrounds the outer domain.
        Plane-wave incidence on the aperture face.

    The shield surfaces use Leontovich impedance BCs:
        n × H = (1/Z_s) E_tan
    with Z_s from the ``surfaceImpedance[material=Cu]`` surrogate.

    Class attributes can be overridden for different geometries:

    .. code-block:: python

        class NGSolveExactLargeBox(NGSolveExact):
            BOX_MM = 100.0
            APT_MM = 10.0
    """

    BOX_MM = _sim.get('box_mm',   20.0)   # cubic enclosure side [mm]
    APT_MM = _sim.get('apt_mm',    5.0)   # square aperture side [mm]
    PML_MM = _sim.get('pml_mm',    5.0)   # PML shell thickness [mm]
    D_NM   = _sim.get('d_nm',    100.0)   # Cu wall thickness [nm] for Z_s lookup

    def task(self, fw_spec):
        omega_eV = self['point']['omega_eV']

        surrogate_Zs = modena.load('surfaceImpedance[material=Cu]')
        res          = surrogate_Zs({'omega_eV': omega_eV, 'd_nm': self.D_NM})
        Zs           = complex(res['Zs_real'], res['Zs_imag'])

        import ngsolve
        from netgen.csg import CSGeometry, OrthoBrick, Pnt

        omega_rad = omega_eV * const.e / const.hbar
        k0mm      = (omega_rad / _c) * 1e-3   # wave number [1/mm]

        box = self.BOX_MM / 2.0
        apt = self.APT_MM / 2.0
        pml = self.PML_MM

        geo = CSGeometry()
        outer     = OrthoBrick(Pnt(-(box+pml), -(box+pml), -(box+pml)),
                               Pnt( box+pml,    box+pml,    box+pml)).bc('outer')
        enclosure = OrthoBrick(Pnt(-box, -box, -box), Pnt(box, box, box))
        aperture  = OrthoBrick(Pnt(-apt, -apt, box-1e-3), Pnt(apt, apt, box+1e-3))
        interior  = enclosure - aperture
        geo.Add((outer - enclosure).bc('exterior'), col=[1,1,0], name='exterior')
        geo.Add(interior.bc('shield'),              col=[0,0,1], name='interior')

        mesh = ngsolve.Mesh(geo.GenerateMesh(maxh=_sim.get('mesh_maxh', 3.0)))
        mesh.Curve(3)

        order = _sim.get('order', 2)
        fes   = ngsolve.HCurl(mesh, order=order, complex=True, dirichlet='outer')
        u, v  = fes.TnT()

        k0c   = ngsolve.CF(k0mm)
        a     = ngsolve.BilinearForm(fes)
        a    += ngsolve.InnerProduct(ngsolve.curl(u), ngsolve.curl(v)) * ngsolve.dx
        a    += -k0c**2 * ngsolve.InnerProduct(u, v) * ngsolve.dx
        a    += (ngsolve.CF(1.0 / Zs) *
                 ngsolve.InnerProduct(u.Trace(), v.Trace())) * ngsolve.ds('shield')

        z_coord = ngsolve.specialcf.point(2)
        E_inc   = ngsolve.CoefficientFunction((
            ngsolve.exp(1j * k0c * z_coord),
            ngsolve.CF(0),
            ngsolve.CF(0),
        ))

        f_rhs  = ngsolve.LinearForm(fes)
        f_rhs += ngsolve.CF(0) * v[0] * ngsolve.dx

        with ngsolve.TaskManager():
            a.Assemble()
            f_rhs.Assemble()

        gf = ngsolve.GridFunction(fes)
        gf.Set(E_inc, ngsolve.BND)

        res_vec       = f_rhs.vec.CreateVector()
        res_vec.data  = f_rhs.vec - a.mat * gf.vec
        gf.vec.data  += a.mat.Inverse(fes.FreeDofs(), inverse='sparsecholesky') * res_vec

        E_probe     = gf(mesh(0.0, 0.0, 0.0))
        E_probe_mag = abs(complex(E_probe[0]))
        SE_dB       = -20.0 * np.log10(max(E_probe_mag, 1e-20))

        self['point']['SE_dB'] = float(SE_dB)


# --------------------------------------------------------------------------- #
# Surrogate function
# --------------------------------------------------------------------------- #

f = CFunction(
    Ccode=r'''
#include "modena.h"

void structuralSE_enclosure
(
    const modena_model_t *model,
    const double         *inputs,
    double               *outputs
)
{
    {% block variables %}{% endblock %}

    const double w  = omega_eV;
    const double w2 = w * w;

    outputs[0] = parameters[0]
               + parameters[1] * w
               + parameters[2] * w2;
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
    _id='structuralSE[geometry=enclosure]',
    surrogateFunction=f,
    exactTask=NGSolveExact(),
    substituteModels=[m_slab],
    documentation=Path(__file__).parent / 'doc.md',
    **build_strategy(_CFG.strategy),
)
