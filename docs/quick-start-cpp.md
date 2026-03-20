# Quick-Start — Calling MoDeNa Models from C++

This guide covers the RAII C++ wrapper (`modena/modena.hpp`).  It uses
exceptions instead of integer return codes and manages all resources
automatically.  For the raw C API see [quick-start-c.md](quick-start-c.md).

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `libmodena` | Installed by MoDeNa's CMake build |
| C++17 or later | Required by the wrapper header |
| CMake ≥ 3.0 | For `find_package(MODENA)` |
| MongoDB running | `MODENA_URI` must point to a populated database |

```bash
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
export PYTHONPATH="${PYTHONPATH}:${HOME}/lib/python3.10/site-packages"
```

---

## CMake integration

```cmake
cmake_minimum_required(VERSION 3.0)
project(myApp CXX)

find_package(MODENA REQUIRED)

add_executable(myApp main.cpp)
target_link_libraries(myApp MODENA::modena_cpp)
target_compile_features(myApp PRIVATE cxx_std_17)
```

---

## The pattern

```
1. Construct    modena::Model model("id")   — loads model, owns all handles
2. Cache once   model.input_pos("name")     — before the loop
3. Per step     model.set → model.call → model.output
4. Destruct     automatic when model goes out of scope
```

Errors and workflow events are signalled by exceptions, not return codes.

---

## Exceptions

| Exception | Trigger | Required action |
|-----------|---------|----------------|
| `modena::ParametersUpdated` | ret == 100, surrogate retrained | Decrement time, retry step |
| `modena::ExitAndRestart` | ret == 200, DoE campaign needed | `exit(e.code)` |
| `modena::ExitNoRestart` | ret == 201, workflow complete | `exit(e.code)` |
| `modena::ModelNotFound` | Model ID not in database | Fix `_id` or run `initModels` |
| `modena::Exception` | Base class for all MoDeNa exceptions | `e.code` holds the integer code |

---

## Example — twoTanks

Adapted from
`examples/MoDeNaModels/twoTankCxx/src/twoTanksMacroscopicProblemCxx.C`.

```cpp
#include <modena/modena.hpp>
#include <iostream>

int main()
{
    const double D      = 0.01;
    const double R      = 287.1;
    const double T      = 300.0;
    const double V0     = 0.1,  V1     = 1.0;
    const double deltat = 1e-3, tend   = 5.5;

    double p0 = 3e5, p1 = 1e4;
    double m0 = p0*V0/R/T, m1 = p1*V1/R/T;
    double rho0 = m0/V0,   rho1 = m1/V1;
    double t = 0.0;

    try
    {
        /* ── 1. Construct — owns model, inputs, and outputs handles ──────── */
        modena::Model model("flowRate");

        /* Optionally print metadata */
        std::cout << "inputs:\n";
        for (const auto& n : model.inputs_names())
            std::cout << "  " << n << '\n';

        /* ── 2. Cache positions once before the loop ─────────────────────── */
        const std::size_t pos_D    = model.input_pos("D");
        const std::size_t pos_rho0 = model.input_pos("rho0");
        const std::size_t pos_p0   = model.input_pos("p0");
        const std::size_t pos_p1p0 = model.input_pos("p1Byp0");
        model.check();   /* verify every declared input was queried */

        /* ── 3. Time-step loop ───────────────────────────────────────────── */
        while (t + deltat < tend + 1e-10)
        {
            t += deltat;

            if (p0 > p1) {
                model.set(pos_D,    D);
                model.set(pos_rho0, rho0);
                model.set(pos_p0,   p0);
                model.set(pos_p1p0, p1/p0);
            } else {
                model.set(pos_D,    D);
                model.set(pos_rho0, rho1);
                model.set(pos_p0,   p1);
                model.set(pos_p1p0, p0/p1);
            }

            try {
                model.call();
            } catch (const modena::ParametersUpdated&) {
                t -= deltat;   /* surrogate retrained — retry this step */
                continue;
            }

            const double mdot = model.output(0);   /* positional access */

            if (p0 > p1) { m0 -= mdot*deltat; m1 += mdot*deltat; }
            else         { m0 += mdot*deltat; m1 -= mdot*deltat; }

            rho0 = m0/V0;   p0 = rho0*R*T;
            rho1 = m1/V1;   p1 = rho1*R*T;

            std::cout << "t=" << t << "  p0=" << p0 << "  p1=" << p1 << '\n';
        }

    } /* ── 4. model destroyed automatically here ─────────────────────────── */
    catch (const modena::ExitAndRestart& e) { return e.code; }
    catch (const modena::ExitNoRestart&  e) { return e.code; }
    catch (const modena::Exception&      e) {
        std::cerr << "MoDeNa error: " << e.what() << '\n';
        return e.code;
    }

    return 0;
}
```

---

## Named output access

In addition to positional access (`model.output(0)`), outputs can be read by
name:

```cpp
const double mdot = model.output("flowRate");
```

Named access performs a lookup on every call.  Cache the position with
`output_pos` if this is inside a tight loop:

```cpp
const std::size_t pos_mdot = model.output_pos("flowRate");
// ...
const double mdot = model.output(pos_mdot);
```

---

## Named input assignment via `operator[]`

The wrapper also provides a subscript operator for setting inputs by name,
useful for setup code where ergonomics matter more than performance:

```cpp
model["D"]      = 0.01;
model["rho0"]   = rho0;
model["p0"]     = p0;
model["p1Byp0"] = p1/p0;
model.call();
```

For the simulation loop, prefer the cached-position form (`model.set(pos,
val)`) to avoid repeated name lookups.
