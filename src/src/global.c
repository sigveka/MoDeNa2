/*

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
*/

#undef __INLINE_H__
#define __INLINE_H__  /* first, ignore the gsl_inline.h header file */

#undef INLINE_DECL
#define INLINE_DECL       /* disable inline in declarations */

#undef INLINE_FUN
#define INLINE_FUN        /* disable inline in definitions */

#ifndef HAVE_INLINE       /* enable compilation of definitions in .h files */
#define HAVE_INLINE
#endif

#include "global.h"

#ifdef HAVE_INLINE       /* disable compilation of definitions in .h files */
#undef HAVE_INLINE
#endif

#include "indexset.h"
#include "function.h"
#include "model.h"
#include <execinfo.h>

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


// Initialise global variable
thread_local int modena_error_code = 0;

PyObject *modena_DoesNotExist = NULL;
PyObject *modena_OutOfBounds = NULL;
PyObject *modena_ParametersNotValid = NULL;

struct modena_errordesc
{
    int  code;
    const char *message;
} modena_errordesc[] =
{
    { MODENA_SUCCESS, "No error" },
    { MODENA_MODEL_NOT_FOUND, "Surrogate model not found in database" },
    { MODENA_FUNCTION_NOT_FOUND, "Surrogate function not found in database" },
    { MODENA_INDEX_SET_NOT_FOUND, "Index set not found in database" }
};

const char* modena_error_message(int error_code)
{
    if (error_code < 0 || error_code >= MODENA_MODEL_LAST)
        return "Unknown error";
    return modena_errordesc[error_code].message;
};

static PyObject *
test_function(PyObject *self, PyObject *args)
{
    const char *command;
    int sts;

    if (!PyArg_ParseTuple(args, "s", &command))
        return NULL;
    sts = system(command);
    //if (sts < 0) {
    //    PyErr_SetString(SpamError, "System command failed");
    //    return NULL;
    //}
    return PyLong_FromLong(sts);
}

static PyMethodDef module_methods[] = {
    {.ml_name  = "system",
     .ml_meth  = test_function,
     .ml_flags = METH_VARARGS,
     .ml_doc   = "Execute a shell command."}, 
    {NULL, NULL, 0, NULL}  /* Sentinel */
};

#ifndef PyMODINIT_FUNC    /* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif

/*
 * Convenience macros for creating a Python 3 extension module.
 */
#define MOD_ERROR_VAL NULL
#define MOD_SUCCESS_VAL(module) module
#define MOD_INIT(name) PyMODINIT_FUNC PyInit_##name(void)
#define MOD_DEF(ob, name, doc, module_functions) \
      static struct PyModuleDef moduledef = { \
          PyModuleDef_HEAD_INIT, \
          .m_name     = name, \
          .m_doc      = doc, \
          .m_size     = -1, \
          .m_methods  = module_functions, \
          .m_slots    = NULL, \
          .m_traverse = NULL, \
          .m_clear    = NULL, \
          .m_free     = NULL, \
      }; \
      ob = PyModule_Create(&moduledef);

/*
 * Convenience pre-compiler function for adding classes to a module
 */
# define MOD_ADD_OBJECT(module, name, custom_t) \
  Py_INCREF(&custom_t); \
  if ( PyModule_AddObject(module, name, (PyObject *) &custom_t) < 0) { \
    Py_DECREF(&custom_t);\
    Py_DECREF(module);\
    return MOD_ERROR_VAL; \
  }

PyDoc_STRVAR(module_doc,\
 "\
 Module that creates extension types for modena framework.\
 \n\
 class -- modena_model_t\
 ");



typedef struct {
    PyObject_HEAD
    /* Type-specific fields go here. */
} CustomObject;

static PyTypeObject CustomType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "libmodena.Custom",
    .tp_doc = "Custom objects",
    .tp_basicsize = sizeof(CustomObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
};


// Define initialisation function: PyInit_libmodena
MOD_INIT(libmodena)
{
    // Initialize the Python Interpreter
    if(!Py_IsInitialized())
    {
        Py_Initialize();
    }

    if(PyType_Ready(&modena_index_set_tType) < 0)
    {
        return MOD_ERROR_VAL;
    }

    if(PyType_Ready(&modena_function_tType) < 0)
    {
        return MOD_ERROR_VAL;
    }

    if(PyType_Ready(&modena_model_tType) < 0)
    {
        return MOD_ERROR_VAL;
    }

    PyObject* module;
    MOD_DEF(
        module,
        "libmodena",
        module_doc,
        module_methods)

    if(!module)
    {
        return MOD_ERROR_VAL;
    }


        MOD_ADD_OBJECT(module,"modena_index_set_t", modena_index_set_tType)
        MOD_ADD_OBJECT(module,"modena_function_t",  modena_function_tType)
        MOD_ADD_OBJECT(module,"modena_model_t",     modena_model_tType)

    if(!modena_DoesNotExist)
    {
        PyObject *pName;
        pName = PyUnicode_FromString("modena.SurrogateModel");
        if(!pName){ Modena_PyErr_Print(); }

        PyObject *pModule = PyImport_Import(pName);
        Py_DECREF(pName);
        if(!pModule){ Modena_PyErr_Print(); }

        PyObject *pDict = PyModule_GetDict(pModule); // Borrowed ref
        if(!pDict){ Modena_PyErr_Print(); }

        pName = PyUnicode_FromString("IndexSet");
        if(!pName){ Modena_PyErr_Print(); }

        modena_IndexSet = PyObject_GetItem(pDict, pName);
        Py_DECREF(pName);
        if(!modena_IndexSet){ Modena_PyErr_Print(); }

        pName = PyUnicode_FromString("SurrogateFunction");
        if(!pName){ Modena_PyErr_Print(); }

        modena_SurrogateFunction = PyObject_GetItem(pDict, pName);
        Py_DECREF(pName);
        if(!modena_SurrogateFunction){ Modena_PyErr_Print(); }

        pName = PyUnicode_FromString("SurrogateModel");
        if(!pName){ Modena_PyErr_Print(); }

        modena_SurrogateModel = PyObject_GetItem(pDict, pName);
        Py_DECREF(pName);
        if(!modena_SurrogateModel){ Modena_PyErr_Print(); }

        pName = PyUnicode_FromString("DoesNotExist");
        if(!pName){ Modena_PyErr_Print(); }

        modena_DoesNotExist = PyObject_GetItem(pDict, pName);
        Py_DECREF(pName);
        if(!modena_DoesNotExist){ Modena_PyErr_Print(); }

        pName = PyUnicode_FromString("ParametersNotValid");
        if(!pName){ Modena_PyErr_Print(); }

        modena_ParametersNotValid = PyObject_GetItem(pDict, pName);
        Py_DECREF(pName);
        if(!modena_ParametersNotValid){ Modena_PyErr_Print(); }

        pName = PyUnicode_FromString("OutOfBounds");
        if(!pName){ Modena_PyErr_Print(); }

        modena_OutOfBounds = PyObject_GetItem(pDict, pName);
        Py_DECREF(pName);
        if(!modena_OutOfBounds){ Modena_PyErr_Print(); }

        Py_DECREF(pModule);
    }
    return MOD_SUCCESS_VAL(module);

}

// TODO: Support non-Gcc compilers here
PyMODINIT_FUNC PyInit_libmodena(void) __attribute__((constructor));

void modena_print_backtrace()
{
    void* tracePtrs[100];
    int count = backtrace( tracePtrs, 100 );

    char** funcNames = backtrace_symbols( tracePtrs, count );
    // Print the stack trace
    int ii;
    for( ii = 0; ii < count; ii++ )
        printf( "%s\n", funcNames[ii] );

    // Free the string pointers
    free( funcNames );

    exit(1);
}

