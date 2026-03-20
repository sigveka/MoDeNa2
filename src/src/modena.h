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

@file modena.h
@brief Public entry point for the MoDeNa C interface library (libmodena).

Include **only** this header in application code.  All other headers
(`model.h`, `function.h`, `indexset.h`, `inputsoutputs.h`, `global.h`) are
internal implementation details and are not installed.

@par What libmodena does

libmodena is a C shared library that lets simulation codes written in C,
C++, Fortran, Julia, or MATLAB evaluate surrogate models stored in a MongoDB
database.  Under the hood it embeds a CPython interpreter and loads the
`modena` Python package at startup.

@par Prerequisites

Before calling any libmodena function:
- A MongoDB instance must be accessible at the URI stored in the environment
  variable `MODENA_URI` (e.g. `mongodb://localhost:27017/modena`).
- The surrogate models must have been initialised with `./initModels` so that
  their documents exist in the database.
- `LD_LIBRARY_PATH` (Linux) or `DYLD_LIBRARY_PATH` (macOS) must include the
  directory containing `libmodena.so`.

@par Three-phase usage pattern

Every adaptor follows the same three phases:

**Phase 1 — Initialisation** (once per model, before the time loop)
~~~~{.c}
modena_model_t   *model   = modena_model_new("flowRate");
modena_inputs_t  *inputs  = modena_inputs_new(model);
modena_outputs_t *outputs = modena_outputs_new(model);

size_t pos_D       = modena_model_inputs_argPos(model, "D");
size_t pos_rho0    = modena_model_inputs_argPos(model, "rho0");
size_t pos_p0      = modena_model_inputs_argPos(model, "p0");
size_t pos_p1Byp0  = modena_model_inputs_argPos(model, "p1Byp0");
size_t pos_mdot    = modena_model_outputs_argPos(model, "flowRate");

modena_model_argPos_check(model);   // terminates if any input was not queried
~~~~

**Phase 2 — Execution** (every time step / iteration)
~~~~{.c}
modena_inputs_set(inputs, pos_D,      D);
modena_inputs_set(inputs, pos_rho0,   rho0);
modena_inputs_set(inputs, pos_p0,     p0);
modena_inputs_set(inputs, pos_p1Byp0, p1 / p0);

int ret = modena_model_call(model, inputs, outputs);

if (ret == 100) { t -= dt; continue; }  // retrained — retry this step
if (ret != 0)   { exit(ret); }          // 200/201 — FireWorks takes over

double mdot = modena_outputs_get(outputs, pos_mdot);
~~~~

**Phase 3 — Cleanup**
~~~~{.c}
modena_inputs_destroy(inputs);
modena_outputs_destroy(outputs);
modena_model_destroy(model);
~~~~

@see modena_model_new(), modena_model_call(), modena_model_destroy()

@author    Henrik Rusche
@copyright 2014-2026, MoDeNa Project. GNU Public License.

@defgroup  C_interface_library MoDeNa C interface library
@brief     Public C API for evaluating MoDeNa surrogate models at runtime.
*/

#ifndef __MODENA_H__
#define __MODENA_H__

#include "global.h"
#include "indexset.h"
#include "function.h"
#include "model.h"

#endif /* __MODENA_H__ */

