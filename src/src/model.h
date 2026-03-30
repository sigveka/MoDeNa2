/**
@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2026 MoDeNa Consortium, All rights reserved.

License
    This file is part of Modena.

    The Modena interface library is free software; you can redistribute it
    and/or modify it under the terms of the GNU Lesser General Public License
    as published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.
    
@endcond

@file model.h
@brief Surrogate-model runtime object — `modena_model_t` struct and its API.

This is an **internal** header.  Application code must include only `modena.h`.

`modena_model_t` is the central runtime object in libmodena.  One instance is
created per named surrogate model before the time loop and kept alive until the
simulation ends.

## Relationship to Python

Every `modena_model_t` holds a reference to a MongoEngine `SurrogateModel`
Python object (`self->pModel`).  At construction (`modena_model_new`) the
library:

1. Looks up the model by `_id` in MongoDB via the Python class.
2. Calls `self->pModel.minMax()` to retrieve bounds and parameters (see the
   `modena_model_get_minMax()` hazard note in `src/src/CLAUDE.md`).
3. `dlopen`s the compiled surrogate `.so` and stores a function pointer in
   `self->function`.

## Substitute models

A surrogate model may itself call other surrogate models for sub-quantities
(e.g. a foam-conductivity model that calls a gas-density model internally).
These are stored in the `substituteModels` array.  Each entry owns its own
`inputs` and `outputs` vectors plus index maps that translate between the
outer and inner index spaces.

@author    Henrik Rusche
@copyright 2014-2026, MoDeNa Project. GNU Public License.
*/

#ifndef __MODEL_H__
#define __MODEL_H__

#include "Python.h"
#include <stdbool.h>
#include "function.h"
#include "inputsoutputs.h"

#undef __BEGIN_DECLS
#undef __END_DECLS
#ifdef __cplusplus
# define __BEGIN_DECLS extern "C" {
# define __END_DECLS }
#else
# define __BEGIN_DECLS /* empty */
# define __END_DECLS /* empty */
#endif

__BEGIN_DECLS

extern PyTypeObject modena_model_tType;

extern PyObject *modena_SurrogateModel;

/**
@addtogroup C_interface_library
@{
*/

/**
 * @brief Runtime binding of a substitute (sub-) surrogate model.
 *
 * When a surrogate function needs to evaluate another surrogate internally
 * (e.g. the foam-conductivity function calls a gas-density model), the outer
 * model stores one `modena_substitute_model_t` per sub-model.
 *
 * The `map_inputs` and `map_outputs` arrays translate between the outer
 * model's flat index space and the inner model's index space:
 * @code
 * // Copy outer inputs into substitute's input vector
 * for (size_t k = 0; k < sub->map_inputs_size; ++k)
 *     modena_inputs_set(sm_inputs, k,
 *         modena_inputs_get(outer_inputs, sub->map_inputs[k]));
 * @endcode
 *
 * I/O vectors for the sub-model are **not** stored here; they are allocated
 * per-call inside modena_substitute_model_call() so that multiple threads may
 * invoke modena_model_call() on the same outer model concurrently.
 */
typedef struct modena_substitute_model_t
{
    struct modena_model_t *model;    /**< The substitute surrogate model. */

    size_t map_inputs_size;          /**< Length of @c map_inputs. */

    /** Index map: `map_inputs[i]` is the position in the outer inputs vector
     *  that feeds position @c i of the sub-model's inputs vector. */
    size_t *map_inputs;

    size_t map_outputs_size;         /**< Length of @c map_outputs. */

    /** Index map: `map_outputs[i]` is the position in the outer inputs vector
     *  that receives position @c i of the sub-model's outputs vector. */
    size_t *map_outputs;

} modena_substitute_model_t;

/**
 * @brief Runtime representation of a surrogate model loaded from MongoDB.
 *
 * Allocated by modena_model_new() and freed by modena_model_destroy().
 * All pointer members are owned by the struct; do **not** free them
 * individually.
 *
 * ### Index spaces
 *
 * There are two distinct input index spaces:
 *
 * - **Public** (`inputs_size`): the indices used by callers via
 *   modena_model_inputs_argPos() and modena_inputs_set().  Only the inputs
 *   declared directly in this model's `CFunction` definition.
 * - **Internal** (`inputs_internal_size`): the full flat array passed to the
 *   compiled surrogate `.so`.  It is a superset of the public inputs and
 *   includes positions reserved for inherited (substitute-model) inputs.
 *   Never index into this space from application code.
 *
 * `outputs_size` and `parameters_size` have no such split.
 */
typedef struct modena_model_t
{
    PyObject_HEAD

    PyObject *pModel;          /**< Borrowed reference to the Python `SurrogateModel` object. */

    size_t outputs_size;       /**< Number of scalar outputs. */

    size_t inputs_size;        /**< Number of public (caller-visible) inputs. */

    /** Total input array length passed to the compiled surrogate `.so`,
     *  including inherited positions from substitute models.
     *  Always >= `inputs_size`.  Do not use from application code. */
    size_t inputs_internal_size;

    double *inputs_min;        /**< Lower bounds for each public input (length `inputs_size`). */

    double *inputs_max;        /**< Upper bounds for each public input (length `inputs_size`). */

    /** Parallel to `inputs` — set to `true` by modena_model_inputs_argPos()
     *  and modena_model_outputs_argPos().  modena_model_argPos_check() verifies
     *  every entry is `true`. */
    bool *argPos_used;

    size_t parameters_size;    /**< Number of fitted surrogate parameters. */

    double *parameters;        /**< Current fitted parameter values (length `parameters_size`). */

    struct modena_function_t *mf; /**< Surrogate function metadata (`modena_function_t`). */

    /** Function pointer to the compiled surrogate evaluation function.
     *  Signature matches the C template: `void f(model, inputs, outputs)`.
     *  Populated by modena_model_new() via `dlopen`/`dlsym`. */
    void (*function)
    (
        const struct modena_model_t* model,
        const double* i,
        double *o
    );

    size_t substituteModels_size; /**< Number of substitute (sub-) surrogate models. */

    /** Array of substitute model bindings (length `substituteModels_size`).
     *  Each entry owns its index maps; I/O vectors are allocated per-call. */
    modena_substitute_model_t *substituteModels;

    const char** inputs_names;     /**< Null-terminated array of public input names. */
    const char** outputs_names;    /**< Null-terminated array of output names. */
    const char** parameters_names; /**< Null-terminated array of parameter names. */

} modena_model_t;

/**
 * @brief Function fetching a surrogate model from MongoDB.
 *
 * ### About writing adaptors for surrogate models
 *
 * A adaptor is a code fragment which makes an application able to use the
 * surrogate models (SM) that are stored in the MongoDB database.
 * Writing a adaptor for a SM requires implementation of
 * code fragments that corresponds to the life-span of a surrogate model, which
 * consists of three phases:
 *   * Initialisation
 *     1. Fetch the model from database.
 *     2. Allocate memory for input and output vectors.
 *     3. Query the SM for the position of each individual input and output.
 *   * Execution
 *     1. Set the input vector.
 *     2. Evaluate the surrogate model.
 *     3. Check the MoDeNa framework for errors.
 *     4. Fetch outputs.
 *   * Termination
 *     1. Deallocate memory.
 *
 * ### About
 *
 * The function `modena_model_new` is used in the initialisation phase of the
 * adaptor, and its purpose is to fetch a surrogate model from the database.
 * The input to the function is the name, technically the database "_id", of
 * the surrogate model.
 *
 * When the surrogate model has been fetched from the database the
 * initialisation continues with allocating memory for the input and output
 * vectors. However, this procedure is only performed one time for every
 * surrogate model.
 *
 * ### Usage
 *
 * The function is only called one time for every surrogate model that the user
 * want to employ in a application. It is implemented as a pointer to
 * `modena_model_t` as follows:
 *
 * * C:
 * ~~~~{.c}
 * modena_model_t *model = modena_model_new("MY_MODEL");
 * ~~~~
 * * Fortran:
 * ~~~~{.f90}
 * type(c_ptr) :: model = c_null_ptr
 * model = modena_model_new (c_char_"MY_MODEL"//c_null_char);
 * ~~~~
 * * Python:
 * ~~~~{.py}
 * model = SurrogateModel.load("MY_MODEL")
 * ~~~~
 *
 * #### Important
 *
 * 1. Make sure that the name of the surrogate model is spelled correctly, i.e.
 *    that it corresponds to the "_id" field in the definition of the SM.
 *    ~~~~{.py}
 *        m = BackwardMappingModel(
 *               _id= "MY_MODEL",
 *               surrogateFunction= f,
 *               exactTask= FlowRateExactSim(),
 *               substituteModels= [ ],
 *               initialisationStrategy= Strategy.InitialPoints(),
 *               outOfBoundsStrategy= Strategy.ExtendSpaceStochasticSampling(),
 *               parameterFittingStrategy= Strategy.NonLinFitWithErrorContol(),
 *            )
 *    ~~~~
 *
 * 2. Ensure that the input and output variables are spelled correctly,
 *    according to the surrogate function corresponding to the surrogate model.
 *    ~~~~{.py}
 *        f = CFunction(
 *          Ccode= ''' C-code Omitted ''',
 *          # Global bounds for the function
 *          inputs={
 *              'T': { 'min': -298.15, 'max': 5000.0 },
 *              'P': { 'min':       0, 'max':  100.0 },
 *          },
 *          outputs={
 *               'N': { 'min': 9e99, 'max': -9e99, 'argPos': 0 },
 *          },
 *          parameters={
 *              'param1': { 'min': 0.0, 'max': 10.0, 'argPos': 1 },
 *          },
 *        )
 *    ~~~~
 *
 * 3. Check 1 and 2.
 *
 * ~~~~{.c}
 * modena_model_t *model = modena_model_new("MY_MODEL");    // Fetch "MY_MODEL"
 *
 * modena_inputs_t *inputs = modena_inputs_new(model);        // Allocate input
 * modena_outputs_t *outputs = modena_outputs_new(model);    // Allocate output
 *
 * size_t T_pos = modena_model_inputs_argPos(model, "T"); // Input position "T"
 * size_t P_pos = modena_model_inputs_argPos(model, "P"); // Input position "P"
 * size_t N_pos = modena_model_outputs_argPos(model,"N");// Output position "N"
 *
 * modena_model_argPos_check(model);   // Check all positions have been queried
 * ~~~~
 *
 * The name of the model, here "MY_MODEL", must correspond to the "_id"
 * field in the definition of the surrogate model, which is located in a Python
 * module.
 *
 * #### Common issues:
 *
 * - A common error is to start a simulation without the surrogate model being
 *   located in the database. Check this by executing the line below in a 
 *   terminal (replacing "MY_MODEL" with the name of your surrogate model).
 *
 *   ~~~~{.sh}
 *   mongo --eval 'db.surrogate_model.find({"_id":"MY_MODEL"}).forEach(printjson)'
 *   ~~~~
 *
 * ---
 *
 * @param modelId (char) database '_id' if the desired surrogate model.
 * @return modena_model_t pointer to a surrogate model.
*/
modena_model_t *modena_model_new
(
    const char *modelId
);

/**
 * @brief Return the position of a named input in the input vector.
 *
 * Marks the position as queried (sets the corresponding `argPos_used` flag)
 * so that modena_model_argPos_check() does not flag it as missing.
 * Cache the returned value before the time loop — calling this inside a
 * tight loop adds unnecessary string comparisons.
 *
 * ~~~~{.c}
 * // Initialisation (once)
 * size_t pos_D    = modena_model_inputs_argPos(model, "D");
 * size_t pos_rho0 = modena_model_inputs_argPos(model, "rho0");
 *
 * // Execution (every step)
 * modena_inputs_set(inputs, pos_D,    D);
 * modena_inputs_set(inputs, pos_rho0, rho0);
 * ~~~~
 *
 * @param self  Surrogate model created by modena_model_new().
 * @param name  Name of the input as declared in the Python `CFunction`
 *              `inputs` dict (e.g. `"D"`, `"rho0"`).
 * @return      Zero-based index to pass to modena_inputs_set().
 */
size_t modena_model_inputs_argPos
(
    const modena_model_t *self,
    const char *name
);

/**
 * @brief Verify that every input and output position has been queried.
 *
 * Call this once after all modena_model_inputs_argPos() and
 * modena_model_outputs_argPos() calls, before entering the time loop.
 * It checks the internal `argPos_used` flags and prints a diagnostic message
 * for any input or output whose position was never queried.
 *
 * @warning This function calls `exit(1)` if any position was not queried.
 *          It does **not** return an error code.  Use it only during
 *          initialisation — never inside a time-step loop.
 *
 * ~~~~{.c}
 * size_t pos_D    = modena_model_inputs_argPos(model, "D");
 * size_t pos_mdot = modena_model_outputs_argPos(model, "flowRate");
 * modena_model_argPos_check(model);   // aborts if "rho0", "p0", … were omitted
 * ~~~~
 *
 * @param self  Surrogate model created by modena_model_new().
 */
void modena_model_argPos_check(const modena_model_t *self);

/**
 * @brief Return the position of a named output in the output vector.
 *
 * Marks the position as queried (sets the corresponding `argPos_used` flag)
 * so that modena_model_argPos_check() does not flag it as missing.
 *
 * @param self  Surrogate model created by modena_model_new().
 * @param name  Name of the output as declared in the Python `CFunction`
 *              `outputs` dict (e.g. `"flowRate"`).
 * @return      Zero-based index into the output array returned by
 *              modena_outputs_get().
 */
size_t modena_model_outputs_argPos
(
    const modena_model_t *self,
    const char *name
);

/**
 * @brief Return the array of public input names for a model.
 *
 * The returned pointer points into storage owned by @p self — do not free it.
 * The array has `modena_model_inputs_size(self)` entries.
 *
 * @param self  Surrogate model created by modena_model_new().
 * @return      Pointer to an array of C strings, one per public input.
 */
const char** modena_model_inputs_names
(
    const modena_model_t *self
);

/**
 * @brief Return the array of output names for a model.
 *
 * The returned pointer points into storage owned by @p self — do not free it.
 * The array has `modena_model_outputs_size(self)` entries.
 *
 * @param self  Surrogate model created by modena_model_new().
 * @return      Pointer to an array of C strings, one per output.
 */
const char** modena_model_outputs_names
(
    const modena_model_t *self
);

/**
 * @brief Return the array of parameter names for a model.
 *
 * The returned pointer points into storage owned by @p self — do not free it.
 * The array has `modena_model_parameters_size(self)` entries.
 *
 * @param self  Surrogate model created by modena_model_new().
 * @return      Pointer to an array of C strings, one per fitted parameter.
 */
const char** modena_model_parameters_names
(
    const modena_model_t *self
);

/**
 * @brief Return the number of public inputs for a model.
 * @param self  Surrogate model created by modena_model_new().
 * @return      Number of entries in the public input vector.
 */
size_t modena_model_inputs_size(const modena_model_t *self);

/**
 * @brief Return the number of outputs for a model.
 * @param self  Surrogate model created by modena_model_new().
 * @return      Number of entries in the output vector.
 */
size_t modena_model_outputs_size(const modena_model_t *self);

/**
 * @brief Return the number of fitted parameters for a model.
 * @param self  Surrogate model created by modena_model_new().
 * @return      Number of entries in the parameter vector.
 */
size_t modena_model_parameters_size(const modena_model_t *self);

/**
 * @brief Retrieve the SI unit exponents for a public input slot.
 *
 * @warning **NOT IMPLEMENTED** (Phase 3).  This function is declared but has
 *          no body.  Calling it will produce undefined behaviour.
 *          The `#if 0`-guarded tests in `src/tests/c/test_siunits.c` document
 *          the intended interface.
 *
 * @param self   Surrogate model created by modena_model_new().
 * @param i      Input index (0 … `inputs_size` − 1).
 * @param units  Output: filled with the 6 SI exponents for input @p i.
 */
void modena_model_inputs_siunits
(
    const modena_model_t *self,
    const size_t i,
    modena_siunits_t *units
);

/**
 * @brief Retrieve the SI unit exponents for an output slot.
 *
 * @warning **NOT IMPLEMENTED** (Phase 3).  This function is declared but has
 *          no body.  Calling it will produce undefined behaviour.
 *
 * @param self   Surrogate model created by modena_model_new().
 * @param i      Output index (0 … `outputs_size` − 1).
 * @param units  Output: filled with the 6 SI exponents for output @p i.
 */
void modena_model_outputs_siunits
(
    const modena_model_t *self,
    const size_t i,
    modena_siunits_t *units
);

/**
 * @brief Evaluate the surrogate model and handle out-of-bounds signalling.
 *
 * This is the hot-path function called every time step.  It:
 * 1. Checks all inputs against their trained bounds.
 * 2. If in-bounds: evaluates the compiled surrogate `.so` and returns 0.
 * 3. If out-of-bounds: signals the Python layer, which queues new training
 *    points via FireWorks and may refit or request a process restart.
 *
 * ### Return-code handling
 *
 * | Return | Meaning | Required caller action |
 * |--------|---------|------------------------|
 * | `0`    | Success — outputs are valid. | Read outputs and continue. |
 * | `1`    | Internal failure (Python exception, missing `.so`, etc.). | Call `exit(1)`. |
 * | `100`  | Surrogate was retrained in-process; parameters updated. | Undo the current time step (decrement `t`) and retry. |
 * | `200`  | Out-of-bounds — new training data required; FireWorks will restart this process. | Call `exit(200)`. |
 * | `201`  | Out-of-bounds — new training data required; no restart needed. | Call `exit(201)`. |
 *
 * ~~~~{.c}
 * int ret = modena_model_call(model, inputs, outputs);
 *
 * if (ret == 100) { t -= dt; continue; }   // retrained in-process — retry
 * if (ret != 0)   { exit(ret); }           // 200 / 201 — FireWorks takes over
 *
 * double mdot = modena_outputs_get(outputs, pos_mdot);
 * ~~~~
 *
 * @param model    Surrogate model created by modena_model_new().
 * @param inputs   Input vector filled by modena_inputs_set().
 * @param outputs  Output vector to receive the surrogate results.
 * @return         Status code as described above (0 on success).
 */
int modena_model_call
(
    modena_model_t *model,
    modena_inputs_t *inputs,
    modena_outputs_t *outputs
);

/**
 * @brief Evaluate the surrogate model without checking bounds or return codes.
 *
 * Calls the compiled surrogate `.so` directly, skipping the bounds check
 * and Python signalling.  Used internally by the Python fitting loop
 * (`NonLinFitWithErrorContol`) where bounds checking is intentionally
 * disabled and the call overhead must be minimal.
 *
 * @warning Do **not** use this function in application code.  It bypasses all
 *          error handling.  Use modena_model_call() instead.
 *
 * @param model    Surrogate model created by modena_model_new().
 * @param inputs   Input vector filled by modena_inputs_set().
 * @param outputs  Output vector to receive the surrogate results.
 */
void modena_model_call_no_check
(
    modena_model_t *model,
    modena_inputs_t *inputs,
    modena_outputs_t *outputs
);

/**
 * @brief Free all memory associated with a surrogate model.
 *
 * Releases the `modena_model_t` struct and all sub-arrays it owns
 * (`inputs_min`, `inputs_max`, `argPos_used`, `parameters`, `inputs_names`,
 * `outputs_names`, `parameters_names`, `substituteModels`, …).
 * Also decrements the reference count of the embedded Python object (`pModel`).
 *
 * Do **not** call this while any `modena_inputs_t` or `modena_outputs_t`
 * created from this model is still in use.
 *
 * @param model  Surrogate model to destroy.  Passing `NULL` is a no-op.
 */
void modena_model_destroy(modena_model_t *model);

/** @} */ // end of C_interface_library

__END_DECLS

#endif /* __MODEL_H__ */

