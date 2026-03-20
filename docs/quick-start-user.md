# Quick-Start Guide — Running a MoDeNa Simulation

This guide walks you through running the `twoTanks` example from scratch.
No prior knowledge of surrogate modelling is required.

---

## What MoDeNa does

MoDeNa replaces expensive microscopic simulations (e.g. CFD) inside a
macroscopic solver with fast surrogate models.  The first time the macroscopic
solver asks for a result that the surrogate has not seen before, MoDeNa
automatically runs the expensive simulation to collect training data, refits
the surrogate, and restarts the macroscopic solver.  This loop repeats until
the surrogate is accurate enough — after which subsequent runs use only the
fast surrogate.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| MongoDB ≥ 4.4 | Must be running before any MoDeNa command |
| Python ≥ 3.10 | With `modena`, `fireworks`, `mongoengine` installed |
| CMake ≥ 3.0 | Required to build model packages |
| A C compiler | `gcc` or `clang` |

Start MongoDB (if not already running as a service):

```bash
mongod --dbpath ~/.mongodb/data --fork --logpath ~/.mongodb/mongod.log
```

---

## Environment

The following variables must be set in every shell that runs MoDeNa commands.
Add them to your shell profile (`~/.bashrc` or `~/.zshrc`) to avoid repeating
this step.

```bash
# Where Python finds the modena package and model packages
export PYTHONPATH="${PYTHONPATH}:${HOME}/lib/python3.10/site-packages"

# Where the runtime linker finds libmodena.so
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
```

If your MongoDB instance is not on `localhost:27017/test`, set:

```bash
export MODENA_URI=mongodb://myserver:27017/modena
```

---

## Step 1 — Install model packages

Each example ships with a `buildModels` script that compiles and installs the
model packages for that example.

```bash
cd examples/twoTanks
./buildModels
```

This installs the `flowRate` and `twoTank` packages into `./models/` and
registers them for this project via `modena.toml`.

Verify the installation:

```bash
python3 -c "import flowRate; print('OK')"
```

---

## Step 2 — Initialise models in the database

Before a simulation can run, each surrogate model must be registered in
MongoDB and provided with a small set of initial training points.

```bash
./initModels
```

This script:

1. Imports all model definitions (e.g. `flowRate.m`)
2. Runs the exact (expensive) simulation at a handful of pre-defined points
3. Fits the surrogate for the first time
4. Stores the model and its initial parameters in MongoDB

You only need to run `initModels` once per fresh database.  Re-running it
resets the database and discards any previously fitted parameters.

---

## Step 3 — Run the simulation

```bash
./workflow
```

The workflow launches the macroscopic solver (`twoTanksMacroscopicProblem`)
and monitors its return code.  Typical output looks like:

```
INFO Launching rocket
--- Loaded model flowRate
Starting simulation
...
Out of bounds for model flowRate — requesting new samples
INFO Task completed: {{twoTank.TwoTankModel}}    DEFUSED
INFO Launching new FireWork (parameter fitting for flowRate)
...
Fitting complete
INFO Task completed: {{modena.Strategy.ParameterFitting}}
INFO Launching rocket
--- Loaded model flowRate
Starting simulation
...
Success - We are done
INFO Task completed: {{twoTank.TwoTankModel}}
```

The solver restarts automatically after each retraining cycle.  The number of
restarts depends on how many times the simulation moves outside the region the
surrogate was trained on.

---

## Understanding the training loop

| Return code | Meaning | What happens next |
|-------------|---------|-------------------|
| 0 | Success | Workflow completes normally |
| 100 | Surrogate retrained (out of bounds) | Macroscopic solver decrements time and retries the current step |
| 200 | Exit and restart | FireWorks launches parameter fitting, then restarts the solver |
| 201 | Clean exit — no restart | Workflow ends |

---

## Step 4 — Inspect the results

After a successful run, MoDeNa writes a `modena.lock` file in the working
directory:

```toml
[meta]
modena_version = "1.0"
generated      = "2026-03-15T10:05:33"

[packages]
flowRate = "1.0"

[models.flowRate]
surrogate_function = "two_tank_flowRate"
n_samples          = 8
parameters         = [1.234, 0.567]
last_fitted        = "2026-03-15T10:04:50"
```

This file records exactly which model versions and fitted parameters were
active during the run.  Commit it to version control to make runs reproducible:

```bash
git add modena.lock
git commit -m "pin surrogate parameters after calibration run"
```

To restore this state on another machine:

```bash
python3 -m modena restore
```

---

## Step 5 — Rerun without retraining

Run `./workflow` a second time.  Because the surrogate already covers the
input space explored by the simulation, no retraining occurs:

```
Starting simulation
...
Success - We are done
```

---

## Troubleshooting

**`ImportError: No module named 'flowRate'`**
Run `./buildModels` and verify `PYTHONPATH` includes the `models/` site-packages
directory.

**`ServerSelectionTimeoutError`**
MongoDB is not running or `MODENA_URI` points to the wrong host.  Check
`mongod` is up and the URI is correct.

**Simulation restarts many times without converging**
Increase `maxIterations` in the `parameterFittingStrategy`, or check that the
exact simulation (`flowRateExact`) is producing sensible output values.

**`cmake` not found during surrogate compilation**
Install CMake and ensure it is on `PATH`.  The compiled libraries are stored
in `~/.modena/surrogate_functions/` and only need to be built once.
