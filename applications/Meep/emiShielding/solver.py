#!/usr/bin/env python3
"""
@file
Surface impedance frequency sweep.

This script is a convenience wrapper around ``modena sweep``.  The equivalent
command is::

    modena sweep 'surfaceImpedance[material=Cu]' \\
        --param omega_eV=0.5:6.0:40 --fix d_nm=100 --out Zs_spectrum.csv

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   Meep
"""

import subprocess
import sys

sys.exit(subprocess.run([
    sys.executable, '-m', 'modena', 'sweep',
    'surfaceImpedance[material=Cu]',
    '--param', 'omega_eV=0.5:6.0:40',
    '--fix',   'd_nm=100',
    '--out',   'Zs_spectrum.csv',
]).returncode)
