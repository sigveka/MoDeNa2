/*
 * modena_r.c — R .Call() extension that wraps libmodena at runtime.
 *
 * libmodena.so is loaded via dlopen() at first use, following the same
 * approach as the MATLAB MEX gateway (modena_gateway.c).  The R package
 * itself does NOT link against libmodena at compile time, so it can be
 * installed on any machine regardless of whether MoDeNa is present; the
 * library path is resolved at runtime from MODENA_LIB_DIR or by querying
 * the Python modena package.
 *
 * Design note — Python symbol namespace and model destruction
 * ──────────────────────────────────────────────────────────
 * libmodena.so embeds CPython.  For Python extension modules (.so files
 * such as _bz2) to resolve Python symbols, libpython must be in the
 * *global* symbol namespace (RTLD_GLOBAL).  When libmodena is loaded as a
 * DT_NEEDED dependency the linker uses RTLD_LOCAL by default, which breaks
 * extension loading.  We therefore:
 *   1. Explicitly dlopen libpython with RTLD_GLOBAL before loading libmodena.
 *   2. Set PYTHONPATH so the embedded Python finds the modena package.
 *   3. dlopen libmodena with RTLD_GLOBAL.
 *
 * modena_model_t is a Python extension type (PyObject_HEAD).  Calling
 * modena_model_destroy() directly frees memory while ob_refcnt is still 1;
 * Py_Finalize() at process exit may then access the freed block → segfault.
 * Instead, the model externalptr finalizer calls Py_DecRef(), which
 * decrements ob_refcnt to 0 and lets Python's tp_dealloc run at the right
 * time.  modena_inputs_t and modena_outputs_t are plain C structs; their
 * destroy functions are called directly.
 */

#include <R.h>
#include <Rinternals.h>
#include <R_ext/Rdynload.h>
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
typedef modena_model_t*   (*fp_model_new_t)       (const char *);
typedef modena_inputs_t*  (*fp_inputs_new_t)      (const modena_model_t *);
typedef modena_outputs_t* (*fp_outputs_new_t)     (const modena_model_t *);
typedef void              (*fp_inputs_destroy_t)  (modena_inputs_t *);
typedef void              (*fp_outputs_destroy_t) (modena_outputs_t *);
typedef void              (*fp_Py_DecRef_t)        (void *);
typedef size_t (*fp_inputs_argPos_t)  (const modena_model_t *, const char *);
typedef size_t (*fp_outputs_argPos_t) (const modena_model_t *, const char *);
typedef void   (*fp_argPos_check_t)   (const modena_model_t *);
typedef void   (*fp_inputs_set_t)     (modena_inputs_t *, size_t, double);
typedef double (*fp_outputs_get_t)    (const modena_outputs_t *, size_t);
typedef int    (*fp_model_call_t)     (modena_model_t *,
                                       modena_inputs_t *,
                                       modena_outputs_t *);
typedef size_t       (*fp_inputs_size_t)      (const modena_model_t *);
typedef size_t       (*fp_outputs_size_t)     (const modena_model_t *);
typedef size_t       (*fp_parameters_size_t)  (const modena_model_t *);
typedef const char** (*fp_inputs_names_t)     (const modena_model_t *);
typedef const char** (*fp_outputs_names_t)    (const modena_model_t *);
typedef const char** (*fp_parameters_names_t) (const modena_model_t *);

/* ── Static library handle and resolved symbols ──────────────────────────── */
static void *_lib      = NULL;
static void *_libpy    = NULL;

static fp_model_new_t        p_model_new;
static fp_Py_DecRef_t        p_Py_DecRef;
static fp_inputs_new_t       p_inputs_new;
static fp_outputs_new_t      p_outputs_new;
static fp_inputs_destroy_t   p_inputs_destroy;
static fp_outputs_destroy_t  p_outputs_destroy;
static fp_inputs_argPos_t    p_inputs_argPos;
static fp_outputs_argPos_t   p_outputs_argPos;
static fp_argPos_check_t     p_argPos_check;
static fp_inputs_set_t       p_inputs_set;
static fp_outputs_get_t      p_outputs_get;
static fp_model_call_t       p_model_call;
static fp_inputs_size_t      p_inputs_size;
static fp_outputs_size_t     p_outputs_size;
static fp_parameters_size_t  p_parameters_size;
static fp_inputs_names_t     p_inputs_names;
static fp_outputs_names_t    p_outputs_names;
static fp_parameters_names_t p_parameters_names;

/* ── Helper: last non-empty line from a popen command ───────────────────── */
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

/* ── Symbol loader macro ─────────────────────────────────────────────────── */
#define LOAD(var, sym)                                                          \
    do {                                                                        \
        dlerror();                                                              \
        *(void **)(&var) = dlsym(_lib, sym);                                    \
        if (!var)                                                               \
            Rf_error("Modena: symbol '" sym "' not found in libmodena.so: %s", \
                     dlerror());                                                 \
    } while (0)

/* ── Initialization (runs once per R session) ────────────────────────────── */
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
            Rf_error(
                "Modena: cannot determine MODENA_LIB_DIR. "
                "Set the environment variable or ensure "
                "'python3 -c \"import modena\"' works from this session.");
    }

    /* 2. Promote libpython into the global symbol namespace ─────────────────
     * Python extension modules look up Python symbols via the global namespace.
     * When libmodena.so is loaded as a DT_NEEDED dependency the linker uses
     * RTLD_LOCAL, making Python symbols invisible to extensions.  Opening
     * libpython with RTLD_GLOBAL first fixes this.                         */
    {
        static char libname[256];
        if (!popen_last_line(
                "python3 -c \"import sysconfig; "
                "print(sysconfig.get_config_var('LDLIBRARY') or '')\"",
                libname, sizeof(libname)) || !libname[0])
            strncpy(libname, "libpython3.so.1.0", sizeof(libname));

        _libpy = dlopen(libname, RTLD_LAZY | RTLD_GLOBAL | RTLD_NOLOAD);
        if (!_libpy) _libpy = dlopen(libname, RTLD_LAZY | RTLD_GLOBAL);
        dlerror();

        /* Resolve Py_DecRef for safe model destruction (see file header). */
        if (_libpy)
            *(void **)(&p_Py_DecRef) = dlsym(_libpy, "Py_DecRef");
        if (!p_Py_DecRef)
            Rf_error(
                "Modena: symbol 'Py_DecRef' not found in libpython '%s'. "
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
     * __attribute__((constructor)) on PyInit_libmodena triggers
     * Py_Initialize() and PyImport_Import("modena.SurrogateModel") here.   */
    {
        static char lib_path[4096 + 32];
        snprintf(lib_path, sizeof(lib_path), "%s/libmodena.so", dir);
        dlerror();
        _lib = dlopen(lib_path, RTLD_LAZY | RTLD_GLOBAL);
        if (!_lib)
            Rf_error("Modena: dlopen('%s') failed: %s", lib_path, dlerror());
    }

    /* 5. Resolve all symbols ─────────────────────────────────────────────── */
    LOAD(p_model_new,        "modena_model_new");
    LOAD(p_inputs_new,       "modena_inputs_new");
    LOAD(p_outputs_new,      "modena_outputs_new");
    LOAD(p_inputs_destroy,   "modena_inputs_destroy");
    LOAD(p_outputs_destroy,  "modena_outputs_destroy");
    LOAD(p_inputs_argPos,    "modena_model_inputs_argPos");
    LOAD(p_outputs_argPos,   "modena_model_outputs_argPos");
    LOAD(p_argPos_check,     "modena_model_argPos_check");
    LOAD(p_inputs_set,       "modena_inputs_set");
    LOAD(p_outputs_get,      "modena_outputs_get");
    LOAD(p_model_call,       "modena_model_call");
    LOAD(p_inputs_size,      "modena_model_inputs_size");
    LOAD(p_outputs_size,     "modena_model_outputs_size");
    LOAD(p_parameters_size,  "modena_model_parameters_size");
    LOAD(p_inputs_names,     "modena_model_inputs_names");
    LOAD(p_outputs_names,    "modena_model_outputs_names");
    LOAD(p_parameters_names, "modena_model_parameters_names");
}

/* ── externalptr finalizers ──────────────────────────────────────────────── */

static void model_finalizer(SEXP ptr)
{
    void *m = R_ExternalPtrAddr(ptr);
    if (!m) return;
    if (p_Py_DecRef) p_Py_DecRef(m);
    R_ClearExternalPtr(ptr);
}

static void inputs_finalizer(SEXP ptr)
{
    void *i = R_ExternalPtrAddr(ptr);
    if (!i) return;
    if (p_inputs_destroy) p_inputs_destroy(i);
    R_ClearExternalPtr(ptr);
}

static void outputs_finalizer(SEXP ptr)
{
    void *o = R_ExternalPtrAddr(ptr);
    if (!o) return;
    if (p_outputs_destroy) p_outputs_destroy(o);
    R_ClearExternalPtr(ptr);
}

/* ── .Call() entry points ────────────────────────────────────────────────── */

SEXP r_modena_init(void)
{
    ensure_init();
    return R_NilValue;
}

SEXP r_model_new(SEXP id_)
{
    ensure_init();
    const char *id = CHAR(STRING_ELT(id_, 0));
    modena_model_t *m = p_model_new(id);
    if (!m)
        Rf_error("Modena: model '%s' not found in database. "
                 "Run initModels first.", id);
    SEXP ptr = PROTECT(R_MakeExternalPtr(m, R_NilValue, R_NilValue));
    R_RegisterCFinalizer(ptr, model_finalizer);
    UNPROTECT(1);
    return ptr;
}

SEXP r_inputs_new(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    SEXP ptr = PROTECT(R_MakeExternalPtr(p_inputs_new(m),
                                         R_NilValue, R_NilValue));
    R_RegisterCFinalizer(ptr, inputs_finalizer);
    UNPROTECT(1);
    return ptr;
}

SEXP r_outputs_new(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    SEXP ptr = PROTECT(R_MakeExternalPtr(p_outputs_new(m),
                                         R_NilValue, R_NilValue));
    R_RegisterCFinalizer(ptr, outputs_finalizer);
    UNPROTECT(1);
    return ptr;
}

SEXP r_inputs_argPos(SEXP model_, SEXP name_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return ScalarInteger((int)p_inputs_argPos(m, CHAR(STRING_ELT(name_, 0))));
}

SEXP r_outputs_argPos(SEXP model_, SEXP name_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return ScalarInteger((int)p_outputs_argPos(m, CHAR(STRING_ELT(name_, 0))));
}

SEXP r_argPos_check(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    p_argPos_check(m);
    return R_NilValue;
}

SEXP r_inputs_set(SEXP inputs_, SEXP pos_, SEXP value_)
{
    void *i = R_ExternalPtrAddr(inputs_);
    if (!i) Rf_error("Modena: inputs pointer is NULL");
    p_inputs_set(i, (size_t)asInteger(pos_), asReal(value_));
    return R_NilValue;
}

SEXP r_outputs_get(SEXP outputs_, SEXP pos_)
{
    void *o = R_ExternalPtrAddr(outputs_);
    if (!o) Rf_error("Modena: outputs pointer is NULL");
    return ScalarReal(p_outputs_get(o, (size_t)asInteger(pos_)));
}

SEXP r_model_call(SEXP model_, SEXP inputs_, SEXP outputs_)
{
    void *m = R_ExternalPtrAddr(model_);
    void *i = R_ExternalPtrAddr(inputs_);
    void *o = R_ExternalPtrAddr(outputs_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    if (!i) Rf_error("Modena: inputs pointer is NULL");
    if (!o) Rf_error("Modena: outputs pointer is NULL");
    return ScalarInteger(p_model_call(m, i, o));
}

SEXP r_inputs_size(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return ScalarInteger((int)p_inputs_size(m));
}

SEXP r_outputs_size(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return ScalarInteger((int)p_outputs_size(m));
}

SEXP r_parameters_size(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return ScalarInteger((int)p_parameters_size(m));
}

static SEXP names_to_strsxp(const char **names, size_t n)
{
    SEXP result = PROTECT(allocVector(STRSXP, (R_xlen_t)n));
    for (size_t i = 0; i < n; i++)
        SET_STRING_ELT(result, (R_xlen_t)i, mkChar(names[i]));
    UNPROTECT(1);
    return result;
}

SEXP r_inputs_names(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return names_to_strsxp(p_inputs_names(m), p_inputs_size(m));
}

SEXP r_outputs_names(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return names_to_strsxp(p_outputs_names(m), p_outputs_size(m));
}

SEXP r_parameters_names(SEXP model_)
{
    void *m = R_ExternalPtrAddr(model_);
    if (!m) Rf_error("Modena: model pointer is NULL");
    return names_to_strsxp(p_parameters_names(m), p_parameters_size(m));
}

/* ── Registration table ──────────────────────────────────────────────────── */
static const R_CallMethodDef CallMethods[] = {
    {"r_modena_init",      (DL_FUNC) &r_modena_init,       0},
    {"r_model_new",        (DL_FUNC) &r_model_new,         1},
    {"r_inputs_new",       (DL_FUNC) &r_inputs_new,        1},
    {"r_outputs_new",      (DL_FUNC) &r_outputs_new,       1},
    {"r_inputs_argPos",    (DL_FUNC) &r_inputs_argPos,     2},
    {"r_outputs_argPos",   (DL_FUNC) &r_outputs_argPos,    2},
    {"r_argPos_check",     (DL_FUNC) &r_argPos_check,      1},
    {"r_inputs_set",       (DL_FUNC) &r_inputs_set,        3},
    {"r_outputs_get",      (DL_FUNC) &r_outputs_get,       2},
    {"r_model_call",       (DL_FUNC) &r_model_call,        3},
    {"r_inputs_size",      (DL_FUNC) &r_inputs_size,       1},
    {"r_outputs_size",     (DL_FUNC) &r_outputs_size,      1},
    {"r_parameters_size",  (DL_FUNC) &r_parameters_size,   1},
    {"r_inputs_names",     (DL_FUNC) &r_inputs_names,      1},
    {"r_outputs_names",    (DL_FUNC) &r_outputs_names,     1},
    {"r_parameters_names", (DL_FUNC) &r_parameters_names,  1},
    {NULL, NULL, 0}
};

void R_init_modena(DllInfo *dll)
{
    R_registerRoutines(dll, NULL, CallMethods, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
}
