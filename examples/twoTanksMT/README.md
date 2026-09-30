# twoTanksMT

Same two-tank problem as `twoTanks`, but the macroscopic program runs
**several simulations in parallel threads** that share one model.

**Macroscopic solver:** `twoTanksMT` (C, POSIX threads) — a parametric sweep:
four threads each discharge the tanks from a different initial pressure,
all calling the same `modena_model_t`.
**Surrogate model:** `flowRate` (backward mapping)
**Model package:** [`../MoDeNaModels/twoTankMT`](../MoDeNaModels/twoTankMT)

What this example shows is **thread safety**.  A `modena_model_t` is read-only
once `modena_model_new()` returns, so threads may share it; each thread
allocates its own `modena_inputs_t` and `modena_outputs_t`, and reads its own
error state.  An out-of-bounds call from any thread is handled as in the
single-threaded case.  The same pattern is regression-tested by
`src/tests/interface-tests/test_thread_safety.C`.

See [`../twoTanks/README.md`](../twoTanks/README.md) for the model-definition
philosophy and how `modena.toml` connects the surrogate to the solver task.

## How to run

```bash
# 1. Compile and install the model packages
./buildModels

# 2. Initialise the surrogate in the database
./initModels

# 3. Run the simulation
./workflow
```
