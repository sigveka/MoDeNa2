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

#include "model.h"
#include "structmember.h"
#include "global.h"

PyObject *modena_SurrogateModel = NULL;

void modena_substitute_model_calculate_maps
(
    modena_substitute_model_t *sm,
    modena_model_t *parent
)
{
    PyObject *pMaps = PyObject_CallMethod
    (
        parent->pModel, "calculate_maps", "(O)", sm->model->pModel
    );
    if(!pMaps){ Modena_PyErr_Print(); return; }

    if(PyTuple_Size(pMaps) < 2)
    {
        Modena_Error_Print("calculate_maps returned a tuple with fewer than 2 elements");
        Py_DECREF(pMaps);
        return;
    }

    PyObject *pMapOutputs = PyTuple_GET_ITEM(pMaps, 0); // Borrowed ref
    PyObject *pSeq = PySequence_Fast(pMapOutputs, "expected a sequence");
    if(!pSeq){ Py_DECREF(pMaps); Modena_PyErr_Print(); return; }
    sm->map_outputs_size = PySequence_Size(pMapOutputs);
    sm->map_outputs = malloc(sm->map_outputs_size*sizeof(size_t));

    size_t i;
    for(i = 0; i < sm->map_outputs_size; i++)
    {
        sm->map_outputs[i] = PyLong_AsSsize_t(PyList_GET_ITEM(pSeq, i));
    }
    sm->map_outputs_size /= 2;
    Py_DECREF(pSeq);
    /* pMapOutputs is a borrowed ref from PyTuple_GET_ITEM — do NOT Py_DECREF */
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    PyObject *pMapInputs = PyTuple_GET_ITEM(pMaps, 1); // Borrowed ref
    pSeq = PySequence_Fast(pMapInputs, "expected a sequence");
    if(!pSeq){ Py_DECREF(pMaps); Modena_PyErr_Print(); return; }
    sm->map_inputs_size = PySequence_Size(pMapInputs);
    sm->map_inputs = malloc(sm->map_inputs_size*sizeof(size_t));
    for(i = 0; i < sm->map_inputs_size; i++)
    {
        sm->map_inputs[i] = PyLong_AsSsize_t(PyList_GET_ITEM(pSeq, i));
    }
    sm->map_inputs_size /= 2;
    Py_DECREF(pSeq);
    /* pMapInputs is a borrowed ref from PyTuple_GET_ITEM — do NOT Py_DECREF */
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    Py_DECREF(pMaps);
}

bool modena_model_read_substituteModels(modena_model_t *self)
{
     // Modena_Info_Print("In %s", __func__);

    PyObject *pSubstituteModels = PyObject_GetAttrString
    (
        self->pModel, "substituteModels"
    );
    if(!pSubstituteModels){ Modena_PyErr_Print(); return false; }

    PyObject *pSeq = PySequence_Fast
    (
        pSubstituteModels, "expected a sequence"
    );
    if(!pSeq){ Py_DECREF(pSubstituteModels); Modena_PyErr_Print(); return false; }
    self->substituteModels_size = PySequence_Size(pSubstituteModels);
    self->substituteModels =
        malloc(self->substituteModels_size*sizeof(modena_substitute_model_t));
    size_t i;
    for(i = 0; i < self->substituteModels_size; i++)
    {
        PyObject *args = PyTuple_New(0);
        PyObject *kw = Py_BuildValue
        (
            "{s:O}", "model", PyList_GET_ITEM(pSeq, i)
        );

        self->substituteModels[i].model = (modena_model_t *) PyObject_Call
        (
            (PyObject *) &modena_model_tType,
            args,
            kw
        );
        Py_DECREF(args);
        Py_DECREF(kw);

        if(!self->substituteModels[i].model)
        {
            if
            (
                PyErr_ExceptionMatches(modena_DoesNotExist)
             || PyErr_ExceptionMatches(modena_ParametersNotValid)
            )
            {
                PyObject *pModelId =
                    PyObject_GetAttrString(PyList_GET_ITEM(pSeq, i), "_id");
                if(!pModelId){ Modena_PyErr_Print(); }
                PyObject *pModelIdBytes = PyUnicode_AsEncodedString(pModelId, "UTF-8", "strict");
                Py_DECREF(pModelId);
                if(!pModelIdBytes){ Modena_PyErr_Print(); }
                const char* modelId = PyBytes_AsString(pModelIdBytes);

                PyObject *pRet = NULL;
                if
                (
                    PyErr_ExceptionMatches(modena_DoesNotExist)
                )
                {
                    fprintf
                    (
                        stderr,
                        "Loading model %s failed - Attempting automatic initialisation\n",
                        modelId
                    );

                    pRet = PyObject_CallMethod
                    (
                        modena_SurrogateModel,
                        "exceptionLoad",
                        "(z)",
                        modelId
                    );
                }
                else
                {
                    fprintf
                    (
                        stderr,
                        "Parameters of model %s are invalid - Trying to initialise\n",
                        modelId
                    );

                    pRet = PyObject_CallMethod
                    (
                        modena_SurrogateModel,
                        "exceptionParametersNotValid",
                        "(z)",
                        modelId
                    );
                }

                if(!pRet)
                {
                    Py_DECREF(pModelIdBytes);
                    Py_DECREF(pSeq);
                    Py_DECREF(pSubstituteModels);
                    Modena_PyErr_Print();
                    return false;
                }
                int ret = PyLong_AsLong(pRet);
                Py_DECREF(pRet);

                modena_error_code = ret;

                Py_DECREF(pModelIdBytes);
                Py_DECREF(pSeq);
                Py_DECREF(pSubstituteModels);

                return false;
            }
            else
            {
                Modena_PyErr_Print();
                return false;
            }
        }

        modena_substitute_model_calculate_maps
        (
            &self->substituteModels[i],
            self
        );
    }

    Py_DECREF(pSeq);
    Py_DECREF(pSubstituteModels);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    return true;
}

void modena_model_get_minMax
(
    modena_model_t *self
)
{
    PyObject *pObj = PyObject_CallMethod(self->pModel, "minMax", NULL);
    if(!pObj){ Modena_PyErr_Print(); return; }

    PyObject *pMin = PyTuple_GET_ITEM(pObj, 0); // Borrowed ref
    PyObject *pSeq = PySequence_Fast(pMin, "expected a sequence");
    self->inputs_internal_size = PySequence_Size(pSeq);
    self->inputs_min = malloc(self->inputs_internal_size*sizeof(double));
    size_t i;
    for(i = 0; i < self->inputs_internal_size; i++)
    {
        self->inputs_min[i] = PyFloat_AsDouble(PyList_GET_ITEM(pSeq, i));
    }
    Py_DECREF(pSeq);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    PyObject *pMax = PyTuple_GET_ITEM(pObj, 1); // Borrowed ref
    pSeq = PySequence_Fast(pMax, "expected a sequence");
    self->inputs_max = malloc(self->inputs_internal_size*sizeof(double));
    for(i = 0; i < self->inputs_internal_size; i++)
    {
        self->inputs_max[i] = PyFloat_AsDouble(PyList_GET_ITEM(pSeq, i));
    }
    Py_DECREF(pSeq);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    PyObject *pinames = PyTuple_GET_ITEM(pObj, 2); // Borrowed ref
    pSeq = PySequence_Fast(pinames, "expected a sequence");
    self->inputs_size = PySequence_Size(pSeq);
    self->inputs_names = malloc(self->inputs_size*sizeof(char*));
    for(i = 0; i < self->inputs_size; i++)
    {
        PyObject *pBytes = PyUnicode_AsEncodedString(
            PyList_GET_ITEM(pSeq, i), "UTF-8", "strict");
        self->inputs_names[i] = strdup(PyBytes_AsString(pBytes));
        Py_DECREF(pBytes);
    }
    Py_DECREF(pSeq);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    PyObject *ponames = PyTuple_GET_ITEM(pObj, 3); // Borrowed ref
    pSeq = PySequence_Fast(ponames, "expected a sequence");
    self->outputs_size = PySequence_Size(pSeq);
    self->outputs_names = malloc(self->outputs_size*sizeof(char*));
    for(i = 0; i < self->outputs_size; i++)
    {
        PyObject *pBytes = PyUnicode_AsEncodedString(
            PyList_GET_ITEM(pSeq, i), "UTF-8", "strict");
        self->outputs_names[i] = strdup(PyBytes_AsString(pBytes));
        Py_DECREF(pBytes);
    }
    Py_DECREF(pSeq);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    PyObject *ppnames = PyTuple_GET_ITEM(pObj, 4); // Borrowed ref
    pSeq = PySequence_Fast(ppnames, "expected a sequence");
    self->parameters_size = PySequence_Size(pSeq);
    self->parameters_names = malloc(self->parameters_size*sizeof(char*));
    for(i = 0; i < self->parameters_size; i++)
    {
        PyObject *pBytes = PyUnicode_AsEncodedString(
            PyList_GET_ITEM(pSeq, i), "UTF-8", "strict");
        self->parameters_names[i] = strdup(PyBytes_AsString(pBytes));
        Py_DECREF(pBytes);
    }
    Py_DECREF(pSeq);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    Py_DECREF(pObj);
}

modena_model_t *modena_model_new
(
    const char *modelId
)
{
    Modena_Debug_Print("modena_model_new: loading model '%s'", modelId);

    PyObject *args = PyTuple_New(0);
    PyObject *kw = Py_BuildValue("{s:s}", "modelId", modelId);

    PyObject *pNewObj = PyObject_Call
    (
        (PyObject *) &modena_model_tType,
        args,
        kw
    );

    Py_DECREF(args);
    Py_DECREF(kw);
    if( !pNewObj )
    {
        if
        (
            PyErr_ExceptionMatches(modena_DoesNotExist)
         || PyErr_ExceptionMatches(modena_ParametersNotValid)
        )
        {
            //PyErr_Print();

            PyObject *pRet = NULL;
            if
            (
                PyErr_ExceptionMatches(modena_DoesNotExist)
            )
            {
                PyErr_Clear();
                fprintf
                (
                    stderr,
                    "Loading model %s failed - "
                    "Attempting automatic initialisation\n",
                    modelId
                );

                pRet = PyObject_CallMethod
                (
                    modena_SurrogateModel,
                    "exceptionLoad",
                    "(z)",
                    modelId
                );
            }
            else
            {
                PyErr_Clear();
                fprintf
                (
                    stderr,
                    "Parameters of model %s are invalid - "
                    "Trying to initialise\n",
                    modelId
                );

                pRet = PyObject_CallMethod
                (
                    modena_SurrogateModel,
                    "exceptionParametersNotValid",
                    "(z)",
                    modelId
                );
            }

            if(!pRet){ Modena_PyErr_Print(); }
            int ret = PyLong_AsLong(pRet);
            Py_DECREF(pRet);

            modena_error_code = ret;
            return NULL;
        }
        else
        {
            Modena_PyErr_Print();
        }
    }

    return (modena_model_t *) pNewObj;
}

size_t modena_model_inputs_argPos(const modena_model_t *self, const char *name)
{
    PyObject *pRet = PyObject_CallMethod
    (
        self->pModel,
        "inputs_argPos",
        "(z)",
        name
    );
    if(!pRet){ Modena_PyErr_Print(); }
    size_t argPos = PyLong_AsSsize_t(pRet);
    Py_DECREF(pRet);

    if(self->argPos_used)
    {
        //Modena_Info_Print
        //(
        //    "Mark argPos %zu as used from inputs_argPos\n",
        //    argPos
        //);
        self->argPos_used[argPos] = true;
    }

    return argPos;
}

size_t modena_model_outputs_argPos(const modena_model_t *self, const char *name)
{
    PyObject *pRet = PyObject_CallMethod
    (
        self->pModel,
        "outputs_argPos",
        "(z)",
        name
    );
    if(!pRet){ Modena_PyErr_Print(); }
    size_t ret = PyLong_AsSsize_t(pRet);
    Py_DECREF(pRet);

    return ret;
}

void modena_model_argPos_check(const modena_model_t *self)
{
    bool allUsed = true;
    size_t j;

    for(j = 0; j < self->inputs_internal_size; j++)
    {
        if(self->argPos_used[j]){ continue; }

        /* Accept positions that are filled automatically by a substitute model.
         * The framework calls modena_substitute_model_call() before the outer
         * surrogate, which writes substitute outputs into these slots — the C
         * application never sets them and should not have to. */
        bool covered = false;
        size_t s, k;
        for(s = 0; s < self->substituteModels_size && !covered; s++)
        {
            const modena_substitute_model_t *sm = &self->substituteModels[s];
            for(k = 0; k < sm->map_outputs_size && !covered; k++)
            {
                if(sm->map_outputs[2*k+1] == j){ covered = true; }
            }
        }

        if(!covered)
        {
            fprintf(stderr, "argPos %zu not used\n", j);
            allUsed = false;
            break;
        }
    }

    if(!allUsed)
    {
        fprintf(stderr, "Not all input arguments used - Exiting\n");
        exit(1);
    }

    /* All Python-calling setup is now complete.  Release the GIL so that
     * spawned worker threads (pthreads, OpenMP) can acquire it on demand
     * via PyGILState_Ensure when an out-of-bounds event needs Python.
     * Only done when libmodena owns the interpreter (pure-C embedding); in
     * a Python-app context the caller manages the GIL. */
    if(modena_owns_python && !modena_main_thread_state && PyGILState_Check())
    {
        modena_main_thread_state = PyEval_SaveThread();
    }
}

const char** modena_model_inputs_names(const modena_model_t *self)
{
    return self->inputs_names;
}

const char** modena_model_outputs_names(const modena_model_t *self)
{
    return self->outputs_names;
}

const char** modena_model_parameters_names(const modena_model_t *self)
{
    return self->parameters_names;
}

size_t modena_model_inputs_size(const modena_model_t *self)
{
    return self->inputs_size;
}

size_t modena_model_outputs_size(const modena_model_t *self)
{
    return self->outputs_size;
}

size_t modena_model_parameters_size(const modena_model_t *self)
{
    return self->parameters_size;
}

int modena_substitute_model_call
(
    const modena_substitute_model_t *sm,
    const modena_model_t *parent,
    modena_inputs_t *inputs
)
{
    Modena_Debug_Print("modena_substitute_model_call: running substitute model");

    /* Allocate per-call I/O so this function is safe to call concurrently
     * from multiple threads on the same substitute model struct. */
    modena_inputs_t  *sm_inputs  = modena_inputs_new(sm->model);
    modena_outputs_t *sm_outputs = modena_outputs_new(sm->model);

    size_t j;
    for(j = 0; j < sm->map_inputs_size; j++)
    {
        Modena_Verbose_Print(
            "  sub-input  i%zu <- parent[%zu]  (%g)",
            sm->map_inputs[2*j+1],
            sm->map_inputs[2*j],
            inputs->inputs[sm->map_inputs[2*j]]
        );
        sm_inputs->inputs[sm->map_inputs[2*j+1]] =
            inputs->inputs[sm->map_inputs[2*j]];
    }

    int ret = modena_model_call(sm->model, sm_inputs, sm_outputs);

    if(!ret)
    {
        for(j = 0; j < sm->map_outputs_size; j++)
        {
            Modena_Verbose_Print(
                "  sub-output parent[%zu] <- o%zu  (%g)",
                sm->map_outputs[2*j+1],
                sm->map_outputs[2*j],
                sm_outputs->outputs[sm->map_outputs[2*j]]
            );
            inputs->inputs[sm->map_outputs[2*j+1]] =
                sm_outputs->outputs[sm->map_outputs[2*j]];
        }
    }

    modena_inputs_destroy(sm_inputs);
    modena_outputs_destroy(sm_outputs);

    return ret;
}

int write_outside_point
(
    modena_model_t *self,
    modena_inputs_t *inputs
)
{
    /* This function calls into CPython. Acquire the GIL so it is safe to
     * call from worker threads that do not already hold it. */
    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject* pOutside = PyList_New(self->inputs_internal_size);

    size_t j;
    for(j = 0; j < self->inputs_internal_size; j++)
    {
        PyObject *pVal = PyFloat_FromDouble(inputs->inputs[j]);
        if(!pVal)
        {
            Py_DECREF(pOutside);
            Modena_PyErr_Print();
            PyGILState_Release(gstate);
            modena_error_code = 1;
            return 1;
        }
        PyList_SET_ITEM(pOutside, j, pVal);
    }

    PyObject *pRet = PyObject_CallMethod
    (
       self->pModel,
       "exceptionOutOfBounds",
       "(O)",
       pOutside
    );
    Py_DECREF(pOutside);
    if(!pRet){ Modena_PyErr_Print(); }
    int ret = PyLong_AsLong(pRet);
    Py_DECREF(pRet);

    PyGILState_Release(gstate);

    modena_error_code = ret;

    return ret;
}

/*
modena_model_call returns:

201: requesting exit for new DOE without Restart
200: requesting exit for new DOE with Restart
100: updated model parameters, requesting to continue this run
1: failure
0: okay

If exit is requested, do what's necessary and exit with the same error code!

*/
int modena_model_call
(
    modena_model_t *self,
    modena_inputs_t *inputs,
    modena_outputs_t *outputs
)
{
    /* Release the GIL for the pure-C evaluation path so that multi-threaded
     * callers (pthreads, OpenMP, MPI+OpenMP) do not need to call
     * Py_BEGIN_ALLOW_THREADS themselves.  We only release if this thread
     * currently holds the GIL — worker threads in a pthread/OpenMP pool
     * typically do not hold it, so PyGILState_Check() returns 0 and this
     * becomes a no-op.  write_outside_point() re-acquires via
     * PyGILState_Ensure/Release when an OOB event requires Python. */
    int gil_held = PyGILState_Check();
    PyThreadState *_save = NULL;
    if(gil_held) { _save = PyEval_SaveThread(); }

    Modena_Debug_Print("modena_model_call: evaluating model (parameters_size=%zu)", self->parameters_size);

    int retval = 0;

    if
    (
          self->parameters_size == 0
       && self->parameters_size != self->mf->parameters_size
    )
    {
        retval = write_outside_point(self, inputs);
        goto done;
    }

    size_t j;
    for(j = 0; j < self->substituteModels_size; j++)
    {
        int ret = modena_substitute_model_call
        (
            &self->substituteModels[j],
            self,
            inputs
        );
        if(ret){ retval = ret; goto done; }
    }

    for(j = 0; j < self->inputs_internal_size; j++)
    {
        if
        (
            inputs->inputs[j] < self->inputs_min[j]
         || inputs->inputs[j] > self->inputs_max[j]
        )
        {
            retval = write_outside_point(self, inputs);
            goto done;
        }
    }

    self->function
    (
        self,
        inputs->inputs,
        outputs->outputs
    );

done:
    if(gil_held) { PyEval_RestoreThread(_save); }
    return retval;
}

void modena_model_call_no_check
(
    modena_model_t *self,
    modena_inputs_t *inputs,
    modena_outputs_t *outputs
)
{
    //Modena_Info_Print("In %s", __func__);

    if
    (
          self->parameters_size == 0
       && self->parameters_size != self->mf->parameters_size
    )
    {
        write_outside_point(self, inputs);
    }

    size_t j;
    for(j = 0; j < self->substituteModels_size; j++)
    {
        modena_substitute_model_call
        (
            &self->substituteModels[j],
            self,
            inputs
        );
    }

    /*
    for(j = 0; j < self->inputs_internal_size; j++)
    {
        printf
        (
            "j = %zu %g\n",
            j,
            inputs->inputs[j]
        );
    }
    */

    self->function
    (
        self,
        inputs->inputs,
        outputs->outputs
    );
}

/* Destructor, frees the memory block occupied by a model.
 */
void modena_model_destroy(modena_model_t *self)
{
    /* Re-acquire the GIL if argPos_check released it.  Only the first call
     * restores it; subsequent calls (e.g. recursive substitute-model destroy)
     * find modena_main_thread_state == NULL and skip this. */
    if(modena_main_thread_state)
    {
        PyEval_RestoreThread(modena_main_thread_state);
        modena_main_thread_state = NULL;
    }

    size_t i;
    for(i = 0; i < self->substituteModels_size; i++)
    {
        Py_XDECREF(self->substituteModels[i].model);
        free(self->substituteModels[i].map_inputs);
        free(self->substituteModels[i].map_outputs);
    }
    free(self->substituteModels);

    free(self->parameters);
    free(self->inputs_min);
    free(self->inputs_max);

    free(self->argPos_used);

    if(self->mf)
    {
        modena_function_destroy(self->mf);
    }

    for(i = 0; i < self->inputs_size; i++)
    {
        free((char*)self->inputs_names[i]);
    }
    free(self->inputs_names);

    for(i = 0; i < self->outputs_size; i++)
    {
        free((char*)self->outputs_names[i]);
    }
    free(self->outputs_names);

    for(i = 0; i < self->parameters_size; i++)
    {
        free((char*)self->parameters_names[i]);
    }
    free(self->parameters_names);

    Py_XDECREF(self->pModel);

    //self->ob_type->tp_free((PyObject*)self);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

/* C-Python: Destructor, exposed as __del__ in Python
 */
static void modena_model_t_dealloc(modena_model_t* self)
{
    modena_model_destroy(self);
}

/* C-Python: Member-Table
 *
 * Structure which describes an attribute of a type which corresponds to a C 
 * struct member. Its fields are:
 *
 * Field  C Type       Meaning
 * ------ ----------  --------------------------------------------------------
 * name   char *      name of the member
 * type   int         the type of the member in the C struct
 * offset Py_ssize_t  the offset in bytes that the member is located on the
 *                    type's object struct
 * flags  int         flag bits indicating if the field should be read-only or 
 *                    writable
 * doc    char *      points to the contents of the docstring
 */
static PyMemberDef modena_model_t_members[] = {
    { .name   = "outputs_size",
      .type   = T_PYSSIZET,
      .offset = offsetof(modena_model_t, outputs_size),
      .flags  = READONLY, 
      .doc    = "number of putputs"},
    {"inputs_size", T_PYSSIZET,
      offsetof(modena_model_t, inputs_size), READONLY , "number of inputs"},
    {"parameters_size", T_PYSSIZET,
      offsetof(modena_model_t, parameters_size), READONLY , "number of parameters"},
    {NULL}  /* Sentinel */
};

/* C-Python: Method exposed in Python as __call__
 *
 * TODO: The method is also exposed as "call", but this should be deprecated
 */
static PyObject *modena_model_t_call
(
    modena_model_t* self,
    PyObject *args,
    PyObject *kwds
)
{
    // Modena_Info_Print("In %s", __func__);

    PyObject *pI=NULL, *pCheckBounds=NULL;
    bool checkBounds = true;

    static char *kwlist[] = { "inputs", "checkBounds", NULL };

    if
    (
        !PyArg_ParseTupleAndKeywords
        (
            args,
            kwds,
            "O|O",
            kwlist,
            &pI,
            &pCheckBounds
        )
    )
    {
        Modena_PyErr_Print();
    }

    if(pCheckBounds)
    {
        checkBounds = PyObject_IsTrue(pCheckBounds);
    }

    if(!PyList_Check(pI))
    {
        PyErr_SetString(PyExc_TypeError, "First argument is not a list");
        return NULL;
    }

    PyObject *pSeq = PySequence_Fast(pI, "expected a sequence");
    size_t len = PySequence_Size(pI);

    if(len != self->inputs_internal_size)
    {
        Py_DECREF(pSeq);
        PyErr_Format(PyExc_ValueError,
            "input array has incorrect size %zu (expected %zu)",
            len, self->inputs_internal_size);
        return NULL;
    }

    modena_inputs_t *inputs = modena_inputs_new(self);

    size_t j;
    for(j = 0; j < len; j++)
    {
        modena_inputs_set
        (
            inputs, j, PyFloat_AsDouble(PyList_GET_ITEM(pSeq, j))
        );
    }
    Py_DECREF(pSeq);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    modena_outputs_t *outputs = modena_outputs_new(self);

    if(checkBounds)
    {
        if(modena_model_call(self, inputs, outputs))
        {
            modena_inputs_destroy(inputs);
            modena_outputs_destroy(outputs);

            PyObject *pExcArgs = Py_BuildValue(
                "(sO)",
                "Surrogate model is used out-of-bounds",
                self->pModel
            );
            if(pExcArgs)
            {
                PyObject *pExcInst =
                    PyObject_Call(modena_OutOfBounds, pExcArgs, NULL);
                Py_DECREF(pExcArgs);
                if(pExcInst)
                {
                    PyErr_SetObject(modena_OutOfBounds, pExcInst);
                    Py_DECREF(pExcInst);
                }
            }

            return NULL;
        }
    }
    else
    {
        modena_model_call_no_check(self, inputs, outputs);
    }

    PyObject* pOutputs = PyList_New(self->outputs_size);
    for(j = 0; j < self->outputs_size; j++)
    {
        PyObject *pVal = PyFloat_FromDouble(modena_outputs_get(outputs, j));
        if(!pVal)
        {
            Py_DECREF(pOutputs);
            modena_inputs_destroy(inputs);
            modena_outputs_destroy(outputs);
            Modena_PyErr_Print();
            return NULL;
        }
        PyList_SET_ITEM(pOutputs, j, pVal);
    }

    modena_inputs_destroy(inputs);
    modena_outputs_destroy(outputs);

    return pOutputs;
}

/* C-Python: Method-Table
 *
 * Structure used to describe a method of an extension type. This structure has
 * four fields:
 *
 * Field     C Type       Meaning
 * -------   -----------  ----------------------------------------------------
 * ml_name   char *       name of the method
 * ml_meth   PyCFunction  pointer to the C implementation
 * ml_flags  int          flag bits indicating how the call is constructed
 * ml_doc    char *       points to the contents of the docstring
 *
 *
 * [online doc]: https://docs.python.org/2/c-api/structures.html#c.PyMethodDef
 */
 PyMethodDef modena_model_t_methods[] = {
    {
      .ml_name  = "call",
      .ml_meth  = (PyCFunction) modena_model_t_call,
      .ml_flags = METH_VARARGS | METH_KEYWORDS,
      .ml_doc   = "Call surrogate model and return outputs"
    },
    {NULL}  /* Sentinel */
};

/**
 */
PyObject*
modena_model_t_get_parameters(modena_model_t *self, void *closure)
{
    PyObject* pParams = PyList_New(self->parameters_size);
    size_t i;
    for(i = 0; i < self->parameters_size; i++)
    {
        PyObject *pVal = PyFloat_FromDouble(self->parameters[i]);
        if(!pVal)
        {
            Py_DECREF(pParams);
            return NULL;
        }
        PyList_SET_ITEM(pParams, i, pVal);
    }
    return pParams;
}

/**
 */
static int
modena_model_t_set_parameters(modena_model_t *self, PyObject *value, void *closure)
{
    // @TODO: Error checks for the following cases:
    //       1. len(value) == self->parameters_size
    //       2. type(value) == list or tuple
    //       3. value != NULL

    if(self->parameters_size != PySequence_Size(value))
    {
        PyErr_Format(PyExc_ValueError,
            "Wrong number of parameters: got %zd, expected %zu",
            PySequence_Size(value), self->parameters_size);
        return -1;
    }

    /*if (value == NULL)
    {
          PyErr_SetString(PyExc_TypeError, "Cannot delete parameter values");
          return -1;
    }
    if (! PyBytes_Check(value)) {
          PyErr_SetString(PyExc_TypeError, "First attribute must be a string");
          return -1;
    }*/

    size_t i;
    for(i = 0; i < self->parameters_size; i++)
    {
        PyObject *pItem = PyList_GetItem(value, i);
        if(!pItem) { return -1; }
        self->parameters[i] = PyFloat_AsDouble(pItem);
        if(PyErr_Occurred()) { return -1; }
    }

    // PyErr_SetString(PyExc_TypeError, "Attribute is read-only!");
    return 0;
}

/* C-Python
 */
static PyGetSetDef modena_model_t_getset[] = {
    {.name    = "parameters",
     .get     = (getter)modena_model_t_get_parameters,
     .set     = (setter)modena_model_t_set_parameters,
     .doc     = "parameters",
     .closure =  NULL},
    {NULL} /* Sentinel */
};

/* C-Python: Initialiser, exposed in Python as the method: __new__
 *
 * Return -1 upon failure, 0 on success.
 *
 */
static int modena_model_t_init
(
    modena_model_t *self,
    PyObject *args,
    PyObject *kwds
)
{
    PyObject *pParameters=NULL, *pModel=NULL;
    char *modelId=NULL;
    size_t i, j;

    static char *kwlist[] = {"model", "modelId", "parameters", NULL};

    if
    (
        !PyArg_ParseTupleAndKeywords
        (
            args,
            kwds,
            "|OsO",
            kwlist,
            &pModel,
            &modelId,
            &pParameters
        )
    )
    {
        Modena_PyErr_Print();
    }

    if(!pModel)
    {
        self->pModel = PyObject_CallMethod
        (
            modena_SurrogateModel,
            "load",
            "(z)",
            modelId
        );

        if( !self->pModel )
        {
            PyErr_SetString
            (
                modena_DoesNotExist,
                "Surrogate model does not exist"
            ); 
            return -1;
        }
    }
    else
    {
        Py_INCREF(pModel);
        self->pModel = pModel;
    }

    //PyObject_Print(self->pModel, stdout, 0);
    //printf("\n");

    // Avoiding double indirection in modena_model_call
    // Use modena_function_new to construct, then copy function pointer
    self->mf = modena_function_new_from_model(self);
    self->function = self->mf->function;

    modena_model_get_minMax(self);

    PyObject *pOutputs = PyObject_GetAttrString(self->pModel, "outputs");
    if(!pOutputs){ Modena_PyErr_Print(); }
    self->outputs_size = PyDict_Size(pOutputs);
    Py_DECREF(pOutputs);

    if(!modena_model_read_substituteModels(self))
    {
        return -1;
    }

    self->argPos_used = malloc(self->inputs_internal_size*sizeof(bool));

    for(j = 0; j < self->inputs_internal_size; j++)
    {
        self->argPos_used[j] = false;
    }

    for(j = 0; j < self->substituteModels_size; j++)
    {
        modena_substitute_model_t *sm = &self->substituteModels[j];
        for(i = 0; i < sm->map_outputs_size; i++)
        {
            //printf("Mark argPos %zu as used\n", sm->map_outputs[2*i+1]);
            self->argPos_used[sm->map_outputs[2*i+1]] = true;
        }
    }

    if(!pParameters)
    {
        pParameters = PyObject_GetAttrString(self->pModel, "parameters");
        if(!pParameters){ Modena_PyErr_Print(); }
    }
    else
    {
        Py_INCREF(pParameters);
    }

    PyObject *pSeq = PySequence_Fast(pParameters, "expected a sequence");
    if
    (
          self->parameters_size == 0
        && self->parameters_size != self->mf->parameters_size
        // || self->parameters_size != self->mf->parameters_size
    )
    {
        PyObject *args = PyTuple_New(2);
        if(!args){ Py_DECREF(pSeq); Py_DECREF(pParameters); Modena_PyErr_Print(); return -1; }

        PyObject* str = PyUnicode_FromString
        (
            "Surrogate model does not have valid parameters"
        );
        if(!str){ Py_DECREF(args); Py_DECREF(pSeq); Py_DECREF(pParameters); Modena_PyErr_Print(); return -1; }

        PyTuple_SET_ITEM(args, 0, str);
        Py_INCREF(self->pModel);
        PyTuple_SET_ITEM(args, 1, self->pModel);

        PyErr_SetObject
        (
            modena_ParametersNotValid,
            args
        );
        Py_DECREF(args);

        Py_DECREF(pSeq);
        Py_DECREF(pParameters);
        return -1;
    }

    if(self->parameters_size != PySequence_Size(pParameters))
    {
        Modena_Debug_Print(
            "Wrong number of parameters in '%s'. Requires %zu -- Given %zu",
            modelId ? modelId : "(unknown)",
            self->parameters_size,
            (size_t)PySequence_Size(pParameters)
        );
        PyObject *excArgs = PyTuple_New(2);
        if(!excArgs){ Py_DECREF(pSeq); Py_DECREF(pParameters); Modena_PyErr_Print(); return -1; }

        PyObject *excStr = PyUnicode_FromString("Surrogate model does not have valid parameters");
        if(!excStr){ Py_DECREF(excArgs); Py_DECREF(pSeq); Py_DECREF(pParameters); Modena_PyErr_Print(); return -1; }

        PyTuple_SET_ITEM(excArgs, 0, excStr);
        Py_INCREF(self->pModel);
        PyTuple_SET_ITEM(excArgs, 1, self->pModel);

        PyErr_SetObject(modena_ParametersNotValid, excArgs);
        Py_DECREF(excArgs);

        Py_DECREF(pSeq);
        Py_DECREF(pParameters);
        return -1;
    }

    self->parameters = malloc(self->parameters_size*sizeof(double));
    for(i = 0; i < self->parameters_size; i++)
    {
        self->parameters[i] = PyFloat_AsDouble(PyList_GET_ITEM(pSeq, i));
    }

    Py_DECREF(pSeq);
    Py_DECREF(pParameters);
    if(PyErr_Occurred()){ Modena_PyErr_Print(); }

    return 0;
}

/* C-Python: Constructor, exposed in Python as the method: __new__
 */
static PyObject * modena_model_t_new
(
    PyTypeObject *type,
    PyObject *args,
    PyObject *kwds
)
{
    // Modena_Info_Print("In '%s'", __func__);
    modena_model_t *self;

    self = (modena_model_t *)type->tp_alloc(type, 0);
    if( self != NULL)
    {
        // Set everything to zero
        self->pModel = NULL;
        self->outputs_size = 0;
        self->inputs_size = 0;
        self->inputs_internal_size = 0;
        self->inputs_min = NULL;
        self->inputs_max = NULL;
        self->argPos_used = NULL;
        self->parameters_size = 0;
        self->parameters = NULL;
        self->mf = NULL;
        self->function = NULL;
        self->substituteModels_size = 0;
        self->substituteModels = NULL;
        /* Initialise name arrays to NULL so modena_model_destroy() can safely
         * call free() on them even when modena_model_t_init() fails before
         * modena_model_get_minMax() populates them. */
        self->inputs_names     = NULL;
        self->outputs_names    = NULL;
        self->parameters_names = NULL;
    }
    return (PyObject *)self;
}

/**
 * @brief  Documentation of modena_model_t class
*/
PyDoc_STRVAR(class_doc,
 "modena_model_t objects\n"
);

/* C-Python: The C structure used to describe the modena_model type.
 */
PyTypeObject modena_model_tType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name           = "modena.modena_model_t",
    .tp_basicsize      = sizeof(modena_model_t),
    .tp_itemsize       = 0,
    .tp_dealloc        = (destructor)modena_model_t_dealloc,
    .tp_getattr        = 0,
    .tp_setattr        = 0,
    .tp_repr           = 0,
    .tp_as_number      = 0,
    .tp_as_sequence    = 0,
    .tp_as_mapping     = 0,
    .tp_hash           = 0,
    .tp_call           = (ternaryfunc)modena_model_t_call,
    .tp_str            = 0,
    .tp_getattro       = 0,
    .tp_setattro       = 0,
    .tp_as_buffer      = 0,
    .tp_flags          = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_doc            = class_doc,
    .tp_traverse       = 0,
    .tp_clear          = 0,
    .tp_richcompare    = 0,
    .tp_weaklistoffset = 0,
    .tp_iter           = 0,
    .tp_iternext       = 0,
    .tp_methods        = modena_model_t_methods,
    .tp_members        = modena_model_t_members,
    .tp_getset         = modena_model_t_getset,
    .tp_base           = 0,
    .tp_dict           = 0,
    .tp_descr_get      = 0,
    .tp_descr_set      = 0,
    .tp_dictoffset     = 0,
    .tp_init           = (initproc)modena_model_t_init,
    .tp_alloc          = 0,
    .tp_new            = modena_model_t_new,
    .tp_as_async       = 0,
};
// vim: filetype=c fileencoding=utf-8 syntax=on colorcolumn=79
// vim: ff=unix tabstop=4 softtabstop=0 expandtab shiftwidth=4 smarttab
// vim: nospell spelllang=en_us
