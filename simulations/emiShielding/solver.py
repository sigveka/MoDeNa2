#!/usr/bin/env python3
"""
Evaluate the surfaceImpedance[material=Cu] surrogate over a frequency sweep.

Output: Zs_spectrum.csv
"""

import sys
import numpy as np
import modena

THICKNESS_NM = 100.0
OMEGA_EV_MIN = 0.5
OMEGA_EV_MAX = 6.0
N_FREQS      = 40

surrogate = modena.load('surfaceImpedance[material=Cu]')

omega_eV_arr = np.linspace(OMEGA_EV_MIN, OMEGA_EV_MAX, N_FREQS)
Zs_real_arr  = np.zeros(N_FREQS)
Zs_imag_arr  = np.zeros(N_FREQS)

print(f"Surface impedance — Cu slab, d = {THICKNESS_NM} nm")
print(f"Frequency sweep: {OMEGA_EV_MIN}–{OMEGA_EV_MAX} eV, {N_FREQS} points")
print(f"{'ω [eV]':>8}  {'Re(Zs) [Ω]':>12}  {'Im(Zs) [Ω]':>12}")
print("─" * 38)

for i, omega_eV in enumerate(omega_eV_arr):
    result = surrogate({'omega_eV': omega_eV, 'd_nm': THICKNESS_NM})
    Zs_real_arr[i] = result['Zs_real']
    Zs_imag_arr[i] = result['Zs_imag']
    print(f"{omega_eV:>8.3f}  {Zs_real_arr[i]:>12.4f}  {Zs_imag_arr[i]:>12.4f}")

output_file = 'Zs_spectrum.csv'
np.savetxt(
    output_file,
    np.column_stack([omega_eV_arr, Zs_real_arr, Zs_imag_arr]),
    header='omega_eV [eV], Zs_real [Ohm], Zs_imag [Ohm]',
    delimiter=',',
    comments='',
)
print(f"\nResults written to {output_file}")

sys.exit(0)
