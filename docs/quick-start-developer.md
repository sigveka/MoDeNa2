# Quick-Start Guide — Integrating MoDeNa Models into Your Code

This guide explains how to call an existing MoDeNa surrogate model from your
simulation code and how to define a new model from scratch.  The `flowRate`
model from the `twoTanks` example is used throughout.

---

## Core concepts

```
┌──────────────────────────────────────────────────────────────┐
│  Macroscopic solver  (C++, Fortran, MATLAB, Python, …)       │
│                                                              │
│   calls modena_model_call() ──► surrogate (.so)  ◄── fast   │
│              │                                               │
│              │ out of bounds?                                │
│              ▼                                               │
│         return code 200 ──► FireWorks ──► exact simulation   │
│                                      ──► parameter fitting   │
│                                      ──► restart solver      │
└──────────────────────────────────────────────────────────────┘
```

**Surrogate function** — a compiled C shared library that evaluates a
polynomial or other analytical approximation.  Built automatically from C code
embedded in the model definition.

**Surrogate model** — a MongoDB document that stores the surrogate function
reference, current fitted parameters, input/output bounds, and training data.

**Backward mapping** — the adaptive loop: the macroscopic solver runs, the
surrogate is evaluated, and when a query falls outside the trained region the
exact simulation is called, the surrogate is refitted, and the solver restarts.

---

## Calling a model from C/C++

Link against `libmodena` and include `modena.h`.  The pattern is:
**load once before the time loop → set inputs → call → read outputs → handle
return code**.

```c
#include "modena.h"
#include <stdlib.h>

int main(void)
{
    /* ── Load model and allocate I/O vectors ── */
    modena_model_t   *model   = modena_model_new("flowRate");
    modena_inputs_t  *inputs  = modena_inputs_new(model);
    modena_outputs_t *outputs = modena_outputs_new(model);

    /* ── Cache input/output positions (do this ONCE, before the loop) ── */
    size_t pos_D       = modena_model_inputs_argPos(model,  "D");
    size_t pos_rho0    = modena_model_inputs_argPos(model,  "rho0");
    size_t pos_p0      = modena_model_inputs_argPos(model,  "p0");
    size_t pos_p1Byp0  = modena_model_inputs_argPos(model,  "p1Byp0");
    size_t pos_mdot    = modena_model_outputs_argPos(model, "flowRate");

    /* Verify that every declared input/output was queried */
    modena_model_argPos_check(model);

    /* ── Time-step loop ── */
    while (t < t_end)
    {
        t += dt;

        modena_inputs_set(inputs, pos_D,      D);
        modena_inputs_set(inputs, pos_rho0,   rho0);
        modena_inputs_set(inputs, pos_p0,     p0);
        modena_inputs_set(inputs, pos_p1Byp0, p1 / p0);

        int ret = modena_model_call(model, inputs, outputs);

        if (ret == 100) { t -= dt; continue; }   /* retrained — retry step */
        if (ret != 0)   { exit(ret); }            /* 200/201 — let FireWorks handle */

        double mdot = modena_outputs_get(outputs, pos_mdot);
        /* use mdot … */
    }

    /* ── Clean up ── */
    modena_inputs_destroy(inputs);
    modena_outputs_destroy(outputs);
    modena_model_destroy(model);
    return 0;
}
```

**CMakeLists.txt** to link against modena:

```cmake
find_package(MODENA REQUIRED)
target_link_libraries(myApp MODENA::modena)
```

---

## Calling a model from Fortran

Use the `fmodena_oop` module (Fortran 2003).  Resources are released
automatically when the `modena_model` variable goes out of scope.

```fortran
program twoTanks
    use fmodena_oop
    use iso_c_binding
    implicit none

    type(modena_model) :: m
    integer(c_size_t)  :: pos_D, pos_rho0, pos_p0, pos_p1Byp0, pos_mdot
    integer(c_int)     :: ret
    real(c_double)     :: D, rho0, p0, p1Byp0, mdot, t, dt, t_end

    ! ── Load model ──────────────────────────────────────────────────────────
    call m%init("flowRate")

    ! ── Cache positions (once, before the loop) ─────────────────────────────
    pos_D      = m%input_pos("D")
    pos_rho0   = m%input_pos("rho0")
    pos_p0     = m%input_pos("p0")
    pos_p1Byp0 = m%input_pos("p1Byp0")
    pos_mdot   = m%output_pos("flowRate")
    call m%check()

    ! ── Time-step loop ───────────────────────────────────────────────────────
    do while (t < t_end)
        t = t + dt

        call m%set(pos_D,      D)
        call m%set(pos_rho0,   rho0)
        call m%set(pos_p0,     p0)
        call m%set(pos_p1Byp0, p1 / p0)

        ret = m%call()

        if (ret == 100) then
            t = t - dt        ! surrogate retrained — retry this step
            cycle
        end if
        if (ret /= 0) call exit(ret)   ! 200/201 — FireWorks takes over

        mdot = m%get_output(pos_mdot)
        ! use mdot …
    end do

    ! m is destroyed automatically by the Fortran finaliser

end program twoTanks
```

**CMakeLists.txt:**

```cmake
find_package(MODENA REQUIRED)
target_link_libraries(myApp MODENA::fmodena_oop)
```

---

## Calling a model from MATLAB / Octave

Use the `Modena` class, which wraps the MEX gateway.

```matlab
% ── Load model ──────────────────────────────────────────────────────────────
m = Modena('flowRate');

% ── Cache positions (once, before the loop) ─────────────────────────────────
pos_D      = input_pos(m, 'D');
pos_rho0   = input_pos(m, 'rho0');
pos_p0     = input_pos(m, 'p0');
pos_p1Byp0 = input_pos(m, 'p1Byp0');
pos_mdot   = output_pos(m, 'flowRate');
check(m);

% ── Time-step loop ───────────────────────────────────────────────────────────
while t < t_end
    t = t + dt;

    set_input(m, pos_D,      D);
    set_input(m, pos_rho0,   rho0);
    set_input(m, pos_p0,     p0);
    set_input(m, pos_p1Byp0, p1 / p0);

    code = call(m);

    if code == 100, t = t - dt; continue; end   % retrained — retry step
    if code == 200 || code == 201, exit(code); end

    mdot = get_output(m, pos_mdot);
    % use mdot …
end

% m is freed automatically when it goes out of scope (RAII destructor)
```

The MEX gateway (`modena_gateway`) must be on the MATLAB path.  It is
installed to `${MODENA_MATLAB_DIR}` by CMake.  Add it once in `startup.m`:

```matlab
addpath(getenv('MODENA_MATLAB_DIR'));
```

---

## Defining a new model

A model package is a standard Python package that defines three things:
a **surrogate function** (C code), a **surrogate model** (MongoDB document),
and an **exact task** (FireTask that runs the expensive simulation).

The `flowRate` model (`examples/MoDeNaModels/flowRate/python/flowRate.py`)
is the canonical reference.

### 1 — Surrogate function

The surrogate function is C code with a specific signature, defined inline
using `CFunction`.  MoDeNa compiles it to a shared library automatically.

```python
from modena import CFunction

f = CFunction(
    Ccode='''
#include "modena.h"
#include "math.h"

void two_tank_flowRate
(
    const modena_model_t* model,
    const double* inputs,
    double* outputs
)
{
    {% block variables %}{% endblock %}   /* MoDeNa injects variable bindings here */

    const double P0 = parameters[0];
    const double P1 = parameters[1];

    outputs[0] = M_PI * pow(D, 2.0) * P1 * sqrt(P0 * rho0 * p0);
}
''',
    inputs={
        'D':      {'min': 0,    'max': 9e99},
        'rho0':   {'min': 0,    'max': 9e99},
        'p0':     {'min': 0,    'max': 9e99},
        'p1Byp0': {'min': 0,    'max': 1.0 },
    },
    outputs={
        'flowRate': {'min': 9e99, 'max': -9e99, 'argPos': 0},
    },
    parameters={
        'param0': {'min': 0.0, 'max': 10.0, 'argPos': 0},
        'param1': {'min': 0.0, 'max': 10.0, 'argPos': 1},
    },
)
```

The `{% block variables %}` block is filled in by MoDeNa's Jinja2 template
engine, which generates `const double D = inputs[0];` style bindings for each
declared input.  You use those variable names directly in the C body.

### 2 — Exact task

The exact task is a FireWorks `FireTask` that runs the expensive simulation
and writes its output back into `self['point']`.

```python
from fireworks.utilities.fw_utilities import explicit_serialize
from modena import ModenaFireTask
from jinja2 import Template
import os

@explicit_serialize
class FlowRateExactSim(ModenaFireTask):

    def task(self, fw_spec):
        # Write inputs to a file the simulation executable expects
        Template('{{ s.point.D }}\n{{ s.point.p0 }}\n').stream(s=self).dump('in.txt')

        # Locate the binary: checks MODENA_BIN_PATH / [binaries] paths in
        # modena.toml, then falls back to bin/ alongside this .py file.
        binary = self.find_binary('flowRateExact')
        ret = os.system(binary)
        self.handleReturnCode(ret)

        # Read output and store it back so MoDeNa can use it for fitting
        with open('out.txt') as fh:
            self['point']['flowRate'] = float(fh.readline())
```

### 3 — Surrogate model

Wire the surrogate function and exact task together with a `BackwardMappingModel`:

```python
from modena import BackwardMappingModel
import modena.Strategy as Strategy

m = BackwardMappingModel(
    _id='flowRate',
    surrogateFunction=f,
    exactTask=FlowRateExactSim(),
    substituteModels=[],
    initialisationStrategy=Strategy.InitialPoints(
        initialPoints={
            'D':      [0.01, 0.01, 0.01, 0.01],
            'rho0':   [3.4,  3.5,  3.4,  3.5 ],
            'p0':     [2.8e5, 3.2e5, 2.8e5, 3.2e5],
            'p1Byp0': [0.03, 0.03, 0.04, 0.04],
        },
    ),
    outOfBoundsStrategy=Strategy.ExtendSpaceStochasticSampling(
        nNewPoints=4,
    ),
    parameterFittingStrategy=Strategy.NonLinFitWithErrorContol(
        crossValidation=Strategy.Holdout(testDataPercentage=0.2),
        acceptanceCriterion=Strategy.MaxError(threshold=0.5),
        improveErrorStrategy=Strategy.StochasticSampling(nNewPoints=2),
    ),
)
```

**`_id`** — the name used when calling `modena_model_new("flowRate")`.

**`initialisationStrategy`** — points evaluated once by `./initModels` to seed
the database before the first simulation run.

**`outOfBoundsStrategy`** — what to do when the solver queries outside the
trained region.  `ExtendSpaceStochasticSampling` adds random points around the
out-of-bounds query.

**`nonConvergenceStrategy`** *(optional)* — what to do when an exact simulation
raises an exception (numerical failure, convergence error, etc.).

| Strategy | Behaviour |
|---|---|
| `SkipPoint()` | Log WARNING, skip the point, continue — **default** |
| `FizzleOnFailure()` | Re-raise → FireWorks marks the firework FIZZLED |
| `DefuseWorkflowOnFailure()` | Defuse the entire workflow (pre-3.x behaviour) |

Models where numerical failures are expected at certain input combinations
(e.g. mixture properties near phase boundaries) should set this explicitly:

```python
nonConvergenceStrategy=Strategy.SkipPoint(),
```

**`parameterFittingStrategy`** — how to fit the surrogate to the collected
data.  `NonLinFitWithErrorContol` uses non-linear least squares
(`scipy.optimize.least_squares`) with a composable cross-validation/acceptance
design:

| Constructor key | Type | Purpose |
|---|---|---|
| `crossValidation` | `CrossValidationStrategy` | How to split data into train/test folds.  Default: `Holdout(testDataPercentage=0.2)`. |
| `acceptanceCriterion` | `AcceptanceCriterionBase` | When to accept the fit.  Default: `MaxError(threshold=0.1)`. |
| `improveErrorStrategy` | `ImproveErrorStrategy` | What to do when the fit is rejected.  Typically `StochasticSampling(nNewPoints=N)`. |

Available cross-validation strategies:

| Strategy | Description |
|---|---|
| `Holdout(testDataPercentage)` | Single random train/test split |
| `KFold(k)` | k-fold cross-validation (shuffled) |
| `LeaveOneOut()` | Leave-one-out (N folds) |
| `LeavePOut(p)` | Leave-p-out (C(N,p) folds).  Raises `ValueError` when the fold count exceeds 1000 — use `KFold` or `LeaveOneOut` for larger datasets. |
| `Jackknife()` | LOO splits, mean error aggregation |

When the CV error is acceptable, the surrogate is refit on **all** data before
saving, giving the best possible parameters.

---

## Project layout

A typical model package follows this structure:

```
examples/
├── myExample/
│   ├── modena.toml         # tells MoDeNa where the model package is installed
│   ├── FW_config.yaml      # FireWorks config — ADD_USER_PACKAGES: [modena]
│   ├── initModels          # Python script: initialise and fit the surrogate
│   └── workflow            # Python script: run the simulation
│
└── MoDeNaModels/
    └── myModel/
        ├── CMakeLists.txt  # builds the exact-simulation executable
        └── python/
            ├── __init__.py
            └── myModel.py  # CFunction + BackwardMappingModel + FireTask
```

The example scripts at the project root tie everything together:

| Script | Purpose |
|--------|---------|
| `buildModels` | Compiles and installs model packages into `./models/` |
| `initModels` | Registers models in MongoDB and collects initial training data |
| `workflow` | Creates the FireWorks workflow and runs the simulation |

### `initModels`

```python
#!/usr/bin/env python3
import modena
import myModel  # noqa: F401 — registers the model via SurrogateModel.get_instances()

modena.run(list(modena.SurrogateModel.get_instances()))
```

`modena.run()` handles everything: it creates a `ModenaLaunchPad` from
`MODENA_URI`, resets the launchpad, constructs the initialisation workflow from
all registered models (one sub-workflow per model chained from a shared root),
adds it to the launchpad, and runs `rapidfire` until all Fireworks complete.

### `workflow`

```python
#!/usr/bin/env python3
import modena
from fireworks import Firework, Workflow
import myModel

wf = Workflow([Firework(myModel.m)], name='mySimulation')
modena.run(wf)
```

### `FW_config.yaml`

```yaml
ADD_USER_PACKAGES:
    - modena
REMOVE_USELESS_DIRS: True
```

When a Rocket subprocess deserializes tasks from MongoDB, it needs the
`@explicit_serialize` FireTask classes in scope.  Listing `modena` is
sufficient — on import, `modena` automatically imports every model package
installed in the registered prefixes (from `modena.toml` or `MODENA_PATH`),
populating the FireWorks task registry.  See
[Task serialization and FW_config.yaml](fireworks.md#task-serialization-and-fw_configyaml)
for details.

---

## Project configuration

Create a `modena.toml` in your project root to tell MoDeNa where the model
packages are installed and where to store compiled surrogate libraries:

```toml
[models]
paths = ["./models"]

[binaries]
paths = ["./models/bin"]     # omit to rely on the package-relative bin/ fallback

[surrogate_functions]
lib_dir = "./surrogate_functions"   # omit to use ~/.modena/surrogate_functions

[logging]
level = "INFO"       # WARNING | INFO | DEBUG | DEBUG_VERBOSE
# file = "run.log"   # optional: also write to a log file
```

The `[logging]` and `[binaries]` sections are optional.  The `MODENA_LOG_LEVEL`
environment variable overrides the log level when set.  Use `DEBUG_VERBOSE` to
also enable full FireWorks output (useful when diagnosing workflow failures).

See the [environment variable reference](model-registry.md#environment-variable-reference)
for session-level overrides via `MODENA_URI`, `MODENA_PATH`, `MODENA_BIN_PATH`,
and `MODENA_SURROGATE_LIB_DIR`.

---

## Troubleshooting

Run the environment health check before filing a bug:

```bash
modena doctor
```

This verifies `libmodena.so`, `modena.toml`, MongoDB connectivity, all
required Python packages, and key environment variables.

For a guided walkthrough of the full workflow:

```bash
modena quickstart
```
