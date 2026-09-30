# coolPropMixtureTP

The mixture example of [`../coolPropMixture`](../coolPropMixture/README.md),
extended with temperature and pressure: the **density** of an N2/O2/Ar
mixture as a function of (T, p, x_N2, x_O2), trained against
[CoolProp](http://www.coolprop.org/).

**Surrogate model:** `mixtureDensity[fluid=N2O2Ar]` — a second-order
polynomial over T ∈ [250, 350] K, p ∈ [1e5, 2e6] Pa, `x_N2` ∈ [0.70, 0.85]
and `x_O2` ∈ [0.14, 0.25], with `x_Ar = 1 - x_N2 - x_O2` computed in the
surrogate's C code.
**Model package:** [`../MoDeNaModels/coolPropMixtureTP`](../MoDeNaModels/coolPropMixtureTP).

Training uses `ExpandedCASTROSampling`: T and p are sampled by ordinary Latin
hypercube sampling, the composition group by CASTRO, and the two are paired
and thinned by greedy maximin selection in the joint four-dimensional space —
unconstrained and constrained inputs in one model.

Needs the `CoolProp` Python package (`pip install CoolProp`).

## How to run

```bash
./buildModels   # compile and install the coolPropMixtureTP package into ./models
./initModels    # sample (T, p) with LHS and compositions with CASTRO, fit
./workflow      # validate against CoolProp at held-out points
```

On a database FireWorks has never used, run `modena fw reset --force` first;
it clears the launchpad of the database `MODENA_URI` names.
