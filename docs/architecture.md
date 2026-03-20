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

When the application exits with code 200, FireWorks takes over:

```mermaid
flowchart TD
    A([Application starts]) --> B[modena_model_call]
    B --> C{In bounds?}
    C -- yes --> D[Use surrogate output\ncontinue time loop]
    D --> B
    C -- no --> E[exit 200]

    E --> F[FireWorks detects\nexit code 200]
    F --> G[OutOfBoundsStrategy\nqueues new sim points]
    G --> H1[ExactSim 1]
    G --> H2[ExactSim 2]
    G --> H3[ExactSim N]
    H1 & H2 & H3 --> I[NonLinFitWithErrorContol\nrefit surrogate]
    I --> J{Error\nacceptable?}
    J -- no --> K[StochasticSampling\nadd more points]
    K --> H1
    J -- yes --> L[Save parameters\nto MongoDB]
    L --> M([Resume application\nnew Firework])
    M --> B
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
| `return 100` | `libmodena` | application | surrogate was just retrained — retry this step |
| `exit(200)` | application | FireWorks | query was out of bounds — trigger OOB loop |
| `minMax()` tuple | Python | C (by position) | input/output bounds and parameter count |
| `argPos` | MongoDB | C arrays | index mapping input/output names → array positions |
