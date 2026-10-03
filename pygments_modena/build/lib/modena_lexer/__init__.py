"""
Custom Pygments lexers for MoDeNa documentation.

Extends the standard C and Python lexers to highlight MoDeNa-specific
API functions, types, and classes in a distinct colour.

Usage in MkDocs markdown:

    ```modena-c
    modena_model_t *m = modena_model_new("flowRate");
    modena_model_call(m, inputs, outputs);
    ```

    ```modena-python
    m = BackwardMappingModel(_id='flowRate', ...)
    modena.run([m])
    ```
"""

from pygments.lexers.c_cpp import CLexer
from pygments.lexers.python import Python3Lexer
from pygments.token import Name, Keyword

# ── C API ────────────────────────────────────────────────────────────────────

MODENA_C_FUNCTIONS = frozenset({
    # Lifecycle
    "modena_initialize",
    "modena_model_new",
    "modena_model_delete",
    # Evaluation
    "modena_model_call",
    # Inputs / outputs allocation
    "modena_inputs_new",
    "modena_outputs_new",
    "modena_inputs_destroy",
    "modena_outputs_destroy",
    # Accessor helpers
    "modena_inputs_set",
    "modena_outputs_get",
    # ArgPos lookup
    "modena_model_argPos",
    "modena_model_argPos_check",
    # Introspection
    "modena_model_nInputs",
    "modena_model_nOutputs",
    "modena_model_nParameters",
})

MODENA_C_TYPES = frozenset({
    "modena_model_t",
    "modena_inputs_t",
    "modena_outputs_t",
})


class ModenaCLexer(CLexer):
    """C lexer with MoDeNa API functions and types highlighted."""

    name = "MoDeNa C"
    aliases = ["modena-c"]
    filenames = []

    def get_tokens_unprocessed(self, text):
        for index, token, value in super().get_tokens_unprocessed(text):
            if token is Name and value in MODENA_C_FUNCTIONS:
                yield index, Name.Function, value
            elif token is Name and value in MODENA_C_TYPES:
                yield index, Keyword.Type, value
            else:
                yield index, token, value


# ── Python API ───────────────────────────────────────────────────────────────

MODENA_PYTHON_CLASSES = frozenset({
    # Model types
    "BackwardMappingModel",
    "ForwardMappingModel",
    "SurrogateModel",
    "CFunction",
    # Fitting strategies
    "NonLinFitWithErrorContol",
    "StochasticSampling",
    "EmptyInitialisationStrategy",
    # Samplers
    "LatinHypercube",
    "Halton",
    "Sobol",
    "RandomUniform",
    # Cross-validation
    "Holdout",
    "KFold",
    "LeaveOneOut",
    "LeavePOut",
    "Jackknife",
    # Non-convergence strategies
    "SkipPoint",
    "FizzleOnFailure",
    "DefuseWorkflowOnFailure",
    # Acceptance / error metrics
    "MaxError",
    "AbsoluteError",
    "RelativeError",
    "NormalizedError",
    # Optimizers
    "TrustRegionReflective",
    "LevenbergMarquardt",
    "DogBox",
    # Launchpad / tasks
    "ModenaLaunchPad",
    "BackwardMappingScriptTask",
    # FireWorks primitives (used in modena context)
    "Firework",
    "Workflow",
})

MODENA_PYTHON_FUNCTIONS = frozenset({
    "run",
    "lpad",
    "load",
    "configure_logging",
})


class ModenaPythonLexer(Python3Lexer):
    """Python lexer with MoDeNa classes and top-level functions highlighted."""

    name = "MoDeNa Python"
    aliases = ["modena-python"]
    filenames = []

    def get_tokens_unprocessed(self, text):
        for index, token, value in super().get_tokens_unprocessed(text):
            if token in (Name, Name.Other) and value in MODENA_PYTHON_CLASSES:
                yield index, Name.Class, value
            else:
                yield index, token, value
