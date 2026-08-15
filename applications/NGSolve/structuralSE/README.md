# structuralSE — NGSolve 3D shielding effectiveness

Provides the MoDeNa surrogate model `structuralSE[geometry=enclosure]`.

The exact task runs a full-wave 3D frequency-domain FEM using NGSolve and
Netgen to compute the shielding effectiveness SE(ω) of a metallic enclosure
with an aperture.  Metal walls are modelled with Leontovich impedance
boundary conditions using Z_s(ω, d) from the `surfaceImpedance[material=Cu]`
surrogate — the skin depth is never resolved in the mesh.  The surrogate is
a quadratic polynomial in ω fitted by the MoDeNa backward-mapping loop.

This is the top level of the three-level multi-scale chain:

```
dielectricFunction (QE)  →  emiShielding (Meep 1D)  →  structuralSE (NGSolve 3D)
```

## Prerequisites

- **NGSolve** and **Netgen**:
  ```bash
  pip install ngsolve netgen-mesher
  ```
  <https://ngsolve.org>

## Installation

Installs the full chain (dielectricFunction → emiShielding → structuralSE)
to `~/.modena/models` and registers the path so that `import modena` makes
all packages importable automatically:

```bash
./install
```

## Usage

```bash
./initModels     # train all three levels in dependency order
python solver.py # evaluate SE over a frequency sweep → SE_3d_spectrum.csv
```

## Citation

If you use NGSolve/Netgen, please cite:

> J. Schöberl, *NETGEN: An advancing front 2D/3D-mesh generator based on
> abstract rules*, Comput. Vis. Sci. **1**, 41–52 (1997).
> <https://doi.org/10.1007/s007910050004>
