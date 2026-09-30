# multicomponentDiffusion

Binary gas-phase diffusion coefficients from the correlation of Fuller et al.,
defined once for a whole family of species pairs by an **index set**.

**Model:** `fullerEtAlDiffusion[A=…,B=…]` — a **forward-mapping** model: the
correlation is evaluated in closed form with parameters (molar masses and
diffusion volumes) read from its `config.toml`, so nothing is sampled or
fitted and there is no out-of-bounds retraining.
**Index set:** `species = {H2O, N2, SO2}`; the indices `A` and `B` of the
surrogate function both range over it.
**Macroscopic program:** `fullerEtAlDiffusionTest` (C++), which looks species
up by name in the index set and evaluates `D` at a given `p` and `T`.

The model package lives in
[`../MoDeNaModels/fullerEtAlDiffusion`](../MoDeNaModels/fullerEtAlDiffusion).
What this example shows is the index-set mechanics — one `CFunction` with
`indices={'A': species, 'B': species}`, instantiated per species pair — rather
than backward mapping; see [`../twoTanks`](../twoTanks/README.md) for that.

The function declares its output and parameters with index-set notation:
`D[A]`, and `W[A]`, `V[A]`, `W[B]`, `V[B]` (molar mass and diffusion volume of
each species).  The instance `fullerEtAlDiffusion[A=H2O,B=N2]` stores its
output as `D[H2O]` — the name a model built on top of it, such as a
multicomponent mixture rule, would take as an input.  In the C code the
indexed names are bound without brackets, as `WA`, `VA`, `WB` and `VB`.

## How to run

MoDeNa must be installed and a MongoDB reachable at `MODENA_URI`
(`modena doctor` checks both).

On a database FireWorks has never used, initialise its launchpad first, or
step 2 stops with `Could not get next FW id`.  This **clears** the launchpad
of the database `MODENA_URI` names, so skip it on one holding runs you want
to keep:

```bash
modena fw reset --force
```

```bash
# 1. Compile and install the fullerEtAlDiffusion package into ./models
./buildModels

# 2. Register the model for the H2O/N2 pair in the database
./initModels

# 3. Run fullerEtAlDiffusionTest through FireWorks
./workflow
```

`make distclean` removes the build directory, the installed models and the
compiled surrogate functions.
