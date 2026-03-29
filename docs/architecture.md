# Architecture — Models and Workflow Manager

## Overview

MoDeNa separates the **runtime call path** (fast, synchronous, in-process)
from the **training loop** (asynchronous, managed by FireWorks).

---

## Runtime call path

```mermaid
sequenceDiagram
    participant App as C/Fortran/Python<br/>application
    participant lib as libmodena
    participant so  as surrogate .so
    participant py  as SurrogateModel<br/>(Python / MongoDB)

    App->>lib: modena_model_new("flowRate")
    lib->>py: load bounds + parameters
    py-->>lib: minMax() tuple, parameter values
    lib-->>App: modena_model_t*

    loop time-step loop
        App->>lib: modena_model_call(model, inputs, outputs)
        lib->>so: evaluate surrogate
        so-->>lib: outputs[]

        alt in bounds
            lib-->>App: return 0 — use outputs
        else out of bounds
            lib-->>App: return 200 — exit process
        end
    end
```

---

## Backward-mapping training loop

When the application exits with code 200, FireWorks takes over.  The full loop
includes three conditional branches that the simplified view omits:

```mermaid
flowchart TD
    A([Application starts]) --> B[modena_model_call]
    B --> C{In bounds?}
    C -- yes --> D[Use surrogate output\ncontinue time loop]
    D --> B

    C -- no --> E[exit 200]
    E --> F[FireWorks detects exit 200]
    F --> G[OutOfBoundsStrategy\nqueues new sim points]

    G --> H1[ExactSim 1]
    G --> H2[ExactSim 2]
    G --> H3[ExactSim N]

    H1 --> sim1{Sim OK?}
    H2 --> sim2{Sim OK?}
    H3 --> sim3{Sim OK?}

    sim1 -- yes --> R[write fitData]
    sim2 -- yes --> R
    sim3 -- yes --> R
    sim1 -- exception --> NC[nonConvergenceStrategy]
    sim2 -- exception --> NC
    sim3 -- exception --> NC

    NC -- SkipPoint --> R
    NC -- FizzleOnFailure --> FIZZLE([Firework FIZZLED\nworkflow stops])
    NC -- DefuseWorkflowOnFailure --> DEFUSE([Workflow defused])

    R --> I[NonLinFitWithErrorContol\nrefit surrogate]
    I --> J{CV error\nacceptable?}
    J -- yes --> L[Refit on all data\nSave parameters to MongoDB]
    J -- no --> K[improveErrorStrategy\nadd more sample points]
    K --> G

    L --> M([Resume application])
    M --> B
```

---

## Auto-initialisation — the 202 protocol

If `./workflow` runs before `./initModels`, the model exists in MongoDB but
has zero fitted parameters.  libmodena detects this and returns exit code 202
instead of 200, triggering a one-time initialisation detour.

### Model identification — the UUID stamp

A naive approach — scanning MongoDB for any model with empty parameters — is
wrong: unrelated models from other projects may also be uninitialised in the
same database.  Instead, `BackwardMappingScriptTask` generates a per-launch
UUID and injects it as `MODENA_LAUNCH_ID` into the subprocess environment.
When `exceptionParametersNotValid` is called inside the subprocess via Python
embedding, it stamps that UUID onto the failing model's document.  The parent
rocket queries by UUID and initialises only that specific model.

```mermaid
sequenceDiagram
    participant bst as BackwardMappingScriptTask
    participant App as C application
    participant lib as libmodena
    participant emb as modena (subprocess)
    participant DB  as MongoDB
    participant FW  as FireWorks

    bst ->> bst : uuid4() → MODENA_LAUNCH_ID
    bst ->> App : ScriptTask — launch subprocess\n(MODENA_LAUNCH_ID in env)

    App ->> lib : modena_model_new("flowRate")
    lib ->> DB  : load surrogate + parameters
    DB -->> lib : parameters = [] (not yet fitted)
    lib ->> emb : exceptionParametersNotValid("flowRate")
    emb ->> DB  : $set flowRate._pending_init_launch_id = UUID
    emb -->> lib : return 202
    lib -->> App : NULL, exit code 202
    App -->> bst : subprocess exits 202

    bst ->> DB  : find where _pending_init_launch_id = UUID
    DB -->> bst : flowRate document
    bst ->> DB  : $unset flowRate._pending_init_launch_id
    bst ->> FW  : FWAction(detours=[init flowRate → resume bst])
    FW  ->>  FW : run init detour — exact sims → fit → save parameters

    Note over FW,bst: Original task retried after detour
    FW  ->> bst : re-run BackwardMappingScriptTask
    bst ->> App : launch subprocess (new UUID in env)
    App ->> lib : modena_model_new("flowRate")
    lib ->> DB  : load surrogate + parameters
    DB -->> lib : parameters = [P0, P1] (fitted)
    lib -->> App : model ready — simulation proceeds
```

### handleReturnCode(202) — precise path vs fallback

When `MODENA_LAUNCH_ID` is set the UUID stamp is used for precise
identification.  If the subprocess crashes before stamping (or is launched
outside `BackwardMappingScriptTask`), a fallback scan is used with a warning.

```mermaid
flowchart TD
    rc([handleReturnCode\nreturnCode = 202])
    lid{launch_id\navailable?}
    qdb[Query MongoDB:\nmodel where\n_pending_init_launch_id = UUID]
    found{model\nfound?}
    clear[Clear UUID marker\nfrom model document]
    precise([ParametersNotValid\nexact model only])
    warn[/WARNING: cannot identify\nexact model — falling back/]
    scan[Scan MongoDB:\nall models where\nparameters = \[\]]
    nomod{any\nfound?}
    term([TerminateWorkflow\ndefuse])
    fallback([ParametersNotValid\nall uninitialized models\nmay include unrelated ones])

    rc --> lid
    lid -- Yes --> qdb --> found
    found -- Yes --> clear --> precise
    found -- No  --> warn
    lid  -- No  --> warn
    warn --> scan --> nomod
    nomod -- Yes --> fallback
    nomod -- No  --> term

    style precise  fill:#388e3c,color:#fff,stroke:#2e7d32
    style fallback fill:#ef6c00,color:#fff,stroke:#e65100
    style term     fill:#c62828,color:#fff,stroke:#b71c1c
    style warn     stroke:#f57c00,stroke-width:2px
```

---

## Initialisation workflow

Before a simulation can run, each `BackwardMappingModel` must be seeded with
training data.  `modena.run(models)` builds this workflow automatically:

```mermaid
flowchart LR
    root([init root]) --> A

    subgraph modelA [flowRate]
        A[InitialPoints\nsample grid] --> B1[ExactSim 1/4]
        A --> B2[ExactSim 2/4]
        A --> B3[ExactSim 3/4]
        A --> B4[ExactSim 4/4]
        B1 & B2 & B3 & B4 --> C[NonLinFitWithErrorContol]
    end

    subgraph modelB [idealGas]
        D[EmptyInit\nno-op]
    end

    root --> D
```

---

## CFunction compilation pipeline

The first time a model is registered (`initModels` or first import), the C
surrogate function is compiled from source and the resulting `.so` path is
cached in MongoDB.  Subsequent runs skip the compilation step entirely.

```mermaid
flowchart TD
    src["User-written C code\n(Ccode= string in CFunction)"]
    hash["SHA-256 hash\nof C source"]
    cached{.so already\ncached in MongoDB?}
    jinja["Jinja2 renders template\ninjects input variable bindings\nconst double x = inputs[0]"]
    write["Write .c + CMakeLists.txt\nto surrogate_lib_dir/func_hash/"]
    cmake["cmake configure + build\nas subprocess"]
    store["Store .so path\nin MongoDB libraryName field"]
    load["dlopen the .so\nstore function pointer\nin modena_model_t"]

    src --> hash --> cached
    cached -- yes --> load
    cached -- no --> jinja --> write --> cmake --> store --> load
```

The `surrogate_lib_dir` is resolved in priority order: `MODENA_SURROGATE_LIB_DIR`
env var → `[surrogate_functions] lib_dir` in `modena.toml` → installed library
directory.  SHA-256 is used (not MD5) because MD5 has known collisions that
could silently reuse the wrong `.so` for a different function.

---

## Component relationships

```mermaid
graph TD
    App["C / Fortran / MATLAB<br/>application"]
    libmodena["libmodena.so<br/>(C runtime)"]
    surrogate_so["surrogate .so<br/>(compiled C function)"]
    MongoDB[("MongoDB")]
    FireWorks["FireWorks<br/>LaunchPad"]
    ExactSim["Exact simulation<br/>executable"]
    Python["modena Python library<br/>(SurrogateModel, Strategy)"]

    App -->|"modena_model_call()"| libmodena
    libmodena -->|"dlopen / call"| surrogate_so
    libmodena -->|"minMax(), parameters"| Python
    Python -->|"MongoEngine read/write"| MongoDB
    FireWorks -->|"stores workflow state"| MongoDB
    FireWorks -->|"launches"| ExactSim
    ExactSim -->|"writes fitData"| MongoDB
    FireWorks -->|"runs"| Python
    Python -->|"NonLinFit → update parameters"| MongoDB
```

---

## Key data flows

| Signal | From | To | Meaning |
|---|---|---|---|
| `return 0` | `libmodena` | application | surrogate evaluated successfully |
| `return 100` | `libmodena` | application | surrogate was just retrained — retry this time step |
| `exit(200)` | application | FireWorks | query was out of bounds — trigger OOB training loop |
| `exit(202)` | application | FireWorks | model has no parameters yet — trigger initialisation detour; failing model identified via `MODENA_LAUNCH_ID` UUID stamped on MongoDB document |
| `minMax()` tuple | Python | C (by position) | input/output bounds and parameter count — positional, do not reorder |
| `argPos` | MongoDB | C arrays | index mapping input/output names → `double[]` array positions |
