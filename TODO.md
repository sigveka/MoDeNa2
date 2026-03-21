# TODO

Planned work and known limitations for MoDeNa 2.x.

---

## Near-term

### In-place surrogate parameter update

**File:** `src/src/model.c`, `src/python/Strategy.py`

During surrogate fitting, the optimizer calls `modena_model_new()` on every
iteration to evaluate the surrogate at a candidate parameter vector.  This
allocates and immediately discards a full `modena_model_t` struct per call.

The fix is to add a parameter-update function to the C API:

```c
/* model.h */
void modena_model_set_parameters(
    modena_model_t *model,
    const double   *parameters,
    size_t          n
);
```

The Python binding would expose this as `modena_model_t.set_parameters(list)`,
allowing `NonLinFitWithErrorContol._fit()` to reuse a single C struct across
all optimizer iterations instead of reconstructing it each time.

---

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

A C-level integration test that loads a known model, calls `minMax()`, and
asserts the correct values at each tuple position would catch any future
accidental reordering.

---

### Parallel cross-validation folds

**File:** `src/python/Strategy.py`

The cross-validation loop in `NonLinFitWithErrorContol` runs folds sequentially.
Parallelising with `ProcessPoolExecutor` is the natural fix, but is currently
blocked because `modena_model_t` (the C struct wrapper) is not picklable and
cannot be sent to worker processes.

The fix requires restructuring `_fit()` to accept only plain serialisable data
(parameter bounds, `fitData` arrays) and re-initialise `modena_model_t` inside
each worker.  This is also a prerequisite for making data-driven surrogate types
(Phase 4) practical — GP and neural network fitting is expensive enough that
sequential folds would be prohibitively slow.

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
Parallel CV folds (above) should be completed first.*

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

*Further out.  Parallel CV folds and Phase 4 linear methods should land first.*

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

---

### Portal pages

The existing local portal (`src/portal/`) already has the core building
blocks: model library table, per-model detail pages (overview, parameters,
I/O bounds, dependency graph, fit data, C code, interactive evaluator), and
a runs view.  The public portal extends this with:

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
| **Authentication** | None | ORCID / institutional login |
| **Editing** | Full — documentation, retrigger fits | Read-only (install to use) |
| **Deployment** | `modena-portal`, localhost | Hosted web service |

The local portal is partially implemented.  The public portal reuses its
components and extends them.

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

