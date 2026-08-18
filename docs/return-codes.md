# Return codes

The canonical reference for every MoDeNa status code. The per-language
quick-starts reproduce the subset each one needs; this page is the source they
must agree with.

The numbers themselves are defined in `src/python/Strategy.py`:

```python
OUT_OF_BOUNDS             = 200
MODEL_NOT_IN_DATABASE     = 201
PARAMETERS_NOT_VALID      = 202
INDEX_SET_NOT_IN_DATABASE = 401
INTERNAL_ERROR            = 1
```

Because C, Fortran, MATLAB and R compare integers rather than catching typed
exceptions, each exposes the same set as named constants. Use them instead of
writing the numbers inline:

| Language | How to reach them |
|---|---|
| Python | `from modena.Strategy import OUT_OF_BOUNDS, ...` |
| C / C++ | `enum modena_status_t` in `modena.h` — `MODENA_OUT_OF_BOUNDS`, … |
| Fortran | `use fmodena_status` — `MODENA_OUT_OF_BOUNDS`, … |
| MATLAB | `Modena.OUT_OF_BOUNDS`, … (constant properties) |
| R | `MODENA_OUT_OF_BOUNDS`, … (exported) |

`modena_status_t` is deliberately separate from `modena_error_t`, which is
**deprecated**. Its three "not found" values are never assigned by any code
path and never were — a missing model or function sets `201`, a missing index
set sets `401`. Only `MODENA_SUCCESS` there is live. The names survive because
the header is installed; they will go at the next major release.

Note `MODENA_MODEL_NOT_FOUND` is `1`, the same value as
`MODENA_INTERNAL_ERROR` — which is what actually produces it. That mismatch is
why the old name was misleading rather than merely unused.

`modena_error_message()` describes all of them; it used to return
"Unknown error" for anything above `3`, which is every code that actually
occurs.

`SurrogateModel.exception*()` returns them, libmodena reads them back off the
raised exception, and `handleReturnCode()` dispatches on them. No other file
should contain the literals.

---

## Two different things are called a "return code"

This is the distinction the language guides used to blur, and getting it wrong
breaks a workflow silently.

| | What it is | Who reads it |
|---|---|---|
| **Call result** | the `int` returned by `modena_model_call()` | your application, in-process |
| **Exit code** | the status your process terminates with | `handleReturnCode()`, in the FireWorks worker |

They overlap but are not the same list. `100` is only ever a call result — a
process that *exits* with 100 does not get retried, it falls into
`handleReturnCode`'s catch-all and terminates the workflow.

---

## Call results — what `modena_model_call()` returns

| Code | Meaning | What the application must do |
|------|---------|------------------------------|
| `0` | Success | Use the outputs; continue |
| `1` | Failure | Abort; this is not a protocol signal |
| `100` | Surrogate was retrained mid-run; parameters are now updated | **Retry the current step in-process.** Do not exit |
| `200` | Out of bounds — a new design of experiments is needed, then this run restarts | Exit with `200` |
| `201` | The model was not in the database and must be initialised from its module | Exit with `201` |

`202` never appears here. It comes from `modena_model_new()` when the model
exists but has no usable fitted parameters — see below.

---

## Exit codes — what `handleReturnCode()` acts on

| Code | Exception raised | Framework response |
|------|------------------|--------------------|
| `200` | `OutOfBounds` | Queue a retraining detour for the out-of-bounds point, then relaunch this binary |
| `201` | `ParametersNotValid` | Identify the model via `loadFromModule()`, initialise it, relaunch |
| `202` | `ParametersNotValid` | Identify the uninitialised model, run its initialisation workflow, relaunch |
| `401` | `TerminateWorkflow` | Stop, naming the missing IndexSet. Not recoverable: IndexSets are written to MongoDB when their package is imported, so there is no workflow to queue — check `MODENA_PATH` and that `initModels` has run |
| `1` | `TerminateWorkflow` | Stop. An internal libmodena failure (allocation, CPython call) |
| any other non-zero | `TerminateWorkflow` | Stop. The failure is not recoverable |

> `201` does **not** mean "clean exit" or "workflow complete", and it does not
> mean "no restart". Both branches of `handleReturnCode(201)` treat it as a
> model that needs initialising, and `executeAndCatchExceptions()` appends a
> *resume after init* Firework — so the simulation is re-queued exactly as it
> is for `200`. The guides described it as a normal termination, and
> `model.c`'s comment block called it "exit for new DOE without Restart";
> both were wrong. The C++/Julia exception was called `ExitNoRestart` for the
> same reason and is now `ExitAndInitialise`. If you have application code
> that exits 201 to signal success, it is signalling the opposite.

---

## Auto-initialisation — the 202 path

`modena_model_new()` returns `NULL` with `modena_error_code = 202` when the
model is in MongoDB but has no fitted parameters — freshly registered, with
`initModels` never run. The application propagates it:

```c
modena_model_t *model = modena_model_new("myModel");
if (modena_error_occurred()) { return modena_error(); }   /* 202 */
```

FireWorks then inserts an initialisation detour and re-queues the simulation.
This is why `./workflow` succeeds without running `./initModels` first.

---

## Languages that raise instead of returning

The C++, Julia and Python wrappers convert the codes into exceptions. The
mapping is exact — the code is still available on the exception.

| Code | C++ | Julia | Python |
|------|-----|-------|--------|
| `100` | `modena::ParametersUpdated` | `ParametersUpdated` | — |
| `200` | `modena::ExitAndRetrain` | `ExitAndRetrain` | `modena.OutOfBounds` |
| `201` | `modena::ExitAndInitialise` | `ExitAndInitialise` | `modena.ParametersNotValid` |
| `202` | — | — | `modena.ParametersNotValid` |
| other | `modena::ModenaError` | `ModenaError` | — |

In C++ and Julia the code is `e.code`; in Python it is `exc.returnCode`, and
`exc.model` identifies the surrogate that failed.

**Python differs in an important way.** `SurrogateModel.callModel()` raises
rather than exiting, so *the caller decides*. Whether to exit depends on who
launched the script:

* Launched by FireWorks as a `BackwardMappingScriptTask` subprocess — exit with
  `exc.returnCode`. The process exit status is the only channel back to
  `handleReturnCode()`.
* Run standalone — do not exit. Nothing is reading the status, and the exception
  carries more than an integer does.

---

## See also

* `modena model show <id>` — whether a model is trained
* [Architecture](architecture.md) — the full out-of-bounds loop
* `src/src/CLAUDE.md` — the C side of the 202 protocol
