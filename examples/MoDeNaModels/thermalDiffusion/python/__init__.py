"""
@file
Thermal conductivity surrogate model package.

Re-exports the model instance and FireTask class so that FireWorks can
deserialise tasks from MongoDB without listing this package explicitly in
FW_config.yaml — `ADD_USER_PACKAGES: [modena]` is sufficient because modena's
__init__.py auto-imports all packages registered in modena.toml.

@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from .thermalDiffusion import m, ThermalConductivityExact

__all__ = ['m', 'ThermalConductivityExact']
