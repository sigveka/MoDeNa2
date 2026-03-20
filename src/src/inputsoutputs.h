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

@file inputsoutputs.h
@brief I/O vectors — `modena_inputs_t`, `modena_outputs_t`, and SI unit helpers.

This is an **internal** header.  Application code must include only `modena.h`.

`modena_inputs_t` and `modena_outputs_t` are lightweight structs that wrap
`double[]` arrays used to exchange data with the compiled surrogate `.so`.

### Direct vs inherited inputs

`modena_inputs_t` contains two arrays:

- **`inputs`** — the *public* (caller-visible) inputs set via modena_inputs_set().
  Indexed 0 … `inputs_size − 1`.
- **`inherited_inputs`** — inputs forwarded from the outer model's input vector
  into a substitute model.  Populated internally by modena_model_call(); callers
  should never touch this array directly.  Use modena_inherited_inputs_set() only
  when implementing a custom surrogate wrapper.

All getter/setter functions are defined as `inline` (when the compiler supports
it) to eliminate call overhead in the hot path.

@author    Henrik Rusche
@copyright 2014-2026, MoDeNa Project. GNU Public License.
*/

#include "inline.h"
#include <stddef.h>

#ifndef __INPUTSOUTPUTS_H__
#define __INPUTSOUTPUTS_H__

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

/**
@addtogroup C_interface_library
@{
*/

// Forward declaration
struct modena_model_t;

/**
 * @brief SI unit descriptor for a single physical quantity.
 *
 * Stores the 6 integer exponents of the SI base units in the order:
 * [m, kg, s, A, K, mol].  For example, pressure (Pa = kg·m⁻¹·s⁻²) would be
 * `{-1, 1, -2, 0, 0, 0}`.
 *
 * @note The units API (modena_siunits_get(), modena_model_inputs_siunits(),
 *       modena_model_outputs_siunits()) is **NOT IMPLEMENTED** (Phase 3).
 */
typedef struct
{
    int exponents[6]; /**< SI exponents: [m, kg, s, A, K, mol]. */

} modena_siunits_t;

/**
 * @brief Input data container for a surrogate model evaluation.
 *
 * Allocated by modena_inputs_new() and freed by modena_inputs_destroy().
 * The `inputs` array is indexed 0 … `inputs_size − 1` (public inputs).
 * The `inherited_inputs` array carries values forwarded from the outer model
 * into a substitute model and is managed internally.
 */
typedef struct
{
    double *inputs;           /**< Public input values (length `inputs_size`). */
    double *inherited_inputs; /**< Inherited (substitute-model) inputs — internal use only. */

} modena_inputs_t;

/**
 * @brief Output data container for a surrogate model evaluation.
 *
 * Allocated by modena_outputs_new() and freed by modena_outputs_destroy().
 * The `outputs` array is indexed 0 … `outputs_size − 1`.
 */
typedef struct
{
    double *outputs; /**< Output values (length `outputs_size`). */

} modena_outputs_t;

/**
 * @brief Allocate an SI unit descriptor.
 * @return  Newly allocated `modena_siunits_t` with all exponents zeroed.
 */
modena_siunits_t *modena_siunits_new();

/**
 * @brief Return the SI exponent at position @p i.
 *
 * @warning **NOT IMPLEMENTED** (Phase 3).  This function is declared but has
 *          no body.  Calling it will produce undefined behaviour.
 *
 * @param self  SI unit descriptor.
 * @param i     Base unit index (0=m, 1=kg, 2=s, 3=A, 4=K, 5=mol).
 * @return      Exponent of base unit @p i.
 */
int modena_siunits_get(const modena_siunits_t *self, const size_t i);

/**
 * @brief Free an SI unit descriptor.
 * @param self  Descriptor to destroy.  Passing `NULL` is a no-op.
 */
void modena_siunits_destroy(modena_siunits_t *self);

/**
 * @brief Allocate an input vector sized for the given model.
 *
 * Allocates both the `inputs` and `inherited_inputs` arrays based on the
 * model's `inputs_size` and `inputs_internal_size`.
 *
 * @param self  Model whose input dimensions should be used.
 * @return      Newly allocated `modena_inputs_t`.
 */
modena_inputs_t *modena_inputs_new(const struct modena_model_t *self);

/**
 * @brief Allocate an output vector sized for the given model.
 *
 * @param self  Model whose output dimension should be used.
 * @return      Newly allocated `modena_outputs_t`.
 */
modena_outputs_t *modena_outputs_new(const struct modena_model_t *self);

/**
 * @brief Free an input vector.
 * @param inputs  Vector to destroy.  Passing `NULL` is a no-op.
 */
void modena_inputs_destroy(modena_inputs_t *inputs);

/**
 * @brief Free an output vector.
 * @param outputs  Vector to destroy.  Passing `NULL` is a no-op.
 */
void modena_outputs_destroy(modena_outputs_t *outputs);

/**
 * @brief Set a public input value.
 *
 * ~~~~{.c}
 * modena_inputs_set(inputs, pos_D,    D);
 * modena_inputs_set(inputs, pos_rho0, rho0);
 * ~~~~
 *
 * @param self  Input vector.
 * @param i     Position returned by modena_model_inputs_argPos().
 * @param x     Value to set.
 */
INLINE_DECL void modena_inputs_set(modena_inputs_t *self, const size_t i, double x);

/**
 * @brief Set an inherited input value.
 *
 * Used internally when propagating outer inputs into a substitute model.
 * Do not call this from application code.
 *
 * @param self  Input vector.
 * @param i     Inherited input index.
 * @param x     Value to set.
 */
INLINE_DECL void modena_inherited_inputs_set
(
    modena_inputs_t *self,
    const size_t i,
    double x
);

/**
 * @brief Read back a public input value.
 *
 * @param self  Input vector.
 * @param i     Position returned by modena_model_inputs_argPos().
 * @return      The value previously set by modena_inputs_set().
 */
INLINE_DECL double modena_inputs_get(const modena_inputs_t *self, const size_t i);

/**
 * @brief Read back an inherited input value.
 *
 * Used internally.  Do not call from application code.
 *
 * @param self  Input vector.
 * @param i     Inherited input index.
 * @return      The inherited input value.
 */
INLINE_DECL double modena_inherited_inputs_get
(
    const modena_inputs_t *self,
    const size_t i
);

/**
 * @brief Read a surrogate output after a successful modena_model_call().
 *
 * ~~~~{.c}
 * int ret = modena_model_call(model, inputs, outputs);
 * if (ret == 0)
 *     double mdot = modena_outputs_get(outputs, pos_mdot);
 * ~~~~
 *
 * @param self  Output vector.
 * @param i     Position returned by modena_model_outputs_argPos().
 * @return      Computed surrogate output at position @p i.
 */
INLINE_DECL double modena_outputs_get(const modena_outputs_t *self, const size_t i);

#ifdef HAVE_INLINE

INLINE_FUN void modena_inputs_set(modena_inputs_t *self, const size_t i, double x)
{
    self->inputs[i] = x;
}

INLINE_FUN void modena_inherited_inputs_set
(
    modena_inputs_t *self,
    const size_t i,
    double x
)
{
    self->inherited_inputs[i] = x;
}

INLINE_FUN double modena_inputs_get(const modena_inputs_t *self, const size_t i)
{
    return self->inputs[i];
}

INLINE_FUN double modena_inherited_inputs_get
(
    const modena_inputs_t *self,
    const size_t i
)
{
    return self->inherited_inputs[i];
}

INLINE_FUN double modena_outputs_get(const modena_outputs_t *self, const size_t i)
{
    return self->outputs[i];
}

#endif /* HAVE_INLINE */

/** @} */ // end of C_interface_library

__END_DECLS

#endif /* __INPUTSOUTPUTS_H__ */


