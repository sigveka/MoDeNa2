#!/usr/bin/env python3
"""
@file      Pure-Python macroscopic simulation for the twoTanks example.
@details   Simulates the discharge of air between two tanks through a nozzle.
           The flow rate is evaluated via the MoDeNa surrogate model. If the
           surrogate is queried outside its trained region, the underlying C
           library calls exit(200), which FireWorks intercepts to trigger
           parameter fitting and a restart.
@author    MoDeNa Project
@copyright 2014-2016, MoDeNa Project. GNU Public License.
"""

import sys
import modena

# ── Physical constants and initial conditions ──────────────────────────────────
D      = 0.01    # nozzle diameter [m]
R      = 287.1   # specific gas constant for air [J/(kg K)]
T_gas  = 300.0   # temperature [K]
V0     = 0.1     # volume of tank 0 [m³]
V1     = 1.0     # volume of tank 1 [m³]
deltat = 1e-3    # time step [s]
tend   = 5.5     # end time [s]

p0 = 3e5         # initial pressure in tank 0 [Pa]
p1 = 1e4         # initial pressure in tank 1 [Pa]

m0   = p0 * V0 / R / T_gas
m1   = p1 * V1 / R / T_gas
rho0 = m0 / V0
rho1 = m1 / V1
t    = 0.0

# ── Load surrogate model from database ────────────────────────────────────────
print('Starting simulation')
model = modena.load('flowRate')

# ── Time-step loop ────────────────────────────────────────────────────────────
while t + deltat < tend + 1e-10:

    t += deltat

    # Set inputs depending on flow direction
    if p0 > p1:
        inputs = {'D': D, 'rho0': rho0, 'p0': p0, 'p1Byp0': p1 / p0}
    else:
        inputs = {'D': D, 'rho0': rho1, 'p0': p1, 'p1Byp0': p0 / p1}

    # Evaluate surrogate — exits with code 200 if out of bounds,
    # which FireWorks intercepts to trigger retraining and restart.
    mdot = model(inputs)['flowRate']

    # Update mass and state
    if p0 > p1:
        m0 -= mdot * deltat
        m1 += mdot * deltat
    else:
        m0 += mdot * deltat
        m1 -= mdot * deltat

    rho0 = m0 / V0;  p0 = rho0 * R * T_gas
    rho1 = m1 / V1;  p1 = rho1 * R * T_gas

    print(f't={t:.3f}  p0={p0:.1f}  p1={p1:.1f}')

print('Success - We are done')
sys.exit(0)
