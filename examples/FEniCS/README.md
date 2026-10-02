# FEniCS

MoDeNa driving a finite-element code: a [FEniCSx](https://fenicsproject.org/)
solver that evaluates a surrogate at every degree of freedom.

## thermalDiffusion

A steady nonlinear heat equation, `-∇·(k(T) ∇T) = 0` on the unit square with
fixed temperatures on the left and right walls and insulated top and bottom,
solved by Picard iteration.  The temperature-dependent conductivity `k(T)`
is the MoDeNa surrogate: each iteration evaluates it at every degree of
freedom.

**Surrogate model:** `thermalDiffusion` — a quadratic polynomial `k(T)` over
T ∈ [273, 1500] K, fitted by the backward-mapping loop to an "exact" power
law `k = k_ref (T / T_ref)^n` that stands in for an expensive property
calculation.
**Model package:** [`../MoDeNaModels/thermalDiffusion`](../MoDeNaModels/thermalDiffusion)
**Output:** `temperature.xdmf` — the temperature and conductivity fields,
readable with ParaView or pyvista.

Needs FEniCSx: the `dolfinx`, `mpi4py` and `petsc4py` Python packages (for
example `fenics-dolfinx` from conda-forge).

### How to run

```bash
cd thermalDiffusion

# 1. Install the model package into ./models (modena.toml looks there)
modena install --prefix ./models ../../MoDeNaModels/thermalDiffusion/python

# 2. Fit the conductivity surrogate
./initModels

# 3. Solve
python3 solver.py
```

On a database FireWorks has never used, run `modena fw reset --force` before
step 2; it clears the launchpad of the database `MODENA_URI` names.
