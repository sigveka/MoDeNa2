# dielectricFunction — Quantum ESPRESSO optical dielectric function

Provides the MoDeNa surrogate model `dielectricFunction[material=Cu]`.

The exact task runs a Quantum ESPRESSO SCF + NSCF calculation followed by
`epsilon.x` to compute the optical dielectric function
ε(ω) = ε₁(ω) + i ε₂(ω) at a single photon energy using the
independent-particle approximation (IPA).  The surrogate is a pair of
cubic polynomials in ω fitted by the MoDeNa backward-mapping loop.

This model is used as the base of the multi-scale EMI shielding chain:

```
dielectricFunction  →  emiShielding (Meep)  →  structuralSE (NGSolve)
```

## Prerequisites

- **Quantum ESPRESSO** — `pw.x` and `epsilon.x` on `PATH`, or set
  `QE_BIN_DIR` to the directory containing them.
  <https://www.quantum-espresso.org>
- **Pseudopotential** — `Cu.upf` (norm-conserving PBE) in
  `~/.modena/data/pseudo/`, or set `QE_PSEUDO_DIR`.
  Pseudopotentials are available from the
  [QE pseudo library](https://www.quantum-espresso.org/pseudopotentials).

## Installation

```bash
./install
```

## Usage

```bash
./initModels     # train the surrogate
```

## Citation

If you use Quantum ESPRESSO, please cite:

> P. Giannozzi et al., *QUANTUM ESPRESSO: a modular and open-source
> software project for quantum simulations of materials*,
> J. Phys.: Condens. Matter **21**, 395502 (2009).
> <https://doi.org/10.1088/0953-8984/21/39/395502>

> P. Giannozzi et al., *Advanced capabilities for materials modelling
> with Quantum ESPRESSO*, J. Phys.: Condens. Matter **29**, 465901 (2017).
> <https://doi.org/10.1088/1361-648X/aa8f79>
