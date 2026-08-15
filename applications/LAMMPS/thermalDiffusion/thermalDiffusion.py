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
LAMMPS Green-Kubo thermal conductivity surrogate model.

Exact task
----------
Runs a LAMMPS equilibrium MD simulation using the Green-Kubo method to
compute k(T) at a single temperature.  EAM potentials (Foiles/Mishin u3
series) are bundled with the package.

Surrogate
---------
Quadratic polynomial in T, shared across materials:

    k(T) = p0 + p1·T + p2·T²

Each material gets its own fitted coefficients stored in MongoDB.

Supported materials
-------------------
Defined by ``ThermalMaterials`` (an ``IndexSet``).  Currently: Cu, Au, Ag.
Add new metals by adding a ``_MaterialSpec`` entry to ``_MATERIAL_SPECS``.
No new class is needed.

Usage
-----
    from thermalDiffusion import models, ThermalMaterials
    m_cu = models['Cu']
    m_au = models['Au']

    # or the default (Cu) convenience alias:
    from thermalDiffusion import m

Model IDs
---------
``thermalDiffusion[material=Cu]``, ``thermalDiffusion[material=Au]``, …

Requirements
------------
* LAMMPS binary (``lmp``, ``lmp_serial``, or ``lmp_mpi``) on ``PATH``, or
  set ``LAMMPS_EXE`` to the full path.
* EAM potential files are bundled in the package (``potentials/``).
  Override with ``LAMMPS_POTENTIALS`` env var if needed.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   LAMMPS
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger('modena.surrogate')

from fireworks.utilities.fw_utilities import explicit_serialize
from jinja2 import Template

from modena import BackwardMappingModel, CFunction, IndexSet, ModenaFireTask
from modena.utils import find_executable, find_file, load_model_config, build_strategy
import modena.Strategy as Strategy

_CFG = load_model_config(__file__)


# --------------------------------------------------------------------------- #
# Material index set
# --------------------------------------------------------------------------- #

class ThermalMaterials(IndexSet):
    """Registry of metals for which a thermalDiffusion surrogate exists.

    The material list is driven by ``[[materials]]`` in ``config.toml``.
    Add a new metal there — no Python change needed.
    """
    def __init__(self):
        names = [m.name for m in _CFG.materials]
        super().__init__(name='thermalMaterials', names=names)


# --------------------------------------------------------------------------- #
# Material specifications
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _MaterialSpec:
    """All material-specific parameters needed for a LAMMPS EAM simulation."""
    name:           str
    lattice_const:  float   # Å
    mass:           float   # g/mol
    potential_file: str
    lattice_type:   str = 'fcc'
    potential_style: str = 'eam'


_MATERIAL_SPECS: list[_MaterialSpec] = [
    _MaterialSpec(
        m.name,
        m.lattice_const,   # type: ignore[attr-defined]
        m.mass,            # type: ignore[attr-defined]
        m.potential_file,  # type: ignore[attr-defined]
        getattr(m, 'lattice_type',   'fcc'),
        getattr(m, 'potential_style', 'eam'),
    )
    for m in _CFG.materials
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_TEMPLATE_PATH = Path(__file__).parent / 'green_kubo.in.j2'

_POTENTIAL_SEARCH_DIRS = [
    Path(__file__).parent / 'potentials',   # bundled with the package
    Path.home() / '.modena' / 'data' / 'potentials',
    Path.home() / 'lammps' / 'potentials',
    Path('/usr/share/lammps/potentials'),
    Path('/usr/local/share/lammps/potentials'),
    Path('/opt/lammps/potentials'),
]


def _parse_k(result_file: str = 'k_result.txt') -> float:
    """Parse thermal conductivity [W/(m·K)] from the LAMMPS result file."""
    path = Path(result_file)
    if not path.exists():
        raise RuntimeError(
            f"LAMMPS result file '{result_file}' not found.\n"
            "Check log.lammps for errors."
        )
    text = path.read_text().strip()
    try:
        return float(text)
    except ValueError:
        raise RuntimeError(
            f"Could not parse k from '{result_file}': got '{text}'"
        )


# --------------------------------------------------------------------------- #
# Exact task base class
# --------------------------------------------------------------------------- #

class ThermalConductivityLAMMPS(ModenaFireTask):
    """Base class for LAMMPS Green-Kubo thermal conductivity exact tasks.

    Do not subclass manually.  Use ``_make_task_class()`` instead, which
    creates a correctly registered subclass from a ``_MaterialSpec``.
    """

    MATERIAL        = NotImplemented
    LATTICE_TYPE    = 'fcc'
    LATTICE_CONST   = NotImplemented
    MASS            = NotImplemented
    POTENTIAL_STYLE = 'eam'
    POTENTIAL_FILE  = NotImplemented

    # Defaults — overridden per-class by _make_task_class() from config.toml
    NX, NY, NZ      = 5, 5, 5
    DT              = 0.001     # timestep [ps] = 1 fs
    N_EQUIL         = 20_000    # equilibration steps (20 ps)
    N_PROD          = 100_000   # production steps (100 ps)
    SAMPLE_EVERY    = 5
    N_SAMPLES       = 200
    SEED            = 12345

    def task(self, fw_spec):
        T   = self['point']['T']
        lmp = find_executable(
            'lmp',
            env_var='LAMMPS_EXE',
            extra_names=['lmp_serial', 'lmp_mpi', 'lammps'],
        )
        pot = find_file(
            self.POTENTIAL_FILE,
            [Path('.')] + _POTENTIAL_SEARCH_DIRS,
            env_var='LAMMPS_POTENTIALS',
        )

        nfreq = self.SAMPLE_EVERY * self.N_SAMPLES

        lammps_input = Template(_TEMPLATE_PATH.read_text()).render(
            material        = self.MATERIAL,
            lattice_type    = self.LATTICE_TYPE,
            lattice_const   = self.LATTICE_CONST,
            mass            = self.MASS,
            potential_style = self.POTENTIAL_STYLE,
            potential_file  = pot,
            T               = T,
            dt              = self.DT,
            nx              = self.NX,
            ny              = self.NY,
            nz              = self.NZ,
            n_equil         = self.N_EQUIL,
            n_prod          = self.N_PROD,
            sample_every    = self.SAMPLE_EVERY,
            n_samples       = self.N_SAMPLES,
            nfreq           = nfreq,
            seed            = self.SEED,
        )

        Path('lammps.in').write_text(lammps_input)
        _log.info('LAMMPS %s T=%.1f K — starting', self.MATERIAL, T)
        result = subprocess.run(
            [lmp, '-in', 'lammps.in'],
            capture_output=True, text=True,
        )
        _log.debug('LAMMPS stdout:\n%s', result.stdout)
        if result.returncode != 0:
            _log.error('LAMMPS failed (rc=%d):\n%s', result.returncode, result.stderr)
            raise RuntimeError(
                f'LAMMPS exited with code {result.returncode}. '
                'Check log.lammps or re-run with MODENA_LOG_LEVEL=DEBUG.'
            )
        k = _parse_k('k_result.txt')
        _log.info('LAMMPS %s T=%.1f K — k = %.4f W/(m·K)', self.MATERIAL, T, k)
        self['point']['k'] = k


# --------------------------------------------------------------------------- #
# Task-class factory
# --------------------------------------------------------------------------- #

def _make_task_class(spec: _MaterialSpec):
    """Return an ``@explicit_serialize`` task class for the given material.

    The generated class has the same ``__name__`` and ``__module__`` as a
    hand-written subclass would, so the FireWorks ``_fw_name`` is identical
    (e.g. ``'thermalDiffusion::ThermalConductivityCu'``).  Existing MongoDB
    documents remain compatible.

    Simulation parameters are overridden from ``config.toml [simulation]``
    when present.
    """
    sim = _CFG.simulation or {}
    attrs = {
        '__module__':      __name__,
        'MATERIAL':        spec.name,
        'LATTICE_TYPE':    spec.lattice_type,
        'LATTICE_CONST':   spec.lattice_const,
        'MASS':            spec.mass,
        'POTENTIAL_STYLE': spec.potential_style,
        'POTENTIAL_FILE':  spec.potential_file,
    }
    _SIM_MAP = {
        'nx': 'NX', 'ny': 'NY', 'nz': 'NZ',
        'dt': 'DT', 'n_equil': 'N_EQUIL', 'n_prod': 'N_PROD',
        'sample_every': 'SAMPLE_EVERY', 'n_samples': 'N_SAMPLES',
        'seed': 'SEED',
    }
    for toml_key, cls_attr in _SIM_MAP.items():
        if toml_key in sim:
            attrs[cls_attr] = sim[toml_key]

    cls = type(f'ThermalConductivity{spec.name}', (ThermalConductivityLAMMPS,), attrs)
    return explicit_serialize(cls)


# --------------------------------------------------------------------------- #
# Shared surrogate function
# --------------------------------------------------------------------------- #
# Same quadratic polynomial form for all metals.
# Each material gets its own fitted coefficients stored in MongoDB.

f = CFunction(
    Ccode=r'''
#include "modena.h"

void thermalDiffusion_poly
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
# Factory
# --------------------------------------------------------------------------- #

def make_thermal_model(mat: str, task: ThermalConductivityLAMMPS) -> BackwardMappingModel:
    """Create a thermalDiffusion surrogate model for the given material.

    Args:
        mat:  Material symbol, e.g. ``'Cu'``.  Must be in
              ``ThermalMaterials().names``.
        task: A concrete ``ThermalConductivityLAMMPS`` subclass instance.

    Returns:
        A ``BackwardMappingModel`` with ``_id='thermalDiffusion[material=<mat>]'``.
    """
    return BackwardMappingModel(
        _id=f'thermalDiffusion[material={mat}]',
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

models = {mat: make_thermal_model(mat, _TASKS[mat])
          for mat in ThermalMaterials().names}

# Convenience alias — the default material
m = models['Cu']
