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

#include "indexset.h"
#include "structmember.h"
#include "global.h"

extern PyMODINIT_FUNC PyInit_libmodena(void);

PyObject *modena_IndexSet = NULL;

modena_index_set_t *modena_index_set_new
(
    const char *indexSetId
)
{
    // Initialize the Python Interpreter
    if(!Py_IsInitialized())
    {
        Py_Initialize();
    }

    // Initialize this module
    PyInit_libmodena();

    PyObject *args = PyTuple_New(0);
    PyObject *kw = Py_BuildValue("{s:s}", "indexSetId", indexSetId);

    PyObject *pNewObj = PyObject_Call
    (
        (PyObject *) &modena_index_set_tType,
        args,
        kw
    );

    Py_DECREF(args);
    Py_DECREF(kw);
    if(!pNewObj)
    {
        if(PyErr_ExceptionMatches(modena_DoesNotExist))
        {
            PyErr_Clear();

            PyObject *pRet = PyObject_CallMethod
            (
                modena_IndexSet,
                "exceptionLoad",
                "(z)",
                indexSetId
            );
            if(!pRet){ Modena_PyErr_Print(); }
            int ret = PyInt_AsLong(pRet);
            Py_DECREF(pRet);

            modena_error_code = ret;
            return NULL;
        }
        else
        {
            Modena_PyErr_Print();
        }
    }

    return (modena_index_set_t *) pNewObj;
}

size_t modena_index_set_get_index
(
    const modena_index_set_t *self,
    const char* name
)
{
    PyObject *pRet = PyObject_CallMethod
    (
        self->pIndexSet,
        "get_index",
        "(z)",
        name
    );
    if(!pRet){ Modena_PyErr_Print(); }
    size_t ret = PyInt_AsSsize_t(pRet);
    Py_DECREF(pRet);

    return ret;
}

const char* modena_index_set_get_name
(
    const modena_index_set_t *self,
    const size_t index
)
{
    PyObject *pRet = PyObject_CallMethod
    (
        self->pIndexSet,
        "get_name",
        "(i)",
        index
    );
    if(!pRet){ Modena_PyErr_Print(); }
    /* Convert to bytes to get a char* pointer.  PyUnicode_AsEncodedString
     * returns a new reference; we strdup the content and release it so the
     * returned char* is valid beyond this call.  Callers must NOT free it —
     * it lives as long as this index set object is alive (minor controlled
     * leak; one allocation per get_name call). */
    PyObject *pBytes = PyUnicode_AsEncodedString(pRet, "UTF-8", "strict");
    Py_DECREF(pRet);
    const char* ret = strdup(PyBytes_AsString(pBytes));
    Py_DECREF(pBytes);

    return ret;
}

size_t modena_index_set_iterator_start
(
    const modena_index_set_t *self
)
{
    return 0;
}

size_t modena_index_set_iterator_end
(
    const modena_index_set_t *self
)
{
    PyObject *pRet = PyObject_CallMethod
    (
        self->pIndexSet,
        "iterator_end",
        "()"
    );
    if(!pRet){ Modena_PyErr_Print(); }
    size_t ret = PyInt_AsSsize_t(pRet);
    Py_DECREF(pRet);

    return ret;
}

void modena_index_set_destroy(modena_index_set_t *self)
{
    Py_XDECREF(self->pIndexSet);

//    self->ob_type->tp_free((PyObject*)self);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static void modena_index_set_t_dealloc(modena_index_set_t* self)
{
    modena_index_set_destroy(self);
}

static PyMemberDef modena_index_set_t_members[] = {
    {NULL}  /* Sentinel */
};

static PyMethodDef modena_index_set_t_methods[] = {
    {NULL}  /* Sentinel */
};

static int modena_index_set_t_init
(
   modena_index_set_t *self,
   PyObject *args,
   PyObject *kwds
)
{
    PyObject *pIndexSet=NULL;
    char *indexSetId=NULL;

    static char *kwlist[] = {"indexSet", "indexSetId", NULL};

    if
    (
        !PyArg_ParseTupleAndKeywords
        (
            args,
            kwds,
            "|Os",
            kwlist,
            &pIndexSet,
            &indexSetId
        )
    )
    {
        Modena_PyErr_Print();
    }

    if(!pIndexSet)
    {
        self->pIndexSet = PyObject_CallMethod
        (
            modena_IndexSet,
            "load",
            "(z)",
            indexSetId
        );

        if(!self->pIndexSet)
        {
            PyErr_SetString(modena_DoesNotExist, "Index set does not exist");

            Modena_PyErr_Print();
        }
    }
    else
    {
        Py_INCREF(pIndexSet);
        self->pIndexSet = pIndexSet;
    }

    return 0;
}

static PyObject *modena_index_set_t_new
(
    PyTypeObject *type,
    PyObject *args,
    PyObject *kwds
)
{
    modena_index_set_t *self;

    self = (modena_index_set_t *)type->tp_alloc(type, 0);
    if(self)
    {
        self->pIndexSet = NULL;
    }

    return (PyObject *)self;
}

PyDoc_STRVAR(module_doc,
 "modena_index_set_t objects\n"
);

PyTypeObject modena_index_set_tType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name           = "modena.modena_index_set_t",
    .tp_basicsize      = sizeof(modena_index_set_t),
    .tp_itemsize       = 0,
    .tp_dealloc        = (destructor)modena_index_set_t_dealloc,
    .tp_getattr        = 0,
    .tp_setattr        = 0,
    .tp_repr           = 0,
    .tp_as_number      = 0,
    .tp_as_sequence    = 0,
    .tp_as_mapping     = 0,
    .tp_hash           = 0,
    .tp_call           = 0,
    .tp_str            = 0,
    .tp_getattro       = 0,
    .tp_setattro       = 0,
    .tp_as_buffer      = 0,
    .tp_flags          = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_doc            = module_doc,
    .tp_traverse       = 0,
    .tp_clear          = 0,
    .tp_richcompare    = 0,
    .tp_weaklistoffset = 0,
    .tp_iter           = 0,
    .tp_iternext       = 0,
    .tp_methods        = modena_index_set_t_methods,
    .tp_members        = modena_index_set_t_members,
    .tp_getset         = 0,
    .tp_base           = 0,
    .tp_dict           = 0,
    .tp_descr_get      = 0,
    .tp_descr_set      = 0,
    .tp_dictoffset     = 0,
    .tp_init           = (initproc)modena_index_set_t_init,
    .tp_alloc          = 0,
    .tp_new            = modena_index_set_t_new,
    .tp_as_async       = 0,
};

