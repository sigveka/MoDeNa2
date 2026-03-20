# Quick-Start — Calling MoDeNa Models from MATLAB / Octave

This guide covers the `Modena` handle class and the `modena_gateway` MEX/OCT
extension that backs it.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| MATLAB R2016b+ or GNU Octave ≥ 5 | |
| `modena_gateway` MEX/OCT file | Built and installed by MoDeNa's CMake |
| Python 3 with `modena` on `PYTHONPATH` | Used by the gateway to locate `libmodena` |
| MongoDB running | `MODENA_URI` must point to a populated database |

---

## Setup

Add the MoDeNa MATLAB directory to the MATLAB/Octave path.  Do this once in
`startup.m` (MATLAB) or `~/.octaverc` (Octave):

```matlab
addpath(getenv('MODENA_MATLAB_DIR'));
```

`MODENA_MATLAB_DIR` is set by CMake at install time (typically
`~/share/modena/matlab`).  Alternatively set it explicitly:

```matlab
addpath('/home/user/share/modena/matlab');
```

The gateway also needs Python to be reachable so it can locate `libmodena`:

```bash
export PYTHONPATH="${PYTHONPATH}:${HOME}/lib/python3.10/site-packages"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
```

---

## The pattern

```
1. Construct    model = Modena('id')
2. Cache once   pos = input_pos(model, 'name')   — before the loop
3. Check        check(model)
4. Per step     set_input → call → get_output
5. Destruct     delete(model)  or automatic on clear/scope exit
```

---

## Return codes

`call(model)` returns a scalar integer:

| Code | Meaning | Required action |
|------|---------|----------------|
| `0` | Success | Continue normally |
| `100` | Surrogate retrained | Decrement time, `continue` |
| `200` | Exit and restart | `exit(code)` — FireWorks relaunches |
| `201` | Clean exit | `exit(code)` — workflow complete |

---

## Example — twoTanks

Adapted from
`examples/MoDeNaModels/twoTankMatlab/src/twoTanksMacroscopicProblemMatlab.m`.

```matlab
% Physical constants and initial conditions
D      = 0.01;
R      = 287.1;
T_gas  = 300.0;
V0     = 0.1;    V1     = 1.0;
deltat = 1e-3;   tend   = 5.5;

p0 = 3e5;        p1 = 1e4;
m0 = p0*V0/R/T_gas;   m1 = p1*V1/R/T_gas;
rho0 = m0/V0;         rho1 = m1/V1;
t = 0.0;

% ── 1. Load model ───────────────────────────────────────────────────────────
model = Modena('flowRate');

% Print metadata (optional)
fprintf('inputs:\n');
for n = inputs_names(model);      fprintf('  %s\n', n{1}); end
fprintf('outputs:\n');
for n = outputs_names(model);     fprintf('  %s\n', n{1}); end
fprintf('parameters:\n');
for n = parameters_names(model);  fprintf('  %s\n', n{1}); end

% ── 2. Cache argument positions (once, before the loop) ─────────────────────
pos_D    = input_pos(model, 'D');
pos_rho0 = input_pos(model, 'rho0');
pos_p0   = input_pos(model, 'p0');
pos_p1p0 = input_pos(model, 'p1Byp0');
pos_mdot = output_pos(model, 'flowRate');

% ── 3. Verify every declared input was queried ──────────────────────────────
check(model);

% ── 4. Time-step loop ───────────────────────────────────────────────────────
while t + deltat < tend + 1e-10

    t = t + deltat;

    if p0 > p1
        set_input(model, pos_D,    D);
        set_input(model, pos_rho0, rho0);
        set_input(model, pos_p0,   p0);
        set_input(model, pos_p1p0, p1/p0);
    else
        set_input(model, pos_D,    D);
        set_input(model, pos_rho0, rho1);
        set_input(model, pos_p0,   p1);
        set_input(model, pos_p1p0, p0/p1);
    end

    code = call(model);

    if     code == 100,              t = t - deltat; continue   % retrained
    elseif code == 200 || code == 201, exit(code);              % workflow done
    elseif code ~= 0
        error('Modena:call', 'modena_model_call returned %d', code);
    end

    mdot = get_output(model, pos_mdot);

    if p0 > p1
        m0 = m0 - mdot*deltat;   m1 = m1 + mdot*deltat;
    else
        m0 = m0 + mdot*deltat;   m1 = m1 - mdot*deltat;
    end

    rho0 = m0/V0;   p0 = rho0*R*T_gas;
    rho1 = m1/V1;   p1 = rho1*R*T_gas;

    fprintf('t=%.3f  p0=%.1f  p1=%.1f\n', t, p0, p1);
end

% ── 5. Release resources ────────────────────────────────────────────────────
delete(model);
```

---

## API reference

| Method | Description |
|--------|-------------|
| `Modena(id)` | Load surrogate model by ID; allocates I/O vectors |
| `input_pos(m, name)` | Return 0-based position of input `name` |
| `output_pos(m, name)` | Return 0-based position of output `name` |
| `check(m)` | Assert every input has been queried via `input_pos` |
| `set_input(m, pos, value)` | Set input at position `pos` |
| `get_output(m, pos)` | Read output at position `pos` after a successful `call` |
| `call(m)` | Evaluate the surrogate; returns integer code |
| `inputs_names(m)` | Cell array of input names in positional order |
| `outputs_names(m)` | Cell array of output names in positional order |
| `parameters_names(m)` | Cell array of fitted parameter names |
| `inputs_size(m)` | Number of inputs |
| `outputs_size(m)` | Number of outputs |
| `parameters_size(m)` | Number of fitted parameters |
| `delete(m)` | Free C handles (called automatically by destructor) |

---

## Troubleshooting

**`modena_gateway` not found**
Ensure `MODENA_MATLAB_DIR` is on the path and the `.mex`/`.oct` file was
built for your platform.  Rebuild with:
```bash
cmake --build /path/to/modena/build --target modena_gateway
cmake --install /path/to/modena/build
```

**`Cannot determine MODENA_LIB_DIR`**
The gateway queries Python to find `libmodena`.  Either set
`MODENA_LIB_DIR` explicitly before starting MATLAB/Octave:
```bash
export MODENA_LIB_DIR=/home/user/lib/modena
```
or ensure `python3` is on `PATH` with `modena` importable.
