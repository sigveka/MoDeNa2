# Quick-Start Guide — R Wrapper

This guide shows how to call a MoDeNa surrogate model from R and how to
enable the R wrapper at build time.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| R ≥ 4.0 | With a C compiler accessible to `R CMD INSTALL` (gcc/clang) |
| MoDeNa installed | `libmodena.so` and the Python `modena` package must be on the system |
| MongoDB running | Required at runtime when loading models |

---

## Installing the wrapper

The R wrapper is opt-in.  Enable it when configuring MoDeNa:

```bash
cmake -B build -DWITH_R=ON .
cmake --build build
cmake --install build
```

`cmake --install` runs `R CMD INSTALL` to compile the C extension and register
the `modena` package into R's default library.  If R is not on `PATH` at
configure time, the source is installed to
`${prefix}/share/modena/R/modena` and you can compile it manually later:

```bash
R CMD INSTALL "${prefix}/share/modena/R/modena"
```

---

## Environment

The R wrapper discovers `libmodena.so` at runtime using the same priority
order as the Julia wrapper:

1. `MODENA_LIB_DIR` environment variable (fastest, recommended for CI)
2. `python3 -c "import modena; print(modena.MODENA_LIB_DIR)"` (always
   available if MoDeNa is installed)

Set `MODENA_LIB_DIR` in your shell profile to avoid the Python subprocess
call at package load time:

```bash
export MODENA_LIB_DIR="${HOME}/lib"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
```

---

## Calling a model

The `Modena` reference class mirrors the Julia and MATLAB wrapper APIs.
The pattern is: **load once → cache positions → set inputs in the loop →
call → read outputs → handle return code**.

```r
library(modena)

# ── Load model and cache positions (do this once, before the loop) ── #
m          <- Modena$new("flowRate")
pos_D      <- m$input_pos("D")
pos_rho0   <- m$input_pos("rho0")
pos_p0     <- m$input_pos("p0")
pos_p1Byp0 <- m$input_pos("p1Byp0")
pos_mdot   <- m$output_pos("flowRate")
m$check()   # verify every declared input was queried

# ── Time-step loop ─────────────────────────────────────────────────── #
t <- 0.0
while (t < t_end) {
    t <- t + dt

    m$set(pos_D,      D)
    m$set(pos_rho0,   rho0)
    m$set(pos_p0,     p0)
    m$set(pos_p1Byp0, p1 / p0)

    ret <- m$call()

    if (ret == 100L) { t <- t - dt; next }   # surrogate retrained — retry
    if (ret != 0L)   stop(paste("MoDeNa exit:", ret))

    mdot <- m$output(pos_mdot)
    # use mdot ...
}
```

**Return codes from `$call()`:**

| Code | Meaning | Action |
|---|---|---|
| `0` | Success | Outputs are valid — use them |
| `100` | Surrogate retrained (out of bounds) | Decrement time step and retry (`next`) |
| `200` | Exit and restart | FireWorks re-queues the simulation; call `stop()` |
| `201` | Clean exit | Workflow complete; call `stop()` |

---

## Metadata

```r
m$inputs_size()        # number of inputs  (integer)
m$outputs_size()       # number of outputs (integer)
m$parameters_size()    # number of fitted parameters (integer)

m$inputs_names()       # character vector of input names in positional order
m$outputs_names()      # character vector of output names
m$parameters_names()   # character vector of parameter names

print(m)               # <Modena: 4 input(s), 1 output(s), 2 parameter(s)>
```

---

## Running the tests

The test suite uses `testthat`.  Unit tests (no libmodena required) check
the package structure.  Integration tests (require libmodena + MongoDB) are
skipped automatically when the library is not available.

```r
# From an R session with the package installed:
testthat::test_package("modena")

# Or from the shell, from the package source directory:
Rscript -e 'testthat::test_dir("tests/testthat")'
```

---

## Troubleshooting

**`libmodena could not be loaded at package attach`**

The package loaded but `libmodena.so` was not found.  Set `MODENA_LIB_DIR`
to the directory containing `libmodena.so` and reload the package:

```r
Sys.setenv(MODENA_LIB_DIR = "/path/to/lib")
library(modena)
```

**`Model 'flowRate' not found in database`**

The model has not been initialised.  Run `./initModels` in the example
directory first.

**`Symbol 'Py_DecRef' not found in libpython`**

libpython could not be promoted to the global symbol namespace.  Check that
`python3 -c "import sysconfig; print(sysconfig.get_config_var('LDLIBRARY'))"`
returns a valid shared-library name and that it is on `LD_LIBRARY_PATH`.
