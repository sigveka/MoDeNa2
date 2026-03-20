# Quick-Start — Calling MoDeNa Models from Julia

This guide covers the `Modena.jl` wrapper module.  It uses Julia's `ccall`
to call `libmodena` directly at runtime and signals workflow events as
exceptions.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Julia ≥ 1.6 | |
| `libmodena` | Installed by MoDeNa's CMake build |
| Python 3 with `modena` on `PYTHONPATH` | Used at startup to locate `libmodena` |
| MongoDB running | `MODENA_URI` must point to a populated database |

```bash
export PYTHONPATH="${PYTHONPATH}:${HOME}/lib/python3.10/site-packages"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
```

---

## Installation

The `Modena` Julia package lives in `src/wrappers/julia/`.  Add it to your
Julia environment:

```julia
using Pkg
Pkg.develop(path="/path/to/MoDeNa/src/wrappers/julia")
```

Or, if it has been registered in a local registry:

```julia
Pkg.add("Modena")
```

---

## Library discovery

On `using Modena`, the module locates `libmodena` in this order:

1. `MODENA_LIB_DIR` environment variable
2. Query `python3 -c "import modena; print(modena.MODENA_LIB_DIR)"`
3. Standard dynamic linker search (`LD_LIBRARY_PATH`)

Set `MODENA_LIB_DIR` explicitly to skip the Python query:

```bash
export MODENA_LIB_DIR=/home/user/lib/modena
```

---

## The pattern

```
1. Construct    model = Model("id")
2. Cache once   pos = input_pos(model, "name")   — before the loop
3. Check        check(model)
4. Per step     set! → call! → output
5. GC           automatic finaliser frees C handles
```

---

## Exceptions

`call!(model)` throws instead of returning a non-zero integer:

| Exception | Trigger | Required action |
|-----------|---------|----------------|
| `ParametersUpdated` | ret == 100, surrogate retrained | Decrement time, retry step |
| `ExitAndRestart` | ret == 200, DoE campaign needed | `exit(e.code)` |
| `ExitNoRestart` | ret == 201, workflow complete | `exit(e.code)` |
| `ModenaError` | Any other non-zero code | `e.code` holds the integer |

---

## Example — twoTanks

Adapted from
`examples/MoDeNaModels/twoTankJulia/src/twoTanksMacroscopicProblemJulia.jl`.

```julia
using Modena

# Physical constants and initial conditions
const D      = 0.01
const R      = 287.1
const T_gas  = 300.0
const V0     = 0.1;    V1     = 1.0
const deltat = 1e-3;   tend   = 5.5

p0 = 3e5;   p1 = 1e4
m0 = p0*V0/R/T_gas;   m1 = p1*V1/R/T_gas
rho0 = m0/V0;         rho1 = m1/V1
t = 0.0

# ── 1. Construct — GC finaliser frees C handles automatically ───────────────
model = Model("flowRate")

# Print metadata (optional)
println("inputs:") ;    foreach(n -> println("  ", n), inputs_names(model))
println("outputs:");    foreach(n -> println("  ", n), outputs_names(model))
println("parameters:"); foreach(n -> println("  ", n), parameters_names(model))

# ── 2. Cache argument positions (once, before the loop) ─────────────────────
pos_D    = input_pos(model, "D")
pos_rho0 = input_pos(model, "rho0")
pos_p0   = input_pos(model, "p0")
pos_p1p0 = input_pos(model, "p1Byp0")
pos_mdot = output_pos(model, "flowRate")

# ── 3. Verify every declared input was queried ──────────────────────────────
check(model)

# ── 4. Time-step loop ───────────────────────────────────────────────────────
while t + deltat < tend + 1e-10

    global t, m0, m1, rho0, rho1, p0, p1

    t += deltat

    if p0 > p1
        set!(model, pos_D,    D)
        set!(model, pos_rho0, rho0)
        set!(model, pos_p0,   p0)
        set!(model, pos_p1p0, p1/p0)
    else
        set!(model, pos_D,    D)
        set!(model, pos_rho0, rho1)
        set!(model, pos_p0,   p1)
        set!(model, pos_p1p0, p0/p1)
    end

    try
        call!(model)
    catch e
        if e isa ParametersUpdated
            t -= deltat    # surrogate retrained — retry this step
            continue
        elseif e isa ExitAndRestart || e isa ExitNoRestart
            exit(e.code)
        else
            rethrow()
        end
    end

    mdot = output(model, pos_mdot)

    if p0 > p1
        m0 -= mdot*deltat;   m1 += mdot*deltat
    else
        m0 += mdot*deltat;   m1 -= mdot*deltat
    end

    rho0 = m0/V0;   p0 = rho0*R*T_gas
    rho1 = m1/V1;   p1 = rho1*R*T_gas

    @printf("t=%.3f  p0=%.1f  p1=%.1f\n", t, p0, p1)
end

# ── 5. model freed by GC finaliser — nothing to do explicitly ───────────────
```

---

## API reference

| Function | Description |
|----------|-------------|
| `Model(id)` | Load surrogate model by ID; registers GC finaliser |
| `input_pos(m, name)` | Return 0-based position of input `name` |
| `output_pos(m, name)` | Return 0-based position of output `name` |
| `check(m)` | Assert every declared input has been queried |
| `set!(m, pos, value)` | Set input at position `pos` |
| `output(m, pos)` | Read output at position `pos` after a successful `call!` |
| `call!(m)` | Evaluate the surrogate; throws on non-zero return code |
| `inputs_names(m)` | `Vector{String}` of input names in positional order |
| `outputs_names(m)` | `Vector{String}` of output names in positional order |
| `parameters_names(m)` | `Vector{String}` of fitted parameter names |
| `inputs_size(m)` | Number of inputs |
| `outputs_size(m)` | Number of outputs |
| `parameters_size(m)` | Number of fitted parameters |

---

## Notes

**`global` declarations** — The example uses module-level `global` statements
inside the `while` loop because Julia requires explicit `global` for
assignment to outer-scope variables from within a loop in script mode.  In a
function this is not needed:

```julia
function run_simulation()
    model = Model("flowRate")
    # ... no global declarations needed inside a function
end
```

Wrapping the simulation in a function is also the recommended Julia practice
for performance, as it allows the compiler to infer types.

**Thread safety** — `libmodena` embeds a Python interpreter.  Do not call
MoDeNa functions from multiple Julia threads simultaneously.
