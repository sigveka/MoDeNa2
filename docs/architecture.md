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
instead of 200, triggering a one-time initialisation detour:

```mermaid
sequenceDiagram
    participant App as C application
    participant lib as libmodena
    participant DB  as MongoDB
    participant FW  as FireWorks
    participant py  as modena

    App ->> lib : modena_model_new("flowRate")
    lib ->> DB  : load surrogate + parameters
    DB -->> lib : parameters = [] (not yet fitted)
    lib -->> App : NULL, exit code 202
    App -->> FW  : process exits with code 202

    FW  ->>  py  : handleReturnCode(202)
    py  ->>  DB  : find model with empty parameters
    py  ->>  FW  : build initialisation detour workflow
    FW  ->>  FW  : insert detour, re-queue App after

    Note over FW,py: Detour runs first
    FW  ->>  py  : run exact simulations
    FW  ->>  py  : fit surrogate, save parameters

    Note over FW,App: Original simulation retried
    FW  ->>  App : restart macroscopic solver
    App ->>  lib : modena_model_new("flowRate")
    lib ->>  DB  : load surrogate + parameters
    DB -->>  lib : parameters = [P0, P1] (fitted)
    lib -->> App : model ready
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
| `exit(202)` | application | FireWorks | model has no parameters yet — trigger initialisation detour |
| `minMax()` tuple | Python | C (by position) | input/output bounds and parameter count — positional, do not reorder |
| `argPos` | MongoDB | C arrays | index mapping input/output names → `double[]` array positions |
