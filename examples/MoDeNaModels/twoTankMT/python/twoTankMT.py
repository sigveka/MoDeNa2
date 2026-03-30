"""
@file      FireTask wrapper for the multi-threaded two-tank simulation.
@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from modena.Strategy import BackwardMappingScriptTask


class TwoTankMTModel(BackwardMappingScriptTask):
    """Macroscopic two-tank multi-threaded simulation task."""

    _fw_name = '{{twoTankMT.TwoTankMTModel}}'
    optional_params = None

    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            super().__init__(*args, **kwargs)
            return
        # Binary compiled from src/twoTanksMT.c
        super().__init__(script=self.find_binary('twoTanksMT'), **kwargs)


m = TwoTankMTModel()
