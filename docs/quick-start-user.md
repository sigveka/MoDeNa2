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

**For a default `$HOME` install, running Python code needs no setup at all.**
CMake puts the `modena` package in your user site-packages directory, which
Python adds to `sys.path` by itself, and `libmodena.so` carries
`RUNPATH=$ORIGIN` so it finds its sibling libraries unaided.  Check with:

```bash
python3 -c "import modena; print(modena.__file__)"
```

You do need the environment script in three cases: you installed to a custom
prefix, you are working inside a virtualenv, or you are building a C, C++,
Fortran, Julia or MATLAB application that links against `libmodena`.

```bash
source ~/share/modena/modena-env.sh
```

CMake generates that script at install time from the paths this build actually
used, so it cannot drift from the installed tree the way a hand-written
`export` does.  It sets `LD_LIBRARY_PATH`, `PYTHONPATH`, `PATH` and
`MODENA_MATLAB_DIR`, skips any directory that does not exist, and is safe to
source repeatedly — so it can go straight into `~/.bashrc`.  Replace `~` with
your prefix if you did not install to `$HOME`.

> **Virtualenvs.**  Python drops user site-packages from `sys.path` inside a
> virtualenv, so `import modena` fails there even though the package is
> installed.  Sourcing the script sets `PYTHONPATH` explicitly and fixes that
> for ordinary Python use.  It does **not** make a venv work for C, C++ or
> Fortran applications: the interpreter embedded in `libmodena` ignores
> `$VIRTUAL_ENV` entirely, so dependencies installed inside a venv stay
> invisible to it — see
> [core-developer-guide.md](core-developer-guide.md#why-not-a-venv).
> Note also that `pip install --user` is not an alternative on Ubuntu 24.04
> and other PEP 668 distributions, which is why the package is installed by
> CMake rather than by pip.

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
| 100 | Surrogate retrained mid-run | The solver retries the current step in-process — it does not exit |
| 200 | Out of bounds | FireWorks launches parameter fitting, then restarts the solver |
| 201 | Model not in database | FireWorks initialises it from its module, then restarts the solver |
| 202 | Model has no fitted parameters | FireWorks runs its initialisation workflow, then restarts the solver |

See [Return codes](return-codes.md) for the full protocol.

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
