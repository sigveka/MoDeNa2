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
        if args and isinstance(args[0], dict):
            super().__init__(*args, **kwargs)
            return
        super().__init__(script=self.find_binary('twoTanksSim.py'))


m = TwoTankPythonModel()
