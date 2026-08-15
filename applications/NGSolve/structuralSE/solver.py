#!/usr/bin/env python3
"""
@file
Structural shielding effectiveness frequency sweep.

This script is a convenience wrapper around ``modena sweep``.  The equivalent
command is::

    modena sweep 'structuralSE[geometry=enclosure]' \\
        --param omega_eV=0.5:6.0:40 --out SE_3d_spectrum.csv

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   NGSolve
"""

import subprocess
import sys

sys.exit(subprocess.run([
    sys.executable, '-m', 'modena', 'sweep',
    'structuralSE[geometry=enclosure]',
    '--param', 'omega_eV=0.5:6.0:40',
    '--out',   'SE_3d_spectrum.csv',
]).returncode)
