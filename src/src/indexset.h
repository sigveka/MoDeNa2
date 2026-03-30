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

@file indexset.h
@brief Discrete index set — `modena_index_set_t` struct and its API.

This is an **internal** header.  Application code must include only `modena.h`.

An *index set* is an ordered collection of string labels that maps names to
integer positions (and vice versa).  Index sets are used when a surrogate
function has inputs that range over a discrete, named domain — for example, a
multi-component thermodynamic model that accepts a species name such as `"CO2"`
or `"N2"` and maps it to a column index in the property table.

A model that uses an index set declares it in its Python `CFunction` definition.
At runtime the C code:
1. Calls modena_function_get_index_set() to obtain the `modena_index_set_t`.
2. Calls modena_index_set_get_index() to convert a species name to an integer.
3. Passes that integer as a regular (continuous) input to the surrogate.

@author    Henrik Rusche
@copyright 2014-2026, MoDeNa Project. GNU Public License.
*/

#ifndef __INDEXSET_H__
#define __INDEXSET_H__


#include "Python.h"

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

extern PyTypeObject modena_index_set_tType;

extern PyObject *modena_IndexSet;

/**
@addtogroup C_interface_library
@{
*/

/**
 * @brief An ordered set of string labels backed by a Python `IndexSet` document.
 *
 * Allocated by modena_index_set_new() and freed by modena_index_set_destroy().
 * Iteration uses `modena_index_set_iterator_start()` / `_end()` to obtain the
 * valid integer range [start, end).
 */
typedef struct modena_index_set_t
{
    PyObject_HEAD

    PyObject *pIndexSet;  /**< Reference to the Python `IndexSet` document. */
    char     *cached_name; /**< One-entry string cache for modena_index_set_get_name().
                            *   Freed on the next call and in modena_index_set_destroy(). */

} modena_index_set_t;

/**
 * @brief Load an index set from MongoDB by its `_id`.
 *
 * @param indexSetId  Database `_id` of the `IndexSet` document.
 * @return            Newly allocated `modena_index_set_t`, or `NULL` on error.
 */
modena_index_set_t *modena_index_set_new
(
    const char *indexSetId
);

/**
 * @brief Look up the integer index for a label name.
 *
 * ~~~~{.c}
 * modena_index_set_t *is = modena_function_get_index_set(mf, "species");
 * size_t idx = modena_index_set_get_index(is, "CO2");
 * modena_inputs_set(inputs, pos_species, (double)idx);
 * ~~~~
 *
 * @param self  Index set loaded by modena_function_get_index_set().
 * @param name  Label to look up (e.g. `"CO2"`).
 * @return      Integer position of @p name in the index set.
 */
size_t modena_index_set_get_index
(
    const modena_index_set_t *self,
    const char* name
);

/**
 * @brief Return the label at a given integer index.
 *
 * Inverse of modena_index_set_get_index().  The returned string is owned by
 * the index set and valid until the next call to modena_index_set_get_name()
 * or modena_index_set_destroy() — do not free it.
 *
 * @param self   Index set.
 * @param index  Integer position (must be in [start, end)).
 * @return       The label string at position @p index, or `NULL` on error.
 */
const char* modena_index_set_get_name
(
    const modena_index_set_t *self,
    const size_t index
);

/**
 * @brief Return the first valid integer index (inclusive lower bound).
 *
 * Use with modena_index_set_iterator_end() to iterate over all labels:
 * ~~~~{.c}
 * for (size_t i  = modena_index_set_iterator_start(is);
 *           i != modena_index_set_iterator_end(is); ++i)
 * {
 *     printf("%zu: %s\n", i, modena_index_set_get_name(is, i));
 * }
 * ~~~~
 *
 * @param self  Index set.
 * @return      First valid index (typically 0).
 */
size_t modena_index_set_iterator_start
(
    const modena_index_set_t *self
);

/**
 * @brief Return one past the last valid integer index (exclusive upper bound).
 *
 * @param self  Index set.
 * @return      One past the last valid index (i.e. the number of labels).
 */
size_t modena_index_set_iterator_end
(
    const modena_index_set_t *self
);

/**
 * @brief Free all memory associated with an index set.
 *
 * Decrements the Python object reference count and frees the struct.
 *
 * @param indexSet  Index set to destroy.  Passing `NULL` is a no-op.
 */
void modena_index_set_destroy(modena_index_set_t *indexSet);

/** @} */ // end of C_interface_library

__END_DECLS

#endif /* __INDEXSET_H__ */

