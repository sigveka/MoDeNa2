# TODO

Planned work and known limitations for MoDeNa 2.x.

Last reconciled against the tree on **2026-09-28** (`40e5b09`).

---

## Recently landed

Work delivered since this file was last written, listed here so the open
items below are not read as a description of the whole project.

### In-place surrogate parameter update — **done**

Was: the optimizer called `modena_model_new()` on every iteration, allocating
and discarding a full `modena_model_t` per callback.

`CrossValidation.fit()` (`src/python/Strategy.py`) now constructs one
`modena_model_t` and assigns `cModel.parameters` per iteration;
`modena_model_t_set_parameters()` (`src/src/model.c`) writes the internal
`double[]` in place.  The public C function
`modena_model_set_parameters()` originally proposed here was **not** added —
the Python-side setter covered the need, and nothing in C wanted it.

### Parallel cross-validation folds — **done**

Folds are submitted to a `concurrent.futures.ProcessPoolExecutor` in
`NonLinFitWithErrorContol` (`src/python/Strategy.py`).  The picklability
problem was solved with `_FitProxy`, a plain-data snapshot from which each
worker re-initialises its own `modena_model_t`; no MongoEngine object and no
`modena_model_t` crosses the process boundary.  Falls back to serial when the
model has `substituteModels`.

This was the stated prerequisite for Phase 4, which is therefore unblocked.

### Return-code protocol, defined once — **done**

The out-of-bounds / parameters-not-valid protocol codes are now declared in
one place (`src/python/_status_codes.py`) and generated into the C, Fortran,
MATLAB and R bindings at build time.  `handleReturnCode` dispatches on named
constants instead of integer literals, and the `200`-or-`202` fallback — a
race, since the two were indistinguishable at the call site — is gone:
`OutOfBounds` and `ParametersNotValid` now carry their own `returnCode`.
`docs/return-codes.md` is the reference; `ExitNoRestart` and `ExitAndRestart`
were renamed `ExitAndInitialise` and `ExitAndRetrain`.

### Per-model integration snippets — **done**

`modena model integrate` generates a ready-to-paste call site for a given
model in all seven supported languages, protocol handling included.  Guarded
by the `modena_generated_snippets` ctest entry.

### Local portal — substantially built out

See *Relationship to the existing portal* below for what it now covers.

---

## Near-term

### `JigglePoint` non-convergence strategy

**File:** `src/python/Strategy.py`

`BackwardMappingModel` accepts a `nonConvergenceStrategy` that controls what
happens when an exact simulation raises an exception.  The existing options are:

| Class | Behaviour |
|---|---|
| `SkipPoint()` | Skip the failing point, continue — **default** |
| `FizzleOnFailure()` | Stop the workflow |
| `DefuseWorkflowOnFailure()` | Defuse the entire workflow |

A useful addition would be `JigglePoint(n=3, scale=0.01)`: retry the failing
point up to `n` times with a small random perturbation
(`point[k] *= 1 + U(-scale, scale)`).  This handles models that fail at exact
grid intersections or phase boundaries but succeed at nearby inputs.

---

### Integration test for the Python↔C `minMax()` boundary

**Files:** `src/python/SurrogateModel.py`, `src/src/model.c`

`SurrogateModel.minMax()` returns a tuple that `model.c:modena_model_get_minMax()`
reads by raw integer index.  If the two sides fall out of sync the failure is
silent at runtime — the surrogate silently uses wrong bounds or segfaults.

`src/tests/python/test_minmax_abi.py` pins the tuple's shape and ordering from
the Python side, and catches an accidental reorder in `SurrogateModel`.  What is
still missing is the other half: a C-level test that loads a known model, calls
`modena_model_get_minMax()`, and asserts the values at each index — so that a
change to the *reader* in `model.c` also fails loudly.  No test under
`src/tests/c/` references `minMax` today.

---

## Planned phases

### Phase 1 — Units and variable dtype

*Python-only.  Additive changes; no breaking changes to the C ABI or MongoDB schema.*

- **`Units.py`** — a unit registry mapping physical unit strings (e.g. `"Pa"`,
  `"degC"`) to SI conversion factors and offsets.
- **`dtype` field on inputs** — `'continuous'` (default), `'integer'`, or
  `'boolean'`.  `callModel()` would round integer inputs and clamp boolean
  inputs before passing them to the surrogate.
- **`units` field on inputs and outputs** — stored in MongoDB alongside
  `min`/`max`/`argPos`.  `callModel()` accepts user-supplied units and converts
  to SI internally.
- **CLI update** — `modena model show` displays units and dtype alongside the
  existing bounds table.

---

### Phase 2 — Input normalisation

*Requires changes to both the Python library and `libmodena` (C).*

When surrogate inputs span very different physical scales (e.g. pressure in Pa
alongside temperature in K) the fitting landscape is poorly conditioned and
convergence suffers.  Normalising all inputs to [0, 1] before fitting and
evaluation addresses this.

- Opt-in via `normalize_inputs = True` on `BackwardMappingModel`.
- `modena_model_call()` in C applies the same normalisation before calling the
  compiled surrogate `.so`.
- Stored `fitData` is re-normalised when bounds expand (out-of-bounds event).
- **Sampler change:** Latin Hypercube Sampling is incompatible with sequential
  data collection (it is designed for one-shot experiments).  Phase 2 replaces
  it with a maximin-distance criterion for the out-of-bounds expansion step,
  while retaining LHS for the initial `InitialPoints` strategy.

---

### Phase 3 — Complete the C units API

*Blocked on Phase 1.*

Three functions are declared in the public header but not yet implemented:

| Function | Header |
|---|---|
| `modena_siunits_get()` | `inputsoutputs.h` |
| `modena_model_inputs_siunits()` | `model.h` |
| `modena_model_outputs_siunits()` | `model.h` |

Do not call these — they will link but return garbage.  Tests exist in
`src/tests/c/test_siunits.c` but are disabled with `#if 0`.  Remove the
guards when the implementations are added.

---

### Phase 4 — Data-driven surrogate function types

*Requires new `SurrogateFunction` subclasses and auto-generated C evaluation code.
Its prerequisite — parallel CV folds — has landed, so this phase is unblocked.
Nothing is implemented yet: `SurrogateFunction` still has only `CFunction` and
`Function` as subclasses, and sklearn is not a dependency.*

Currently every surrogate requires the model author to write the C evaluation
function by hand.  This is appropriate when the functional form is known
(ideal gas law, Arrhenius kinetics, etc.).  When the form is unknown,
data-driven methods should discover it automatically from the training data.

Three families in rough order of implementation complexity:

#### Linear and projection-based methods

**Candidates:** Partial Least Squares (`sklearn.cross_decomposition.PLSRegression`),
ridge regression, LASSO, polynomial regression with explicit feature expansion.

These fit naturally into the existing architecture:

- A new `PLSFunction` (or `LinearSurrogateFunction`) subclass of `SurrogateFunction`
  auto-generates the C evaluation code from the fitted weight vectors and
  intercepts — e.g. `outputs[0] = b0 + b1*inputs[0] + b2*inputs[1] + ...`.
- The fitted coefficients are stored in the existing flat `parameters` list,
  with `argPos` assigned automatically.
- Fitting replaces `scipy.optimize.least_squares` with the appropriate sklearn
  estimator.  The `NonLinFitWithErrorContol` strategy is replaced by a new
  `LinearFitStrategy` that wraps sklearn's `fit()` / `predict()` interface.
- Cross-validation and acceptance criteria reuse the existing
  `CrossValidationStrategy` / `AcceptanceCriterionBase` hierarchy unchanged.

PLS is particularly attractive for high-dimensional input spaces where inputs
are correlated — it projects to latent variables before regression.

#### Kernel and interpolation methods

**Candidates:** Gaussian Process Regression
(`sklearn.gaussian_process.GaussianProcessRegressor`),
Radial Basis Function interpolation (`scipy.interpolate.RBFInterpolator`).

These are more complex because the surrogate evaluation at prediction time
requires summing over all training points.  The "parameters" are not a small
fixed-size vector — they are the full training dataset plus kernel
hyperparameters.

Options for C code generation:
- Embed training data as static arrays in the generated C file (works for
  small datasets; generates large `.so` files for large ones).
- Store training data in a separate binary file and `mmap` it at runtime.
- A new `structured_parameters` field on `SurrogateFunction` to hold matrix
  data separately from the scalar `parameters` list.

GPR has the advantage of providing prediction uncertainty estimates, which
could feed back into the out-of-bounds sampling strategy (query points where
uncertainty is highest rather than where the input is furthest from the
training set).

#### Support Vector Regression

**Candidates:** `sklearn.svm.SVR`, `sklearn.svm.NuSVR`.

Similar structure to GPR — evaluation is a weighted sum over support vectors.
C code generation is straightforward for RBF and polynomial kernels.

---

### Phase 5 — Neural network surrogates

*Further out.  Parallel CV folds have landed; Phase 4 linear methods have not,
and should come first.  The design decision below is settled; no code exists.*

Neural networks offer flexible approximation for highly nonlinear sub-models
but introduce significant infrastructure requirements.

#### Feedforward networks with compiled C inference

Small fully-connected networks (up to ~3 hidden layers, ~64 units) can be
expressed as C code — the evaluation is a sequence of matrix multiplications
and pointwise activation functions.  The generated C would look like:

```c
/* Auto-generated by MoDeNa from a trained 2-layer network */
void myModel_nn(const modena_model_t* model,
                const double* inputs, double* outputs)
{
    /* layer 1: tanh(W1 @ x + b1) */
    double h[16];
    for (int i = 0; i < 16; i++) {
        double z = parameters[bias1_offset + i];
        for (int j = 0; j < N_INPUTS; j++)
            z += parameters[w1_offset + i*N_INPUTS + j] * inputs[j];
        h[i] = tanh(z);
    }
    /* layer 2: W2 @ h + b2 */
    ...
    outputs[0] = ...;
}
```

Weights and biases are stored as the flat `parameters` array (flattened
row-major).  Training uses PyTorch or JAX; the trained weights are extracted
and stored in MongoDB after training.

The `argPos` system would need to accommodate very large parameter counts
(thousands to millions of floats) without the current assumption that
parameters are a small set of physically meaningful constants.

#### A separate `CFunction` type, not an extension of the existing one

**Decision:** generated surrogate bodies index `parameters[i]` directly rather
than using the synthesized named bindings — see *Quick-start (developer) →
When to index the array instead*.  That resolves the code-generation question
for polynomials, and it is enough for them.  It is **not** enough for networks,
which need a different document layout and therefore a different `CFunction`
subclass.

The C ABI is already fine.  `modena_model_t` carries
`double *parameters` + `size_t parameters_size` (`src/src/model.h`), which is
exactly the flat row-major weight buffer a generated forward pass wants.  The
one hostile member is `const char** parameters_names`.

What breaks is the Python-side document model, where every parameter is a
first-class named entity:

| Per-weight cost | Location |
|---|---|
| a `MinMax` embedded document | `SurrogateFunction.parameters` (`MapField`) |
| a float keyed by name | `SurrogateModel.parameters` (`DictField`) |
| a name string in the ABI tuple | `minMax()` index 4 → `parameters_names` |
| a `const double` line | the Jinja2 variables block |

Measured with `bson.encode`, that is 39 bytes per weight in
`SurrogateFunction.parameters` and 16 in `SurrogateModel.parameters`, so the
binding document hits the 16 MB BSON limit at roughly 430 000 weights — with
`fitData` still to fit elsewhere.  Long before that ceiling, marshalling a
list of 10⁵ name strings on every model construction is pure waste.  Two further assumptions do not survive the move either:
`parameters_array()` fills unfitted parameters with bound midpoints, where a
network wants Xavier/He initialisation; and per-weight `min`/`max` bounds are
meaningless.

So the new type should:

- store weights as one binary blob (BSON `BinaryField`, or GridFS past 16 MB)
  with a small shape/architecture descriptor, instead of N embedded documents;
- declare only *hyperparameters* — layer sizes, activations — as named
  parameters, so `parameters_names` stays short and the existing tooling
  (`model show`, the portal, lock files) keeps working;
- unpack the blob into `modena_model_t.parameters` at construction, leaving
  the C side and the generated inference code unchanged;
- pair with the `NeuralNetFitStrategy` described below, since
  `scipy.optimize.least_squares` over 10⁵ parameters is not viable.

Keeping this as a sibling class rather than a flag on `CFunction` avoids
putting a branch on the hot path used by every polynomial surrogate, and keeps
the strict `MinMax` schema (and its migration story) intact for them.

#### ONNX Runtime integration

For larger networks, generating C code is impractical.  An alternative is to
embed [ONNX Runtime](https://onnxruntime.ai/) in `libmodena` and load the
trained model from a `.onnx` file at startup.  This decouples inference from
the surrogate compilation pipeline entirely but adds a significant C dependency
and complicates deployment.

#### Key open questions before starting Phase 5

- **Training loop integration** — PyTorch training does not fit naturally into
  the existing `FireTask` / `scipy.optimize` pipeline.  A new
  `NeuralNetFitStrategy` would need to manage epochs, learning rate schedules,
  early stopping, and GPU availability.
- **Out-of-bounds expansion** — the current strategy adds a few points and
  refits.  Retraining a neural network from scratch on each expansion is
  expensive; fine-tuning (warm-start) on the expanded dataset risks
  catastrophic forgetting.
- **Uncertainty quantification** — without UQ (e.g. MC Dropout, deep
  ensembles), the out-of-bounds detector cannot assess prediction confidence,
  which is central to the backward-mapping loop.

---

## Public model archive and portal

> A shared repository where researchers publish, discover, and reuse fitted
> surrogate models — the way PyPI works for Python packages, or the way
> Hugging Face works for machine learning models, but designed around the
> specific needs of multi-scale simulation.

### Motivation

Fitting a surrogate model for a physical sub-process (gas viscosity, foam
conductivity, reaction kinetics) takes significant computational effort:
exact simulations must be run, parameters fitted, validation performed.
Once that work is done, the fitted model is currently locked in a local
MongoDB instance and cannot easily be shared with collaborators or reused
in a different project.

A public archive would allow a researcher to publish a fitted model once and
let others drop it into any MoDeNa simulation without re-running the training
data collection.

---

### What a published model contains

A model entry in the archive is more than just a set of fitted numbers.
It is a self-contained, reproducible artefact:

| Component | Description |
|---|---|
| **C source code** | The surrogate evaluation function (`CFunction.Ccode`), stored as source. The compiled `.so` is platform-specific and not archived — users compile locally on install. |
| **Fitted parameters** | The parameter vector at publication time, with names and bounds. |
| **Input / output specification** | Variable names, physical units, trained bounds. Requires Phase 1 (units) to be complete. |
| **Training data** | The `fitData` collection used to fit the model, enabling independent validation and refitting. |
| **Validation metrics** | Cross-validation error, out-of-sample error on a held-out test set, plot of predicted vs measured. |
| **Dependency graph** | The full substitute-model tree, with each dependency versioned and resolvable. |
| **Model card** | Human-readable description: physical context, applicability range, known limitations, citation, licence. |
| **Workflow snapshot** | The `initModels` and `workflow` scripts that produced this version, making the result fully reproducible. |

---

### Versioning

Models are versioned using semantic versioning (`major.minor.patch`):

- **patch** — re-fit on additional training data; same functional form and variables
- **minor** — new optional input added; existing callers still work unchanged
- **major** — breaking change: input/output renamed, removed, or reordered

The `argPos` system maps directly to this contract: any change to `argPos`
assignments is a major version bump.  Callers pin to a major version; the
archive serves the latest patch within that major.

---

### CLI interface

```bash
# Publish the local 'flowRate' model to the archive
modena publish flowRate --version 1.0.0 --licence CC-BY-4.0

# Search the archive
modena search "gas density"
modena search --input T --input p --output rho

# Install a published model into the local database
modena install idealGas
modena install flowRate@2.1.0          # specific version
modena install flowRate@^2             # latest 2.x

# Inspect
modena list
modena info flowRate
```

`modena install` downloads the model document (parameters, bounds, C source),
compiles the surrogate `.so` locally, and registers the model in the local
MongoDB — exactly as if the user had run `initModels`, but without running
any exact simulations.

**None of this exists yet.**  Note the name clash to resolve first: `modena
install` is already taken — it installs *local model packages* from a directory
into `~/.modena/models`, which is a different operation.  The archive verbs
(`publish`, `search`, `info`) are unclaimed; the current top-level commands are
`fw`, `model`, `init`, `install`, `sweep`, `simulate`, `doctor`, `quickstart`.

---

### Portal pages

The existing local portal (`src/portal/`) already has the core building
blocks: model library table, per-model detail pages (overview, parameters,
I/O bounds, dependency graph, fit data, C code, interactive evaluator), fit
quality and strategy comparison, a sampling panel that can request training
points, a refit panel, an integration-snippet panel, and a runs view with
actions.  The public portal extends this with:

| Page | Description |
|---|---|
| **Browse** | Search and filter the global archive by name, physical quantity, domain (thermodynamics, kinetics, transport, …), input/output variable names, surrogate type, or validation error. |
| **Model card** | Per-model landing page: description, validation plots, dependency graph, C source, fit data download, citation block, and a live *Try it* evaluator that runs the surrogate in the browser. |
| **Workflow gallery** | Published `initModels` + `workflow` script pairs, each linked to the models they produce. A researcher reproducing a literature result can find the workflow here and run it with one command. |
| **Organisation pages** | Groups of models from a research group or project (e.g. PUfoam, CoolProp wrappers). |
| **Comparison** | Side-by-side validation plots for two versions of the same model, or two different models with the same inputs and outputs. |

---

### Authentication and trust

- **Publishing** requires a registered account associated with an ORCID or
  institutional identity to enable citation.
- **Downloading / installing** is open and requires no authentication.
- **Endorsements** — other registered users can mark a model as validated
  against an independent dataset, providing a trust signal analogous to
  download counts or peer review.
- **Licencing** — each model specifies a licence (CC-BY, MIT, etc.) stored
  in the model card.  The CLI can refuse to install models whose licence is
  incompatible with a user-specified policy.

---

### Relationship to the existing portal

| | Local portal | Public portal |
|---|---|---|
| **Audience** | Developer running a local simulation | Community of researchers |
| **Data source** | Local MongoDB | Hosted archive database |
| **Authentication** | Loopback-bound by default; credentials required to expose it | ORCID / institutional login |
| **Editing** | Full — documentation, retrigger fits | Read-only (install to use) |
| **Deployment** | `modena-portal`, localhost | Hosted web service |

The local portal is no longer a sketch: 34 modules under `src/portal/`, with
pages, callbacks and components for the library, per-model detail, evaluator,
diagnostics and runs, plus its own pytest suite wired into ctest as
`modena_portal_unit`.  Feature parity with the CLI was closed in `40e5b09`.
The public portal reuses these components and extends them.

Still thin: there are no Dash callback tests — coverage is `portal/data/` and
`portal/security.py` only.

---

### Open design questions

- **Hosting model** — self-hosted (the MoDeNa project runs one archive) vs
  federated (each group hosts their own, `modena.toml` lists trusted
  registries, similar to Cargo's alternative registries).  Federation avoids
  a single point of failure and lets domain-specific archives emerge.
- **`fitData` storage** — training datasets can be large.  The archive should
  always store metadata and validation metrics, but raw `fitData` could live
  in a separate object store (S3-compatible) with the model card linking to it.
- **Reproducibility of exact simulations** — the compiled binary that generated
  the training data is not portable.  Packaging it as a container image
  alongside the model would make full reproduction possible but significantly
  increases archive size.
- **DOI minting** — models used in publications need persistent identifiers.
  Integration with Zenodo or a similar DOI service would enable proper citation.

---

