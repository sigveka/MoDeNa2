#' @useDynLib modena, .registration = TRUE
NULL

# Status codes live in status_codes.R, generated from
# src/status-codes.cmake at build time.

# Load libmodena at package attach time so the first Modena$new() call does
# not pay the ~100 ms dlopen + Python initialisation cost.
.onLoad <- function(libname, pkgname) {   # nolint: object_name_linter
    tryCatch(
        .Call("r_modena_init"),
        error = function(e) {
            packageStartupMessage(
                "modena: libmodena could not be loaded at package attach.\n",
                "  Error: ", conditionMessage(e), "\n",
                "  Set MODENA_LIB_DIR or ensure ",
                "'python3 -c \"import modena\"' works from this session.\n",
                "  Modena$new() will retry on first use."
            )
        }
    )
}

#' MoDeNa surrogate model interface
#'
#' Reference class wrapping a MoDeNa surrogate model loaded from MongoDB via
#' \code{libmodena}.  Provides the same interface as the Julia and MATLAB
#' wrappers.
#'
#' @section Quick start:
#' \preformatted{
#' library(modena)
#'
#' m      <- Modena$new("flowRate")
#' pos_D  <- m$input_pos("D")
#' pos_q  <- m$output_pos("flowRate")
#' m$check()                        # verify all inputs have been queried
#'
#' t <- 0
#' while (t < t_end) {
#'     t <- t + dt
#'     m$set(pos_D, D)
#'     ret <- m$call()
#'     if (ret == 100L) { t <- t - dt; next }   # surrogate retrained
#'     if (ret != 0L)   stop(paste("MoDeNa exit:", ret))
#'     mdot <- m$output(pos_q)
#'     # use mdot ...
#' }
#' }
#'
#' @section Return codes from \code{$call()}:
#' \describe{
#'   \item{0}{Success — outputs are valid.}
#'   \item{100}{Surrogate retrained mid-run — retry the step; do not quit.}
#'   \item{200}{Out of bounds — FireWorks will re-queue the simulation.}
#'   \item{201}{Model not in database — initialise it from its module.}
#'   \item{202}{Model has no fitted parameters — initialisation needed.}
#' }
#'
#' @export
Modena <- setRefClass(               # nolint: object_name_linter
    "Modena",

    fields = list(
        .model   = "ANY",   # externalptr to modena_model_t
        .inputs  = "ANY",   # externalptr to modena_inputs_t
        .outputs = "ANY"    # externalptr to modena_outputs_t
    ),

    methods = list(

        #' @description Load a surrogate model by its database ID.
        #' @param id Character string matching the model's \code{_id} in MongoDB.
        initialize = function(id) {
            if (!is.character(id) || length(id) != 1L)
                stop("Modena: 'id' must be a single character string.")
            .model   <<- .Call("r_model_new",   id)
            .inputs  <<- .Call("r_inputs_new",  .model)
            .outputs <<- .Call("r_outputs_new", .model)
        },

        #' @description Return the 0-based position index for an input.
        #' @param name Input name as declared in the model definition.
        #' @return Integer position; cache before entering the simulation loop.
        input_pos = function(name) {
            .Call("r_inputs_argPos", .model, as.character(name))
        },

        #' @description Return the 0-based position index for an output.
        #' @param name Output name as declared in the model definition.
        #' @return Integer position.
        output_pos = function(name) {
            .Call("r_outputs_argPos", .model, as.character(name))
        },

        #' @description Verify that every input position has been queried via
        #'   \code{$input_pos()}.  Call once after all \code{$input_pos()} calls
        #'   and before entering the simulation loop.
        check = function() {
            invisible(.Call("r_argPos_check", .model))
        },

        #' @description Set an input value by 0-based position index.
        #' @param pos 0-based integer position returned by \code{$input_pos()}.
        #' @param value Numeric value to assign.
        set = function(pos, value) {
            invisible(.Call("r_inputs_set", .inputs,
                            as.integer(pos), as.double(value)))
        },

        #' @description Get an output value by 0-based position index after a
        #'   successful \code{$call()}.
        #' @param pos 0-based integer position returned by \code{$output_pos()}.
        #' @return Numeric scalar.
        output = function(pos) {
            .Call("r_outputs_get", .outputs, as.integer(pos))
        },

        #' @description Evaluate the surrogate model with the current inputs.
        #' @return Integer return code: 0 = success, 100 = retrained
        #'   (retry in-process), 200 = out of bounds, 201 = model not in
        #'   database, 202 = no fitted parameters.  See docs/return-codes.md.
        call = function() {
            .Call("r_model_call", .model, .inputs, .outputs)
        },

        # ── Metadata ─────────────────────────────────────────────────────── #

        #' @description Number of inputs the model expects.
        inputs_size = function() {
            .Call("r_inputs_size", .model)
        },

        #' @description Number of outputs the model produces.
        outputs_size = function() {
            .Call("r_outputs_size", .model)
        },

        #' @description Number of fitted parameters.
        parameters_size = function() {
            .Call("r_parameters_size", .model)
        },

        #' @description Names of all inputs in positional order.
        #' @return Character vector.
        inputs_names = function() {
            .Call("r_inputs_names", .model)
        },

        #' @description Names of all outputs in positional order.
        #' @return Character vector.
        outputs_names = function() {
            .Call("r_outputs_names", .model)
        },

        #' @description Names of all fitted parameters in positional order.
        #' @return Character vector.
        parameters_names = function() {
            .Call("r_parameters_names", .model)
        },

        #' @description Fitted parameter values as a named numeric vector.
        #'
        #' The R equivalent of Python's ``model.named_parameters()``.  Names
        #' come from the SurrogateFunction's parameter declaration order
        #' (which is the authoritative argPos order post Phase 3).
        #'
        #' @return Named numeric vector, e.g. \code{c(P0 = 0.6134, P1 = 0.6143)}.
        parameters = function() {
            .Call("r_parameters_values", .model)
        },

        #' @description Look up one fitted parameter value by name.
        #' @param name Character; must match a declared parameter.
        #' @return Numeric scalar.
        get_parameter = function(name) {
            vals <- parameters()
            if (!(name %in% names(vals)))
                stop(sprintf(
                    "unknown parameter '%s'; declared parameters are %s",
                    name, paste(names(vals), collapse = ", ")
                ))
            unname(vals[[name]])
        },

        #' @description Print a compact summary of the model.
        show = function() {
            cat(sprintf(
                "<Modena: %d input(s), %d output(s), %d parameter(s)>\n",
                inputs_size(), outputs_size(), parameters_size()
            ))
        }
    )
)
