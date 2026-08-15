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
Optical dielectric function surrogate model — Quantum ESPRESSO exact task.

Exact task
----------
Runs a Quantum ESPRESSO pw.x SCF + NSCF calculation followed by epsilon.x
to compute the optical dielectric function ε(ω) = ε₁(ω) + i ε₂(ω) of a
metal at a single photon energy ω.  The independent-particle approximation
(IPA) is used; local-field effects are neglected.

Workflow per training point
~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. ``pw.x < scf.in``   — SCF ground state (8×8×8 k-mesh)
2. ``pw.x < nscf.in``  — NSCF with denser k-mesh (16×16×16) and more bands
3. ``epsilon.x < epsilon.in`` — optical spectrum via Ehrenreich-Cohen formula
4. Interpolate eps_r.dat / eps_i.dat at the requested photon energy

Surrogate
---------
Two cubic polynomials in ω (photon energy in eV), shared across materials:

    ε₁(ω) = p0 + p1·ω + p2·ω² + p3·ω³
    ε₂(ω) = q0 + q1·ω + q2·ω² + q3·ω³

Each material gets its own fitted coefficients stored in MongoDB.

Supported materials
-------------------
Defined by ``ShieldingMaterials`` (an ``IndexSet``).  Currently: Cu, Au, Ag.
Add new metals by adding a ``_MaterialSpec`` entry to ``_MATERIAL_SPECS``.
No new class is needed.

Usage
-----
    from dielectricFunction import models, ShieldingMaterials
    m_cu = models['Cu']
    m_au = models['Au']

    # or the default (Cu) convenience alias:
    from dielectricFunction import m

Model IDs
---------
``dielectricFunction[material=Cu]``, ``dielectricFunction[material=Au]``, …

Requirements
------------
* Quantum ESPRESSO ``pw.x`` and ``epsilon.x`` on PATH, or set
  ``QE_BIN_DIR`` to the directory containing them.
* Per-material norm-conserving PBE pseudopotentials (e.g. ``Cu.upf``) in
  ``~/.modena/data/pseudo/``, ``QE_PSEUDO_DIR``, or a standard search path.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   QuantumEspresso
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fireworks.utilities.fw_utilities import explicit_serialize
from jinja2 import Template

from modena import BackwardMappingModel, CFunction, IndexSet, ModenaFireTask
from modena.utils import find_executable, find_file, load_model_config, build_strategy
import modena.Strategy as Strategy

_CFG = load_model_config(__file__)


# --------------------------------------------------------------------------- #
# Material index set
# --------------------------------------------------------------------------- #

class ShieldingMaterials(IndexSet):
    """Registry of metals for which a dielectricFunction surrogate exists.

    The material list is driven by ``[[materials]]`` in ``config.toml``.
    Add a new metal there — no Python change needed.
    """
    def __init__(self):
        names = [m.name for m in _CFG.materials]
        super().__init__(name='shieldingMaterials', names=names)


# --------------------------------------------------------------------------- #
# Material specifications
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _MaterialSpec:
    """All material-specific DFT parameters needed for a QE calculation."""
    name:        str
    celldm1:     float   # FCC lattice parameter in Bohr
    mass:        float   # g/mol
    pseudo_file: str
    nbnd:        int = 20


_MATERIAL_SPECS: list[_MaterialSpec] = [
    _MaterialSpec(
        m.name,
        m.celldm1,     # type: ignore[attr-defined]
        m.mass,        # type: ignore[attr-defined]
        m.pseudo_file, # type: ignore[attr-defined]
        nbnd=getattr(m, 'nbnd', 20),
    )
    for m in _CFG.materials
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_QE_DIR = Path(__file__).parent / 'qe'

_PSEUDO_SEARCH_DIRS = [
    Path(__file__).parent / 'pseudo',   # bundled with the package
    Path.home() / '.modena' / 'data' / 'pseudo',
    Path.home() / 'pseudo',
    Path.home() / 'qe' / 'pseudo',
    Path('/usr/share/espresso/pseudo'),
    Path('/opt/qe/pseudo'),
]


def _render(template_name: str, variables: dict) -> str:
    """Render a Jinja2 QE input template."""
    return Template((_QE_DIR / template_name).read_text()).render(**variables)


def _run_qe(exe: str, input_text: str, input_file: str) -> None:
    """Write input and run a QE executable, raising RuntimeError on failure."""
    Path(input_file).write_text(input_text)
    result = subprocess.run(
        [exe, '-in', input_file],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{exe} failed (exit {result.returncode}):\n{result.stderr}"
        )


def _interpolate_eps(filepath: str, omega_eV: float) -> float:
    """Interpolate ε₁ or ε₂ at omega_eV from a QE epsilon.x output file.

    QE epsilon.x writes either ``eps_r.dat`` (real part) or ``eps_i.dat``
    (imaginary part) with columns::

        energy[eV]  eps_xx  eps_yy  eps_zz  eps_avg

    For cubic metals, xx == yy == zz, so we use the average column.
    """
    data = np.loadtxt(filepath, comments='#')
    energies = data[:, 0]
    eps_avg  = data[:, 4]
    if omega_eV < energies[0] or omega_eV > energies[-1]:
        raise ValueError(
            f"omega_eV={omega_eV:.3f} eV outside QE epsilon.x range "
            f"[{energies[0]:.2f}, {energies[-1]:.2f}] eV."
        )
    return float(np.interp(omega_eV, energies, eps_avg))


# --------------------------------------------------------------------------- #
# Exact task base class
# --------------------------------------------------------------------------- #

class DielectricFunctionQE(ModenaFireTask):
    """Base class for QE-based dielectric function exact tasks.

    Do not subclass manually.  Use ``_make_task_class()`` instead, which
    creates a correctly registered subclass from a ``_MaterialSpec``.
    """

    MATERIAL    = NotImplemented
    CELLDM1     = NotImplemented
    MASS        = NotImplemented
    PSEUDO_FILE = NotImplemented
    NBND        = 20

    # Defaults — overridden per-class by _make_task_class() from config.toml
    ECUTWFC        = 60
    ECUTRHO        = 600
    KGRID_SCF      = 8
    KGRID_NSCF     = 16
    EPS_WMIN       = 0.0
    EPS_WMAX       = 7.0
    EPS_NW         = 1000
    EPS_INTERSMEAR = 0.1

    def task(self, fw_spec):
        omega_eV = self['point']['omega_eV']
        T        = self['point'].get('T', 300.0)

        pw_exe  = find_executable('pw.x',      env_var='QE_BIN_DIR')
        eps_exe = find_executable('epsilon.x',  env_var='QE_BIN_DIR')
        pseudo  = find_file(
            self.PSEUDO_FILE,
            [Path('.')] + _PSEUDO_SEARCH_DIRS,
            env_var='QE_PSEUDO_DIR',
        )

        degauss = max(0.02, 8.617e-5 * T / 13.606)

        prefix = 'modena_eps'
        outdir = str(Path('qe_out').resolve())
        Path(outdir).mkdir(exist_ok=True)

        base_vars = dict(
            prefix      = prefix,
            outdir      = outdir,
            pseudo_dir  = str(Path(pseudo).parent),
            celldm1     = self.CELLDM1,
            ecutwfc     = self.ECUTWFC,
            ecutrho     = self.ECUTRHO,
            atom_type   = self.MATERIAL,
            mass        = self.MASS,
            pseudo_file = Path(pseudo).name,
            degauss     = degauss,
        )

        _run_qe(pw_exe,
                _render('scf.in.j2', {**base_vars, 'kgrid_scf': self.KGRID_SCF}),
                'scf.in')
        _run_qe(pw_exe,
                _render('nscf.in.j2', {**base_vars,
                                        'kgrid_nscf': self.KGRID_NSCF,
                                        'nbnd':       self.NBND}),
                'nscf.in')
        _run_qe(eps_exe,
                _render('epsilon.in.j2', dict(
                    prefix     = prefix,
                    outdir     = outdir,
                    intersmear = self.EPS_INTERSMEAR,
                    wmin       = self.EPS_WMIN,
                    wmax       = self.EPS_WMAX,
                    nw         = self.EPS_NW,
                )),
                'epsilon.in')

        self['point']['eps1'] = _interpolate_eps('eps_r.dat', omega_eV)
        self['point']['eps2'] = _interpolate_eps('eps_i.dat', omega_eV)


# --------------------------------------------------------------------------- #
# Task-class factory
# --------------------------------------------------------------------------- #

def _make_task_class(spec: _MaterialSpec):
    """Return an ``@explicit_serialize`` task class for the given material.

    The generated class has the same ``__name__`` and ``__module__`` as a
    hand-written subclass would, so the FireWorks ``_fw_name`` is identical
    (e.g. ``'dielectricFunction::DielectricFunctionCu'``).  Existing MongoDB
    documents remain compatible.

    Simulation parameters are overridden from ``config.toml [simulation]``
    when present.
    """
    sim = _CFG.simulation or {}
    attrs = {
        '__module__':  __name__,
        'MATERIAL':    spec.name,
        'CELLDM1':     spec.celldm1,
        'MASS':        spec.mass,
        'PSEUDO_FILE': spec.pseudo_file,
        'NBND':        spec.nbnd,
    }
    _SIM_MAP = {
        'ecutwfc':        'ECUTWFC',
        'ecutrho':        'ECUTRHO',
        'kgrid_scf':      'KGRID_SCF',
        'kgrid_nscf':     'KGRID_NSCF',
        'eps_wmin':       'EPS_WMIN',
        'eps_wmax':       'EPS_WMAX',
        'eps_nw':         'EPS_NW',
        'eps_intersmear': 'EPS_INTERSMEAR',
    }
    for toml_key, cls_attr in _SIM_MAP.items():
        if toml_key in sim:
            attrs[cls_attr] = sim[toml_key]

    cls = type(f'DielectricFunction{spec.name}', (DielectricFunctionQE,), attrs)
    return explicit_serialize(cls)


# --------------------------------------------------------------------------- #
# Shared surrogate function
# --------------------------------------------------------------------------- #
# Same cubic polynomial form for all FCC noble/transition metals.
# Each material gets its own fitted coefficients (p0–p3, q0–q3) stored in
# MongoDB per BackwardMappingModel instance.

f = CFunction(
    Ccode=r'''
#include "modena.h"

void dielectricFunction_poly
(
    const modena_model_t *model,
    const double         *inputs,
    double               *outputs
)
{
    {% block variables %}{% endblock %}

    const double w  = omega_eV;
    const double w2 = w * w;
    const double w3 = w * w2;

    outputs[0] = parameters[0]
               + parameters[1] * w
               + parameters[2] * w2
               + parameters[3] * w3;

    outputs[1] = parameters[4]
               + parameters[5] * w
               + parameters[6] * w2
               + parameters[7] * w3;
}
''',
    inputs=_CFG.surrogate.inputs_dict(),
    outputs=_CFG.surrogate.outputs_dict(),
    parameters=_CFG.surrogate.parameters_dict(),
)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def make_dielectric_model(mat: str, task: DielectricFunctionQE) -> BackwardMappingModel:
    """Create a dielectricFunction surrogate model for the given material.

    Args:
        mat:  Material symbol, e.g. ``'Cu'``.  Must be in
              ``ShieldingMaterials().names``.
        task: A concrete ``DielectricFunctionQE`` subclass instance for *mat*.

    Returns:
        A ``BackwardMappingModel`` with ``_id='dielectricFunction[material=<mat>]'``.
    """
    return BackwardMappingModel(
        _id=f'dielectricFunction[material={mat}]',
        surrogateFunction=f,
        exactTask=task,
        substituteModels=[],
        documentation=Path(__file__).parent / 'doc.md',
        **build_strategy(_CFG.strategy),
    )


# --------------------------------------------------------------------------- #
# Model instances
# --------------------------------------------------------------------------- #

_TASKS = {spec.name: _make_task_class(spec)() for spec in _MATERIAL_SPECS}

models = {mat: make_dielectric_model(mat, _TASKS[mat])
          for mat in ShieldingMaterials().names}

# Convenience alias — the default material used by the emiShielding chain
m = models['Cu']
