"""
@file      Macroscopic model definition for the pure-Python twoTanks example.
@details   Wraps the Python simulation script as a BackwardMappingScriptTask
           so FireWorks can manage the backward-mapping loop.
@author    MoDeNa Project
@copyright 2014-2016, MoDeNa Project. GNU Public License.
"""

import os
from modena.Strategy import BackwardMappingScriptTask


class TwoTankPythonModel(BackwardMappingScriptTask):
    """FireTask that runs the Python macroscopic simulation as a subprocess."""

    _fw_name = '{{twoTankPython.TwoTankPythonModel}}'

    def __init__(self, *args, **kwargs):
        super().__init__(
            script=os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'bin', 'twoTanksSim.py'
            )
        )


m = TwoTankPythonModel()
