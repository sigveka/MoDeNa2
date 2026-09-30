# coolPropMixture

A surrogate whose inputs are **mole fractions**: the viscosity of an N2/O2/Ar
mixture at fixed T = 300 K and P = 1e5 Pa, trained against
[CoolProp](http://www.coolprop.org/).

**Surrogate model:** `mixtureViscosity[fluid=N2O2Ar]` — a second-order
polynomial in the free fractions `x_N2` ∈ [0.70, 0.85] and `x_O2` ∈
[0.14, 0.25]; the surrogate's C code computes `x_Ar = 1 - x_N2 - x_O2`.
**Model package:** [`../MoDeNaModels/coolPropMixture`](../MoDeNaModels/coolPropMixture).

What this example shows is **constrained sampling**.  The fractions must sum
to one, so independent sampling would waste most points outside the feasible
simplex — and each one is a full exact simulation.  The model therefore
declares `CASTROSampling` (sequential conditional Latin hypercube sampling
with greedy maximin selection), which covers the simplex directly.  See
[`../coolPropMixtureTP`](../coolPropMixtureTP/README.md) for the same idea
combined with temperature and pressure inputs.

Needs the `CoolProp` Python package (`pip install CoolProp`).

## How to run

```bash
./buildModels   # compile and install the coolPropMixture package into ./models
./initModels    # sample compositions with CASTRO, fit the surrogate
./workflow      # validate against CoolProp on a held-out composition grid
```

On a database FireWorks has never used, run `modena fw reset --force` first;
it clears the launchpad of the database `MODENA_URI` names.
