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

@file global.h
@brief Global error state, Python 3 compatibility shims, and diagnostic macros.

This is an **internal** header.  Application code must include only `modena.h`.

### Error handling model

libmodena uses a thread-local integer `modena_error_code` to propagate errors
from C back to the caller without exceptions.  The workflow is:

1. A low-level routine detects an error and sets `modena_error_code` to a
   non-zero `modena_error_t` value.
2. modena_error_occurred() returns `true`.
3. The caller retrieves and resets the code with modena_error() and maps it to
   a human-readable string with modena_error_message().

Python exceptions (`modena_DoesNotExist`, `modena_OutOfBounds`,
`modena_ParametersNotValid`) are raised on the Python side and printed via the
`Modena_PyErr_Print()` macro before the error code is set on the C side.

### Python 2 → 3 compatibility shims

The `#define` aliases at the bottom of this header map legacy Py2 names to
their Py3 equivalents.  Py2 is no longer supported; do not add new shims.

@author    Henrik Rusche
@copyright 2014-2026, MoDeNa Project. GNU Public License.
*/

#ifndef __GLOBAL_H__
#define __GLOBAL_H__

#define PY_SSIZE_T_CLEAN
#include "Python.h"
#include "inline.h"
#include <stdbool.h>

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

#ifndef thread_local
# if __STDC_VERSION__ >= 201112 && !defined __STDC_NO_THREADS__
#  define thread_local _Thread_local
# elif defined _WIN32 && ( \
       defined _MSC_VER || \
       defined __ICL || \
       defined __DMC__ || \
       defined __BORLANDC__ )
#  define thread_local __declspec(thread)
/* note that ICC (linux) and Clang are covered by __GNUC__ */
# elif defined __GNUC__ || \
       defined __SUNPRO_C || \
       defined __xlC__
#  define thread_local __thread
# else
#  error "Cannot define thread_local"
# endif
#endif

/** Thread-local error code.  Zero means no error.  Set by internal routines;
 *  read and cleared by modena_error(). */
extern thread_local int modena_error_code;

/** Python exception raised when a model `_id` is not found in MongoDB. */
extern PyObject *modena_DoesNotExist;

/** Python exception raised when an input is outside its trained bounds. */
extern PyObject *modena_OutOfBounds;

/** Python exception raised when the fitted parameters fail validation. */
extern PyObject *modena_ParametersNotValid;

/**
 * @brief Error codes returned by modena_error().
 */
enum modena_error_t
{
    MODENA_SUCCESS            = 0, /**< No error. */
    MODENA_MODEL_NOT_FOUND    = 1, /**< `modena_model_new()` could not find the `_id` in MongoDB. */
    MODENA_FUNCTION_NOT_FOUND = 2, /**< `modena_function_new()` could not find the function. */
    MODENA_INDEX_SET_NOT_FOUND = 3, /**< `modena_index_set_new()` could not find the index set. */
    MODENA_MODEL_LAST              /**< Sentinel — do not use. */
};

/**
 * @brief Return `true` if an error has been set.
 *
 * Does **not** clear the error code.  Use modena_error() to retrieve and
 * reset it.
 *
 * @return `true` if `modena_error_code != MODENA_SUCCESS`.
 */
INLINE_DECL bool modena_error_occurred();

/**
 * @brief Retrieve and clear the current error code.
 *
 * Atomically reads `modena_error_code` and resets it to `MODENA_SUCCESS`.
 * Typical usage:
 * ~~~~{.c}
 * if (modena_error_occurred())
 * {
 *     int code = modena_error();
 *     fprintf(stderr, "modena error: %s\n", modena_error_message(code));
 *     exit(1);
 * }
 * ~~~~
 *
 * @return  The error code that was set, or `MODENA_SUCCESS` if none.
 */
INLINE_DECL int modena_error();

#ifdef HAVE_INLINE

INLINE_FUN bool modena_error_occurred()
{
    return modena_error_code != MODENA_SUCCESS;
}

INLINE_FUN int modena_error()
{
    int ret = modena_error_code;
    modena_error_code = 0;
    return ret;
}

#endif /* HAVE_INLINE */

/**
 * @brief Return a human-readable description for an error code.
 *
 * @param error_code  A `modena_error_t` value.
 * @return            A static C string describing the error (never `NULL`).
 */
const char* modena_error_message(int error_code);

/**
 * @brief Print a C-level stack trace to `stderr`.
 *
 * Called automatically by `Modena_PyErr_Print()` after a Python exception.
 * On platforms without `execinfo.h` this is a no-op.
 */
void modena_print_backtrace();

/* ── C-side log level (mirrors MODENA_LOG_LEVEL on the Python side) ─────── */
/** Log level constant: errors only (default when MODENA_LOG_LEVEL is unset). */
#define MODENA_LOG_WARNING       0
/** Log level constant: normal progress messages. */
#define MODENA_LOG_INFO          1
/** Log level constant: model-loading details, parameter counts, argPos maps. */
#define MODENA_LOG_DEBUG         2
/** Log level constant: per-call input/output value traces. */
#define MODENA_LOG_DEBUG_VERBOSE 3

/** Set once in PyInit_libmodena by reading $MODENA_LOG_LEVEL.
 *  Never written after initialisation.  Defaults to MODENA_LOG_WARNING. */
extern int modena_log_level;

/**
 * @brief Emit a debug message to stderr when MODENA_LOG_LEVEL >= DEBUG.
 *
 * Usage: `Modena_Debug_Print("loaded %zu parameters for '%s'", n, id);`
 * Output (stderr): `[modena DEBUG] loaded 3 parameters for 'flowRate'`
 *
 * Zero cost at WARNING/INFO level — the condition is a single integer
 * comparison against a process-global constant set at startup.
 */
#define Modena_Debug_Print(fmt, ...)                                          \
    do {                                                                      \
        if (modena_log_level >= MODENA_LOG_DEBUG) {                           \
            fprintf(stderr, "[modena DEBUG] " fmt "\n", ##__VA_ARGS__);       \
        }                                                                     \
    } while(0)

/**
 * @brief Like Modena_Debug_Print but only at DEBUG_VERBOSE.
 *
 * Use for per-call traces (e.g. substitute model input/output values) that
 * would be too noisy at DEBUG level in a long simulation.
 *
 * Usage: `Modena_Verbose_Print("i%zu <- ip%zu (%g)", dst, src, val);`
 */
#define Modena_Verbose_Print(fmt, ...)                                        \
    do {                                                                      \
        if (modena_log_level >= MODENA_LOG_DEBUG_VERBOSE) {                   \
            fprintf(stderr, "[modena TRACE] " fmt "\n", ##__VA_ARGS__);       \
        }                                                                     \
    } while(0)

/**
 * @brief Print an informational message with file/line context to `stdout`.
 *
 * Usage: `Modena_Info_Print("loaded model %s", name);`
 * Output: `loaded model flowRate in line 42 of model.c`
 */
#define Modena_Info_Print(...)                                                \
    char Modena_message[256];                                                 \
    sprintf(Modena_message, __VA_ARGS__);                                     \
    fprintf(stdout, "%s in line %i of %s\n", Modena_message,  __LINE__, __FILE__);

/**
 * @brief Print an error message with file/line context to `stderr`.
 *
 * Usage: `Modena_Error_Print("unexpected return %d", ret);`
 */
#define Modena_Error_Print(...)                                               \
    char Modena_message[256];                                                 \
    sprintf(Modena_message, __VA_ARGS__);                                     \
    fprintf(stderr, "%s in line %i of %s\n", Modena_message, __LINE__, __FILE__);

/**
 * @brief Print the active Python exception and a C-level backtrace.
 *
 * Call this after any CPython API returns `NULL` without a more specific
 * error handler.  It calls `PyErr_Print()`, prints a fixed-message line via
 * `Modena_Error_Print`, and then `modena_print_backtrace()`.
 */
#define Modena_PyErr_Print()                                                  \
    PyErr_Print();                                                            \
    Modena_Error_Print("Error in python catched");                            \
    modena_print_backtrace();

/** @name Python 2 → 3 compatibility shims
 *
 * Python 3 is the only supported version.  These macros map legacy Py2 names
 * to their Py3 equivalents so that old call sites compile without modification.
 * Do **not** add new shims — Py2 is no longer supported.
 * @{ */
#define PyInt_FromLong      PyLong_FromLong   /**< Py3: `PyLong_FromLong` */
#define PyInt_AsLong        PyLong_AsLong     /**< Py3: `PyLong_AsLong` */
#define PyInt_AsSize_t      PyLong_AsSize_t   /**< Py3: `PyLong_AsSize_t` */
#define PyInt_AsSsize_t     PyLong_AsSize_t   /**< Py3: `PyLong_AsSize_t` */
#define PyString_AsString   PyBytes_AsString  /**< Py3: `PyBytes_AsString` */
#define PyString_Check      PyBytes_Check     /**< Py3: `PyBytes_Check` */
#define PyString_FromString PyBytes_FromString /**< Py3: `PyBytes_FromString` */
/** @} */


__END_DECLS

#endif /* __GLOBAL_H__ */

