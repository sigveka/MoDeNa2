# thermalDiffusion — LAMMPS Green-Kubo thermal conductivity

Provides the MoDeNa surrogate model `thermalDiffusion[material=Cu]`.

The exact task runs an equilibrium molecular dynamics simulation using the
Green-Kubo method: the heat-current autocorrelation function is integrated
over time to yield the thermal conductivity k(T) at a single temperature.
Copper is modelled with the Mishin EAM potential.  The surrogate is a
quadratic polynomial in T fitted by the MoDeNa backward-mapping loop.

## Prerequisites

- **LAMMPS** — `lmp` (or `lmp_serial`, `lmp_mpi`) on `PATH`, or set
  `LAMMPS_EXE` to the full path.
  <https://www.lammps.org>
- **EAM potential** — `Cu_u3.eam` (distributed with LAMMPS) in
  `~/.modena/data/potentials/`, or set `LAMMPS_POTENTIALS`.

## Installation

```bash
./install
```

## Usage

```bash
./initModels     # train the surrogate
python solver.py
```

## Citation

If you use LAMMPS, please cite:

> A.P. Thompson et al., *LAMMPS — a flexible simulation tool for
> particle-based materials modeling*, Comput. Phys. Commun. **271**, 108171
> (2022). <https://doi.org/10.1016/j.cpc.2021.108171>
