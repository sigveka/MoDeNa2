/*
 * modena_gateway.c — MEX/OCT gateway to libmodena for MATLAB and Octave.
 *
 * All operations are dispatched through a single entry point:
 *
 *   ptr  = modena_gateway('model_new',        modelId)
 *   iptr = modena_gateway('inputs_new',        ptr)
 *   optr = modena_gateway('outputs_new',       ptr)
 *          modena_gateway('model_destroy',     ptr, iptr, optr)
 *   pos  = modena_gateway('input_pos',         ptr, name)
 *   pos  = modena_gateway('output_pos',        ptr, name)
 *          modena_gateway('argpos_check',      ptr)
 *          modena_gateway('inputs_set',        iptr, pos, value)
 *   val  = modena_gateway('outputs_get',       optr, pos)
 *   code = modena_gateway('model_call',        ptr, iptr, optr)
 *   n    = modena_gateway('inputs_size',       ptr)
 *   n    = modena_gateway('outputs_size',      ptr)
 *   n    = modena_gateway('parameters_size',   ptr)
 *   c    = modena_gateway('inputs_names',      ptr)
 *   c    = modena_gateway('outputs_names',     ptr)
 *   c    = modena_gateway('parameters_names',  ptr)
 *
 * Pointer handles are uint64 scalars.  Positions are 0-based doubles.
 *
 * Design note — runtime dlopen and model destruction
 * ────────────────────────────────────────────────────
 * libmodena.so embeds a Python extension whose constructor (triggered by
 * dlopen) calls Py_Initialize() and then PyImport_Import("modena").
 * For Python extension modules like _bz2 to resolve Python symbols, libpython
 * must be in the *global* symbol namespace (RTLD_GLOBAL).  When libmodena.so
 * is loaded as a DT_NEEDED dependency the linker uses RTLD_LOCAL by default,
 * which breaks extension loading.  We therefore:
 *   1. Explicitly dlopen libpython with RTLD_GLOBAL before loading libmodena.
 *   2. Set PYTHONPATH so the embedded Python finds the modena package.
 *   3. dlopen libmodena with RTLD_GLOBAL.
 * The library is never explicitly closed; the OS reclaims it on process exit.
 *
 * modena_model_t is a Python extension type (PyObject_HEAD).  Its destructor,
 * modena_model_destroy(), doubles as tp_dealloc.  Calling it directly would
 * free the memory block while ob_refcnt is still 1; Py_Finalize() at process
 * exit may then access the freed block and segfault.  Instead, model_destroy
 * calls Py_DecRef() (resolved from the global namespace) which lets Python's
 * own reference-counting machinery invoke tp_dealloc at the correct time.
 * modena_inputs_t and modena_outputs_t are plain C structs; their destroy
 * functions are called directly as before.
 */

#include "mex.h"
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── Opaque types ────────────────────────────────────────────────────────── */
typedef struct modena_model_t_   modena_model_t;
typedef struct modena_inputs_t_  modena_inputs_t;
typedef struct modena_outputs_t_ modena_outputs_t;

/* ── Function pointer types ──────────────────────────────────────────────── */
typedef modena_model_t*   (*fp_model_new_t)      (const char *);
typedef modena_inputs_t*  (*fp_inputs_new_t)     (const modena_model_t *);
typedef modena_outputs_t* (*fp_outputs_new_t)    (const modena_model_t *);
typedef void              (*fp_inputs_destroy_t) (modena_inputs_t *);
typedef void              (*fp_outputs_destroy_t)(modena_outputs_t *);
/* Py_DecRef — the C-API function (non-macro) that decrements the Python
 * reference count of a PyObject.  When the count reaches zero Python's
 * tp_dealloc is called, which is the correct and only safe way to free a
 * modena_model_t (a Python extension type).                               */
typedef void              (*fp_Py_DecRef_t)      (void *);
typedef size_t (*fp_inputs_argPos_t) (const modena_model_t *, const char *);
typedef size_t (*fp_outputs_argPos_t)(const modena_model_t *, const char *);
typedef void   (*fp_argPos_check_t)  (const modena_model_t *);
typedef void   (*fp_inputs_set_t)    (modena_inputs_t *, size_t, double);
typedef double (*fp_outputs_get_t)   (const modena_outputs_t *, size_t);
typedef int    (*fp_model_call_t)    (modena_model_t *,
                                      modena_inputs_t *,
                                      modena_outputs_t *);
typedef size_t       (*fp_inputs_size_t)      (const modena_model_t *);
typedef size_t       (*fp_outputs_size_t)     (const modena_model_t *);
typedef size_t       (*fp_parameters_size_t)  (const modena_model_t *);
typedef const char** (*fp_inputs_names_t)     (const modena_model_t *);
typedef const char** (*fp_outputs_names_t)    (const modena_model_t *);
typedef const char** (*fp_parameters_names_t) (const modena_model_t *);

/* ── Static library handle and resolved symbols ──────────────────────────── */
static void *_lib = NULL;

static fp_model_new_t       p_model_new;
static fp_Py_DecRef_t       p_Py_DecRef;   /* replaces direct model_destroy */
static fp_inputs_new_t      p_inputs_new;
static fp_outputs_new_t     p_outputs_new;
static fp_inputs_destroy_t  p_inputs_destroy;
static fp_outputs_destroy_t p_outputs_destroy;
static fp_inputs_argPos_t   p_inputs_argPos;
static fp_outputs_argPos_t  p_outputs_argPos;
static fp_argPos_check_t    p_argPos_check;
static fp_inputs_set_t      p_inputs_set;
static fp_outputs_get_t     p_outputs_get;
static fp_model_call_t      p_model_call;
static fp_inputs_size_t      p_inputs_size;
static fp_outputs_size_t     p_outputs_size;
static fp_parameters_size_t  p_parameters_size;
static fp_inputs_names_t     p_inputs_names;
static fp_outputs_names_t    p_outputs_names;
static fp_parameters_names_t p_parameters_names;

/* ── Helper: last non-empty line of a popen() command ───────────────────── */
static int popen_last_line(const char *cmd, char *buf, size_t bufsz)
{
    FILE *fp = popen(cmd, "r");
    if (!fp) return 0;
    char line[4096];
    buf[0] = '\0';
    while (fgets(line, sizeof(line), fp)) {
        size_t n = strlen(line);
        while (n > 0 && ((unsigned char)line[n-1] <= ' ')) n--;
        if (n > 0 && n < bufsz) { memcpy(buf, line, n); buf[n] = '\0'; }
    }
    pclose(fp);
    return buf[0] != '\0';
}

/* ── Helper: pointer <-> uint64 scalar mxArray ───────────────────────────── */
static mxArray *ptr_to_mx(void *ptr)
{
    mxArray *a = mxCreateNumericMatrix(1, 1, mxUINT64_CLASS, mxREAL);
    *((uint64_t *)mxGetData(a)) = (uint64_t)(uintptr_t)ptr;
    return a;
}

static void *mx_to_ptr(const mxArray *a)
{
    return (void *)(uintptr_t)(*((const uint64_t *)mxGetData(a)));
}

/* ── Helper: const char** -> cell array of strings ──────────────────────── */
static mxArray *names_to_cell(const char **names, size_t n)
{
    mxArray *cell = mxCreateCellMatrix(1, (mwSize)n);
    for (size_t i = 0; i < n; i++)
        mxSetCell(cell, (mwIndex)i, mxCreateString(names[i]));
    return cell;
}

/* ── Symbol loader macro ─────────────────────────────────────────────────── */
#define LOAD(var, sym)                                                         \
    do {                                                                       \
        dlerror();                                                             \
        *(void **)(&var) = dlsym(_lib, sym);                                   \
        if (!var)                                                              \
            mexErrMsgIdAndTxt("Modena:init",                                   \
                "Symbol '" sym "' not found in libmodena.so: %s", dlerror()); \
    } while (0)

/* ── Initialization (runs once per MATLAB/Octave session) ────────────────── */
static void ensure_init(void)
{
    if (_lib) return;

    /* 1. Determine MODENA_LIB_DIR ─────────────────────────────────────────── */
    static char dir[4096];
    const char *ev = getenv("MODENA_LIB_DIR");
    if (ev && *ev) {
        strncpy(dir, ev, sizeof(dir) - 1);
        dir[sizeof(dir) - 1] = '\0';
    } else {
        if (!popen_last_line(
                "python3 -c \"import modena; print(modena.MODENA_LIB_DIR)\"",
                dir, sizeof(dir)))
            mexErrMsgIdAndTxt("Modena:init",
                "Cannot determine MODENA_LIB_DIR. "
                "Set the environment variable or ensure 'python3 -c "
                "\"import modena\"' works from this session.");
    }

    /* 2. Promote libpython into the global symbol namespace ─────────────────
     * Python extension modules (.so files such as _bz2) look up Python symbols
     * via the global namespace.  When libmodena.so is loaded as a DT_NEEDED
     * dependency the linker uses RTLD_LOCAL, making Python symbols invisible.
     * Opening libpython with RTLD_GLOBAL first fixes this.               */
    {
        static char libname[256];
        dlerror();
        if (!popen_last_line(
                "python3 -c \"import sysconfig; "
                "print(sysconfig.get_config_var('LDLIBRARY') or '')\"",
                libname, sizeof(libname)) || !libname[0])
            strncpy(libname, "libpython3.so.1.0", sizeof(libname));

        /* Try to upgrade an existing mapping first (RTLD_NOLOAD), then load
         * fresh.  Non-fatal: Python may still initialise if already global. */
        static void *_libpy = NULL;
        _libpy = dlopen(libname, RTLD_LAZY | RTLD_GLOBAL | RTLD_NOLOAD);
        if (!_libpy) _libpy = dlopen(libname, RTLD_LAZY | RTLD_GLOBAL);
        dlerror(); /* clear any error from the attempts above */

        /* 2b. Resolve Py_DecRef from the libpython handle ───────────────────
         * modena_model_t is a Python extension type (PyObject_HEAD).  Calling
         * modena_model_destroy() directly bypasses Python's reference counting:
         * the memory is freed while ob_refcnt is still 1, so Py_Finalize() at
         * process exit may access the freed block → segfault.  Instead we call
         * Py_DecRef() to decrement the refcount to 0, triggering tp_dealloc
         * (= modena_model_t_dealloc = modena_model_destroy) at the right time.*/
        if (_libpy)
            *(void **)(&p_Py_DecRef) = dlsym(_libpy, "Py_DecRef");
        if (!p_Py_DecRef)
            mexErrMsgIdAndTxt("Modena:init",
                "Symbol 'Py_DecRef' not found in libpython '%s'. "
                "Cannot safely free modena_model_t objects.", libname);
    }

    /* 3. Set PYTHONPATH so embedded Py_Initialize() finds the modena pkg ─── */
    if (!getenv("PYTHONPATH")) {
        static char paths[8192];
        if (popen_last_line(
                "python3 -c \"import sys; "
                "print(':'.join(p for p in sys.path if p))\"",
                paths, sizeof(paths)) && paths[0])
            setenv("PYTHONPATH", paths, 0);
    }

    /* 4. Load libmodena.so ──────────────────────────────────────────────────
     * The library uses __attribute__((constructor)) on PyInit_libmodena, so
     * Py_Initialize() and PyImport_Import("modena.SurrogateModel") run
     * automatically here.                                                   */
    {
        static char lib_path[4096 + 32];
        snprintf(lib_path, sizeof(lib_path), "%s/libmodena.so", dir);
        dlerror();
        _lib = dlopen(lib_path, RTLD_LAZY | RTLD_GLOBAL);
        if (!_lib)
            mexErrMsgIdAndTxt("Modena:init",
                "dlopen('%s') failed: %s", lib_path, dlerror());
    }

    /* 5. Resolve all symbols ─────────────────────────────────────────────── */
    LOAD(p_model_new,       "modena_model_new");
    LOAD(p_inputs_new,      "modena_inputs_new");
    LOAD(p_outputs_new,     "modena_outputs_new");
    LOAD(p_inputs_destroy,  "modena_inputs_destroy");
    LOAD(p_outputs_destroy, "modena_outputs_destroy");
    LOAD(p_inputs_argPos,   "modena_model_inputs_argPos");
    LOAD(p_outputs_argPos,  "modena_model_outputs_argPos");
    LOAD(p_argPos_check,    "modena_model_argPos_check");
    LOAD(p_inputs_set,      "modena_inputs_set");
    LOAD(p_outputs_get,     "modena_outputs_get");
    LOAD(p_model_call,      "modena_model_call");
    LOAD(p_inputs_size,     "modena_model_inputs_size");
    LOAD(p_outputs_size,    "modena_model_outputs_size");
    LOAD(p_parameters_size, "modena_model_parameters_size");
    LOAD(p_inputs_names,    "modena_model_inputs_names");
    LOAD(p_outputs_names,   "modena_model_outputs_names");
    LOAD(p_parameters_names,"modena_model_parameters_names");
}

/* ── MEX entry point ─────────────────────────────────────────────────────── */
void mexFunction(int nlhs, mxArray *plhs[],
                 int nrhs, const mxArray *prhs[])
{
    if (nrhs < 1 || !mxIsChar(prhs[0]))
        mexErrMsgIdAndTxt("Modena:usage",
            "First argument must be a command string.");

    ensure_init();

    char *cmd = mxArrayToString(prhs[0]);

    /* ── model_new ─────────────────────────────────────────────────────────── */
    if (strcmp(cmd, "model_new") == 0) {
        if (nrhs != 2 || !mxIsChar(prhs[1]))
            mexErrMsgIdAndTxt("Modena:usage",
                "model_new(modelId): expected a model ID string.");
        char *id = mxArrayToString(prhs[1]);
        modena_model_t *m = p_model_new(id);
        mxFree(id);
        if (!m)
            mexErrMsgIdAndTxt("Modena:model_new",
                "Model not found in database.");
        plhs[0] = ptr_to_mx(m);

    /* ── inputs_new ────────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "inputs_new") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "inputs_new(model_ptr).");
        plhs[0] = ptr_to_mx(p_inputs_new(mx_to_ptr(prhs[1])));

    /* ── outputs_new ───────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "outputs_new") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "outputs_new(model_ptr).");
        plhs[0] = ptr_to_mx(p_outputs_new(mx_to_ptr(prhs[1])));

    /* ── model_destroy ─────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "model_destroy") == 0) {
        if (nrhs != 4)
            mexErrMsgIdAndTxt("Modena:usage",
                "model_destroy(model_ptr, inputs_ptr, outputs_ptr).");
        /* Free inputs/outputs first (plain C structs, safe to destroy directly).
         * Then Py_DecRef the model: this decrements ob_refcnt to 0 which
         * triggers tp_dealloc → modena_model_destroy via Python's normal path,
         * preventing use-after-free when Py_Finalize() runs on process exit. */
        p_inputs_destroy (mx_to_ptr(prhs[2]));
        p_outputs_destroy(mx_to_ptr(prhs[3]));
        p_Py_DecRef      (mx_to_ptr(prhs[1]));

    /* ── input_pos ─────────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "input_pos") == 0) {
        if (nrhs != 3 || !mxIsChar(prhs[2]))
            mexErrMsgIdAndTxt("Modena:usage",
                "input_pos(model_ptr, name).");
        char *name = mxArrayToString(prhs[2]);
        size_t pos = p_inputs_argPos(mx_to_ptr(prhs[1]), name);
        mxFree(name);
        plhs[0] = mxCreateDoubleScalar((double)pos);

    /* ── output_pos ────────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "output_pos") == 0) {
        if (nrhs != 3 || !mxIsChar(prhs[2]))
            mexErrMsgIdAndTxt("Modena:usage",
                "output_pos(model_ptr, name).");
        char *name = mxArrayToString(prhs[2]);
        size_t pos = p_outputs_argPos(mx_to_ptr(prhs[1]), name);
        mxFree(name);
        plhs[0] = mxCreateDoubleScalar((double)pos);

    /* ── argpos_check ──────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "argpos_check") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "argpos_check(model_ptr).");
        p_argPos_check(mx_to_ptr(prhs[1]));

    /* ── inputs_set ────────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "inputs_set") == 0) {
        if (nrhs != 4)
            mexErrMsgIdAndTxt("Modena:usage",
                "inputs_set(inputs_ptr, pos, value).");
        p_inputs_set(mx_to_ptr(prhs[1]),
                     (size_t)mxGetScalar(prhs[2]),
                     mxGetScalar(prhs[3]));

    /* ── outputs_get ───────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "outputs_get") == 0) {
        if (nrhs != 3)
            mexErrMsgIdAndTxt("Modena:usage",
                "outputs_get(outputs_ptr, pos).");
        plhs[0] = mxCreateDoubleScalar(
            p_outputs_get(mx_to_ptr(prhs[1]), (size_t)mxGetScalar(prhs[2])));

    /* ── model_call ────────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "model_call") == 0) {
        if (nrhs != 4)
            mexErrMsgIdAndTxt("Modena:usage",
                "model_call(model_ptr, inputs_ptr, outputs_ptr).");
        int ret = p_model_call(mx_to_ptr(prhs[1]),
                               mx_to_ptr(prhs[2]),
                               mx_to_ptr(prhs[3]));
        plhs[0] = mxCreateDoubleScalar((double)ret);

    /* ── inputs_size ───────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "inputs_size") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "inputs_size(model_ptr).");
        plhs[0] = mxCreateDoubleScalar(
            (double)p_inputs_size(mx_to_ptr(prhs[1])));

    /* ── outputs_size ──────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "outputs_size") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "outputs_size(model_ptr).");
        plhs[0] = mxCreateDoubleScalar(
            (double)p_outputs_size(mx_to_ptr(prhs[1])));

    /* ── parameters_size ───────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "parameters_size") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "parameters_size(model_ptr).");
        plhs[0] = mxCreateDoubleScalar(
            (double)p_parameters_size(mx_to_ptr(prhs[1])));

    /* ── inputs_names ──────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "inputs_names") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "inputs_names(model_ptr).");
        void *m = mx_to_ptr(prhs[1]);
        plhs[0] = names_to_cell(p_inputs_names(m), p_inputs_size(m));

    /* ── outputs_names ─────────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "outputs_names") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "outputs_names(model_ptr).");
        void *m = mx_to_ptr(prhs[1]);
        plhs[0] = names_to_cell(p_outputs_names(m), p_outputs_size(m));

    /* ── parameters_names ──────────────────────────────────────────────────── */
    } else if (strcmp(cmd, "parameters_names") == 0) {
        if (nrhs != 2)
            mexErrMsgIdAndTxt("Modena:usage", "parameters_names(model_ptr).");
        void *m = mx_to_ptr(prhs[1]);
        plhs[0] = names_to_cell(p_parameters_names(m), p_parameters_size(m));

    } else {
        mexErrMsgIdAndTxt("Modena:usage",
            "Unknown command '%s'.", cmd);
    }

    mxFree(cmd);
}
