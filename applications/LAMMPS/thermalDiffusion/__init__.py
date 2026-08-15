"""
@file
LAMMPS thermal conductivity surrogate package.

Re-exports model instances and FireTask classes so FireWorks can deserialise
tasks from MongoDB.  ``ADD_USER_PACKAGES: [modena]`` in FW_config.yaml is
sufficient when this package is installed into a prefix registered in modena.toml.

@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from .thermalDiffusion import (
    m, models, ThermalMaterials,
    ThermalConductivityLAMMPS,
    ThermalConductivityCu, ThermalConductivityAu, ThermalConductivityAg,
    make_thermal_model,
)

__all__ = [
    'm', 'models', 'ThermalMaterials',
    'ThermalConductivityLAMMPS',
    'ThermalConductivityCu', 'ThermalConductivityAu', 'ThermalConductivityAg',
    'make_thermal_model',
]
