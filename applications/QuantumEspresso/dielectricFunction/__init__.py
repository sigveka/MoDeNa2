"""
@file
Optical dielectric function surrogate package — Quantum ESPRESSO exact task.

@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from .dielectricFunction import (
    m, models, ShieldingMaterials,
    DielectricFunctionQE,
    DielectricFunctionCu, DielectricFunctionAu, DielectricFunctionAg,
    make_dielectric_model,
)

__all__ = [
    'm', 'models', 'ShieldingMaterials',
    'DielectricFunctionQE',
    'DielectricFunctionCu', 'DielectricFunctionAu', 'DielectricFunctionAg',
    'make_dielectric_model',
]
