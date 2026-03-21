# MoDeNa

**Mo**delling of morphology **De**velopment of micro- and **Na**nostructures —
an open-source multi-scale modelling framework.

MoDeNa lets macroscopic simulation codes (CFD solvers, process simulators,
Python scripts) call expensive sub-models at runtime through cheap surrogate
approximations. When the surrogate is queried outside its trained region,
MoDeNa automatically runs new exact simulations, refits the surrogate, and
restarts the caller — all without any application-side code changes.

---

## Documentation

| Guide | Contents |
|---|---|
| [Quick start — user](quick-start-user.md) | Installation, first run, environment setup |
| [Quick start — developer](quick-start-developer.md) | Define a new model, run a workflow |
| [Architecture](architecture.md) | Runtime call path, backward-mapping loop, protocol details |
| [Core developer guide](core-developer-guide.md) | C library, Python library, cross-language boundaries |
| [Model registry](model-registry.md) | `modena.toml`, `MODENA_PATH`, lock files |
| [FireWorks](fireworks.md) | Workflow engine integration, launchpad API, CLI reference |

## Language bindings

| Language | Guide |
|---|---|
| C | [quick-start-c.md](quick-start-c.md) |
| C++ | [quick-start-cpp.md](quick-start-cpp.md) |
| Fortran | [quick-start-fortran.md](quick-start-fortran.md) |
| Julia | [quick-start-julia.md](quick-start-julia.md) |
| MATLAB / Octave | [quick-start-matlab.md](quick-start-matlab.md) |
| R | [quick-start-r.md](quick-start-r.md) |

---

Source and full documentation: [github.com/sigveka/MoDeNa2](https://github.com/sigveka/MoDeNa2)
