# emiShielding — Meep 1D surface impedance

Provides the MoDeNa surrogate model `surfaceImpedance[material=Cu]`.

The exact task runs a pair of 1D Meep FDTD simulations (reference + slab)
to verify field decay, then computes the Leontovich surface impedance
Z_s(ω, d) analytically from the complex permittivity ε(ω) supplied by the
`dielectricFunction[material=Cu]` surrogate.  The surrogate is a bilinear
polynomial in ω and d fitted by the MoDeNa backward-mapping loop.

Z_s is the key intermediate quantity linking the atomic-scale dielectric
response (QE) to the macroscopic 3D electromagnetic problem (NGSolve): it
serves as a Leontovich impedance boundary condition on metal surfaces,
eliminating the need to resolve the skin depth in the 3D mesh.

## Prerequisites

- **dielectricFunction** package installed and registered with MoDeNa.
- **Meep** *(optional)* — if installed, a 1D FDTD simulation is run at each
  training point to cross-check the analytical result.  Without Meep the
  exact task falls back to the analytical formula only.

  On Debian/Ubuntu:
  ```bash
  apt install python3-meep
  ```
  <https://meep.readthedocs.io>

## Installation

Installs the chain (dielectricFunction → emiShielding) to `~/.modena/models`
and registers the path automatically:

```bash
./install
```

## Usage

```bash
./initModels     # train dielectricFunction, then surfaceImpedance
python solver.py # evaluate Z_s over a frequency sweep → Zs_spectrum.csv
```

## Citation

If you use Meep, please cite:

> A.F. Oskooi et al., *Meep: A flexible free-software package for
> electromagnetic simulations by the FDTD method*,
> Comput. Phys. Commun. **181**, 687–702 (2010).
> <https://doi.org/10.1016/j.cpc.2009.11.008>
