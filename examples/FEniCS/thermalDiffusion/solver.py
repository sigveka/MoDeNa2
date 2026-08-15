#!/usr/bin/env python3
'''@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2026 MoDeNa Consortium, All rights reserved.

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
@file
Steady-state nonlinear heat equation solved with FEniCSx and MoDeNa.

PDE
---
Solve the nonlinear heat equation on the unit square Ω = [0,1]²:

    -∇·( k(T) ∇T ) = 0    in Ω

subject to

    T = T_LEFT   on x = 0   (hot/cold wall)
    T = T_RIGHT  on x = 1   (opposite wall)
    k ∂T/∂n = 0             on y = 0 and y = 1  (insulated, natural BC)

Method
------
Picard (fixed-point) iteration:

    1.  Initialise T⁰ with a linear profile T⁰ = T_LEFT + (T_RIGHT - T_LEFT) x.
    2.  Evaluate k(Tⁿ) at every degree of freedom via the MoDeNa surrogate.
    3.  Solve the linearised problem  -∇·( k(Tⁿ) ∇T^{n+1} ) = 0  for T^{n+1}.
    4.  Compute ‖T^{n+1} - Tⁿ‖₂ and stop if below TOL, else set n ← n+1.

Results
-------
temperature.xdmf — temperature field T and conductivity field k, readable
with ParaView or pyvista.

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
@ingroup   FEniCS
"""

import sys
import numpy as np
import modena
from dolfinx import mesh, fem, io
from dolfinx.mesh import create_unit_square
from mpi4py import MPI
from petsc4py import PETSc
import ufl

# ── Parameters ──────────────────────────────────────────────────────────────────
T_LEFT  = 300.0   # K  — Dirichlet BC on x = 0
T_RIGHT = 1200.0  # K  — Dirichlet BC on x = 1
N_CELLS = 32      # mesh cells per edge
MAX_ITER = 50     # Picard iteration limit
TOL     = 1e-6    # convergence: L2 norm of (T_new - T_old)

# ── Mesh and function space ──────────────────────────────────────────────────────
msh = create_unit_square(MPI.COMM_WORLD, N_CELLS, N_CELLS)
V   = fem.functionspace(msh, ("Lagrange", 1))

# ── MoDeNa surrogate ────────────────────────────────────────────────────────────
# Load the pre-trained 'thermalDiffusion' surrogate from MongoDB.
# Run `./initModels` once before this script to train the surrogate.
surrogate = modena.load('thermalDiffusion')

# ── Conductivity field (updated at each Picard iteration) ───────────────────────
k_h = fem.Function(V)
k_h.name = "k"


def _update_k(T_h: fem.Function) -> None:
    """Evaluate k(T) at every DoF via the MoDeNa surrogate."""
    T_arr = T_h.x.array
    k_arr = np.empty_like(T_arr)
    for i, T_val in enumerate(T_arr):
        # MoDeNa Python API: model({'input': value}) → {'output': value}
        # The surrogate calls exit(200) if T is outside its trained bounds;
        # FireWorks catches that, triggers retraining, and restarts this script.
        k_arr[i] = surrogate({'T': float(T_val)})['k']
    k_h.x.array[:] = k_arr


# ── Dirichlet boundary conditions ───────────────────────────────────────────────
left_dofs  = fem.locate_dofs_geometrical(V, lambda x: np.isclose(x[0], 0.0))
right_dofs = fem.locate_dofs_geometrical(V, lambda x: np.isclose(x[0], 1.0))
bcs = [
    fem.dirichletbc(PETSc.ScalarType(T_LEFT),  left_dofs,  V),
    fem.dirichletbc(PETSc.ScalarType(T_RIGHT), right_dofs, V),
]

# ── Initial guess: linear temperature profile ────────────────────────────────────
T_old = fem.Function(V)
T_old.interpolate(lambda x: T_LEFT + (T_RIGHT - T_LEFT) * x[0])

# ── Trial and test functions ─────────────────────────────────────────────────────
u = ufl.TrialFunction(V)
v = ufl.TestFunction(V)

# ── Picard iteration ─────────────────────────────────────────────────────────────
print("Starting Picard iteration")
print(f"  T_LEFT={T_LEFT} K,  T_RIGHT={T_RIGHT} K,  mesh={N_CELLS}×{N_CELLS}")
print(f"  {'Iter':>5}   {'||ΔT||₂':>12}")
print("  " + "-" * 22)

T_new     = fem.Function(V)
T_new.name = "T"
converged = False

for it in range(1, MAX_ITER + 1):

    # Step 1: update conductivity field from previous iterate
    _update_k(T_old)

    # Step 2: assemble and solve linearised heat equation
    a = ufl.inner(k_h * ufl.grad(u), ufl.grad(v)) * ufl.dx
    L = fem.Constant(msh, PETSc.ScalarType(0.0)) * v * ufl.dx

    problem = fem.petsc.LinearProblem(
        a, L, bcs=bcs,
        petsc_options={"ksp_type": "cg", "pc_type": "hypre"},
    )
    T_new = problem.solve()
    T_new.name = "T"

    # Step 3: convergence check
    diff = T_new.x.array - T_old.x.array
    err  = float(np.sqrt(np.dot(diff, diff)))
    print(f"  {it:>5}   {err:>12.4e}")

    T_old.x.array[:] = T_new.x.array

    if err < TOL:
        converged = True
        break

if not converged:
    print(f"  WARNING: did not converge in {MAX_ITER} iterations")

# ── Write results ────────────────────────────────────────────────────────────────
_update_k(T_new)   # write the converged k field

with io.XDMFFile(MPI.COMM_WORLD, "temperature.xdmf", "w") as xf:
    xf.write_mesh(msh)
    xf.write_function(T_new)
    xf.write_function(k_h)

print(f"\nResults written to temperature.xdmf")
print(f"  T ∈ [{T_new.x.array.min():.1f}, {T_new.x.array.max():.1f}] K")
print(f"  k ∈ [{k_h.x.array.min():.4f}, {k_h.x.array.max():.4f}] W/(m·K)")

sys.exit(0)
