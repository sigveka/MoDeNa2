# twoTanks

Demonstrates the basic MoDeNa backward-mapping loop using a C macroscopic
solver.  Air discharges from one tank into another through a nozzle; the
nozzle flow rate is the sub-model replaced by a surrogate.

**Macroscopic solver:** `twoTanksMacroscopicProblem` (C)
**Surrogate model:** `flowRate` (polynomial, backward mapping)

## How to run

```bash
# 1. Compile and install model packages
./buildModels

# 2. Initialise surrogate in the database
./initModels

# 3. Run the simulation (retraining happens automatically when out-of-bounds)
./workflow

# 4. Run again — no retraining, surrogate covers the full input space
./workflow
```

---

## Model definition philosophy

Every MoDeNa model has two independent parts that communicate only through
the model's `_id` string and the ordering of the `inputs[]`/`outputs[]`
arrays:

```
examples/MoDeNaModels/
└── flowRate/python/flowRate.py   ← Python: surrogate definition (CFunction +
                                            BackwardMappingModel, bounds, strategy)
└── twoTank/python/twoTank.py     ← Python: macroscopic solver task (TwoTankModel)

examples/MoDeNaModels/
└── twoTank/src/twoTanksMacroscopicProblem.C  ← C: macroscopic solver binary
```

**`flowRate.py`** defines what the surrogate *looks like*: the C function
template, input/output bounds, and fitting strategy.  It never knows which
solver will call it.

**`twoTanksMacroscopicProblem.C`** calls `modena_model_call("flowRate", ...)`
from the C API.  It never knows that a surrogate exists — to it, `flowRate`
is just a function handle.

**`twoTank.py`** wraps the binary in a `BackwardMappingScriptTask` subclass
(`TwoTankModel`) so FireWorks can manage the backward-mapping loop: launch the
binary, intercept the out-of-bounds exit code, queue parameter fitting, and
restart.

---

## How `modena.toml` ties it together

```toml
[models]
paths = ["./models"]           # where installed model packages are searched

[surrogate_functions]
lib_dir = "../"                # where compiled surrogate .so files are cached

[simulate]
target = "twoTank.TwoTankModel"  # class to instantiate for the simulation task

[simulate.kwargs]
end_time = 5.5                 # forwarded as --end-time to the binary
```

When `./buildModels` runs, it compiles and installs both model packages into
`./models/`:

```
models/lib/pythonX.Y/site-packages/
├── flowRate/          ← surrogate definition (CFunction, BackwardMappingModel)
└── twoTank/
    ├── __init__.py    ← exports m and TwoTankModel
    └── bin/
        └── twoTanksMacroscopicProblem   ← compiled binary
```

`buildModels` also registers the `./models` prefix in `~/.modena/config.toml`
so modena knows where to look for packages on this machine.

When `./workflow` runs (`python3 -m modena simulate`):

1. **modena reads `modena.toml`** and adds `./models` to the search path.
2. **modena imports every package** found under `./models` — including
   `twoTank` and `flowRate` — registering their surrogate models and FireTask
   classes in memory.
3. **`[simulate] target`** is resolved: modena imports `twoTank`, gets
   `TwoTankModel`, and calls `TwoTankModel(end_time=5.5)` (kwargs from
   `[simulate.kwargs]`).
4. **`TwoTankModel.__init__`** calls `self.find_binary('twoTanksMacroscopicProblem')`,
   which searches the installed packages and resolves to
   `./models/.../twoTank/bin/twoTanksMacroscopicProblem`.
5. **FireWorks** wraps this in a Firework and launches it.  If the binary
   exits with code 200 (out-of-bounds), FireWorks inserts a parameter-fitting
   Firework before restarting the simulation — the backward-mapping loop.
