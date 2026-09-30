# coolProp

A surrogate for a real-fluid property: the density of CO2, trained against
[CoolProp](http://www.coolprop.org/) instead of a hand-written exact code.

**Surrogate model:** `density[fluid=CO2]` — a third-order bivariate polynomial
`rho(T, P)` over T ∈ [250, 350] K and P ∈ [1e5, 2e6] Pa, fitted to
`CoolProp.PropsSI` at the model's initial points.
**Model package:** [`../MoDeNaModels/coolProp`](../MoDeNaModels/coolProp) —
bounds, fitting strategy and parameters are in its `python/config.toml`.
**Validation:** `workflow` evaluates the trained surrogate on a held-out grid
and reports the maximum and mean relative error against CoolProp.

Needs the `CoolProp` Python package (`pip install CoolProp`).

## How to run

```bash
./buildModels   # compile and install the coolProp package into ./models
./initModels    # sample CoolProp at the initial points and fit the surrogate
./workflow      # validate the surrogate against CoolProp
```

On a database FireWorks has never used, run `modena fw reset --force` first;
it clears the launchpad of the database `MODENA_URI` names.
