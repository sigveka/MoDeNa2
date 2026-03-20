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

@file function.h
@brief Surrogate-function runtime object — `modena_function_t` struct and its API.

This is an **internal** header.  Application code must include only `modena.h`.

A *surrogate function* is a compiled C shared library (`.so`) that evaluates
a polynomial or other analytical approximation of an expensive sub-model.
One `modena_function_t` is created per unique `CFunction` definition and is
shared across all `modena_model_t` instances that reference the same function.

The `.so` is found and opened (`dlopen`) from the path stored in the Python
`SurrogateFunction` document in MongoDB.  The callable entry point is fetched
with `dlsym` and stored in the `function` field.

@author    Henrik Rusche
@copyright 2014-2026, MoDeNa Project. GNU Public License.
*/

#ifndef __FUNCTION_H__
#define __FUNCTION_H__

#include "Python.h"
#include <ltdl.h>
#include "indexset.h"

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

// Forward declaration
struct modena_model_t;

extern PyTypeObject modena_function_tType;

extern PyObject *modena_SurrogateFunction;

/**
@addtogroup C_interface_library
@{
*/

/**
 * @brief Runtime representation of a compiled surrogate function.
 *
 * Allocated by modena_function_new() or modena_function_new_from_model()
 * and freed by modena_function_destroy().
 *
 * The `inputs_size`, `outputs_size`, and `parameters_size` fields mirror the
 * Python `CFunction` definition.  They define the lengths of the `double[]`
 * arrays passed to `function`.
 */
typedef struct modena_function_t
{
    PyObject_HEAD

    PyObject *pFunction;   /**< Reference to the Python `SurrogateFunction` object. */

    size_t inputs_size;    /**< Total input array length (public + inherited). */

    size_t outputs_size;   /**< Number of scalar outputs. */

    size_t parameters_size; /**< Number of fitted parameters. */

    lt_dlhandle handle;    /**< `dlopen` handle for the compiled surrogate `.so`. */

    /** Direct pointer to the surrogate evaluation entry point retrieved via
     *  `dlsym`.  The calling convention matches the C template used by MoDeNa's
     *  Jinja2 code generator:
     *  @code
     *  void my_surrogate(const modena_model_t *model,
     *                    const double *inputs,
     *                    double *outputs);
     *  @endcode */
    void (*function)
    (
        const struct modena_model_t* model,
        const double* i,
        double *o
    );

} modena_function_t;

/**
 * @brief Load a surrogate function from MongoDB by its `_id`.
 *
 * Looks up the `SurrogateFunction` document with `_id == functionId`,
 * opens the compiled `.so` with `dlopen`, and resolves the entry point.
 *
 * @param functionId  Database `_id` of the `SurrogateFunction` document.
 * @return            Newly allocated `modena_function_t`, or `NULL` on error.
 */
modena_function_t *modena_function_new
(
    const char *functionId
);

/**
 * @brief Load the surrogate function referenced by a model.
 *
 * Convenience wrapper around modena_function_new() that extracts the function
 * identifier from the model's Python object rather than requiring the caller
 * to know it.
 *
 * @param self  Surrogate model whose function should be loaded.
 * @return      Newly allocated `modena_function_t`, or `NULL` on error.
 */
modena_function_t *modena_function_new_from_model
(
    const struct modena_model_t *self
);

/**
 * @brief Look up a named index set belonging to this surrogate function.
 *
 * Index sets are used when a surrogate has inputs that range over a discrete
 * set of labels (e.g. chemical species, phase names) rather than a continuous
 * real interval.  The index set maps label strings to integer positions.
 *
 * @param self  Surrogate function containing the index set.
 * @param name  Name of the index set as declared in the Python `CFunction`.
 * @return      Pointer to the `modena_index_set_t`, or `NULL` if not found.
 */
modena_index_set_t *modena_function_get_index_set
(
    const modena_function_t* self,
    const char* name
);

/**
 * @brief Free all memory associated with a surrogate function.
 *
 * Closes the `dlopen` handle and decrements the Python object reference count.
 *
 * @param model  Surrogate function to destroy.  Passing `NULL` is a no-op.
 */
void modena_function_destroy(modena_function_t *model);

/** @} */ // end of C_interface_library

__END_DECLS

#endif /* __FUNCTION_H__ */

