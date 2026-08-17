# Return codes

The canonical reference for every MoDeNa status code. The per-language
quick-starts reproduce the subset each one needs; this page is the source they
must agree with.

The numbers themselves are defined once, in `src/python/Strategy.py`:

```python
OUT_OF_BOUNDS        = 200
MODEL_NOT_FOUND      = 201
PARAMETERS_NOT_VALID = 202
```

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
| `201` | The model was not in the database and must be initialised from its module; no restart of this run | Exit with `201` |

`202` never appears here. It comes from `modena_model_new()` when the model
exists but has no usable fitted parameters — see below.

---

## Exit codes — what `handleReturnCode()` acts on

| Code | Exception raised | Framework response |
|------|------------------|--------------------|
| `200` | `OutOfBounds` | Queue a retraining detour for the out-of-bounds point, then relaunch this binary |
| `201` | `ParametersNotValid` | Identify the model via `loadFromModule()`, initialise it, relaunch |
| `202` | `ParametersNotValid` | Identify the uninitialised model, run its initialisation workflow, relaunch |
| any other non-zero | `TerminateWorkflow` | Stop. The failure is not recoverable |

> `201` does **not** mean "clean exit" or "workflow complete". Both branches of
> `handleReturnCode(201)` treat it as a model that needs initialising. The
> quick-start guides described it as a normal termination until 2026-08; if you
> have application code that exits 201 to signal success, it is signalling the
> opposite.

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
| `200` | `modena::ExitAndRestart` | `ExitAndRestart` | `modena.OutOfBounds` |
| `201` | `modena::ExitNoRestart` | `ExitNoRestart` | `modena.ParametersNotValid` |
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
