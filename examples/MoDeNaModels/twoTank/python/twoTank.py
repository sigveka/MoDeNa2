'''@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2016 MoDeNa Consortium, All rights reserved.

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
@file      A simple workflow starting the macroscopic code
@author    Henrik Rusche
@copyright 2014-2016, MoDeNa Project. GNU Public License.
@ingroup   twoTank
"""

import logging

from modena.Strategy import BackwardMappingScriptTask

# Source code in src/twoTanksMacroscopicProblem.C

class TwoTankModel(BackwardMappingScriptTask):
    """Macroscopic two-tank simulation task.

    Demonstrates passing simulation parameters from ``modena.toml`` through
    to the compiled C binary via ``[simulate.kwargs]``:

    .. code-block:: toml

        [simulate]
        target = "twoTank.TwoTankModel"

        [simulate.kwargs]
        end_time = 10.0

    Args:
        end_time: Simulation end time in seconds (default: 5.5).  Forwarded
            as ``--end-time`` to the binary.
        **kwargs: Any additional keyword arguments are stored in the FireWorks
            task dict and passed through to the parent class.
    """
    _fw_name = '{{twoTank.TwoTankModel}}'
    optional_params = None  # allow arbitrary kwargs through to the task dict

    def __init__(self, end_time=None, **kwargs):
        cmd = [self.find_binary('twoTanksMacroscopicProblem')]

        if end_time is not None:
            cmd += ['--end-time', str(end_time)]

        # Pass --verbose when modena is running at DEBUG level or below so the
        # binary prints the model's input/output/parameter names.
        if logging.getLogger('modena').isEnabledFor(logging.DEBUG):
            cmd.append('--verbose')

        super().__init__(script=cmd, **kwargs)


m = TwoTankModel()

