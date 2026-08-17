"""
    Modena

Julia wrapper for the MoDeNa surrogate-model C library (`libmodena`).

# Quick start
```julia
using Modena

m = Model("flowRate")
Dpos  = input_pos(m, "D")
p0pos = input_pos(m, "p0")
check(m)                          # verify all inputs queried

t = 0.0
while t < tend
    global t += dt
    set!(m, Dpos,  D)
    set!(m, p0pos, p0)
    try
        call!(m)
    catch e
        e isa ParametersUpdated && (t -= dt; continue)   # retry step
        e isa ExitAndRestart    && exit(e.code)
        e isa ExitNoRestart     && exit(e.code)
        rethrow()
    end
    mdot = output(m, 0)
end
```

# Library discovery
`libmodena.so` is located by (in order):
1. `MODENA_LIB_DIR` environment variable
2. `python3 -c "import modena; print(modena.MODENA_LIB_DIR)"` (always available in this framework)
3. `Libdl.find_library("libmodena")` (honours `LD_LIBRARY_PATH`)
"""
module Modena

using Libdl

# ── Library handle ────────────────────────────────────────────────────────────
# Opened in __init__ so the path is resolved at runtime, not precompile time.
# All ccalls use Libdl.dlsym(handle, :func) which accepts a runtime Ptr{Cvoid}.

const _lib    = Ref{Ptr{Cvoid}}(C_NULL)
# Handle to libpython, opened with RTLD_GLOBAL in _prime_python_env().
# Used to call Py_DecRef() for safe model destruction (see _destroy! below).
const _libpy  = Ref{Ptr{Cvoid}}(C_NULL)

function __init__()
    # 1. Explicit env var
    dir = get(ENV, "MODENA_LIB_DIR", "")

    # 2. Ask the Python modena package (always present in this framework).
    # Take only the last line — modena prints startup messages to stdout.
    if isempty(dir)
        try
            raw = readchomp(`python3 -c "import modena; print(modena.MODENA_LIB_DIR)"`)
            dir = strip(split(raw, "\n")[end])
        catch e
            e isa InterruptException && rethrow(e)
        end
    end

    if !isempty(dir)
        path = joinpath(dir, "libmodena.so")
        isfile(path) || error(
            "libmodena.so not found at '$path'. " *
            "Check MODENA_LIB_DIR or LD_LIBRARY_PATH."
        )
        _prime_python_env()
        _lib[] = Libdl.dlopen(path, Libdl.RTLD_LAZY | Libdl.RTLD_GLOBAL)
        return
    end

    # 3. Standard library search (honours LD_LIBRARY_PATH)
    found = Libdl.find_library("libmodena")
    isempty(found) && error(
        "libmodena not found. Set MODENA_LIB_DIR or add its directory to LD_LIBRARY_PATH."
    )
    _prime_python_env()
    _lib[] = Libdl.dlopen(found, Libdl.RTLD_LAZY | Libdl.RTLD_GLOBAL)
end

# libmodena.so declares PyInit_libmodena with __attribute__((constructor)), so it
# runs automatically on dlopen and calls Py_Initialize() followed by
# PyImport_Import("modena.SurrogateModel").  Two things must happen before dlopen:
#
#  1. Load libpython with RTLD_GLOBAL.  When libmodena.so is loaded, its DT_NEEDED
#     entry causes libpython to be mapped with RTLD_LOCAL (the linker default).
#     Python extension modules (.so files such as _bz2) expect libpython symbols
#     to be in the global symbol namespace — if they are not, dlopen of the
#     extension fails with "undefined symbol".  Opening libpython explicitly with
#     RTLD_GLOBAL first prevents this.
#
#  2. Set PYTHONPATH so the embedded Py_Initialize() can find the modena package.
#     If the caller already set PYTHONPATH we leave it alone.
function _prime_python_env()
    # Step 1 — promote libpython into the global symbol namespace.
    # Ask the running Python for the exact shared-library name (e.g.
    # "libpython3.11.so.1.0") before falling back to generic names.
    libname = ""
    try
        raw = readchomp(`python3 -c "import sysconfig; print(sysconfig.get_config_var('LDLIBRARY') or '')"`)
        libname = strip(split(raw, "\n")[end])
    catch e
        e isa InterruptException && rethrow(e)
    end

    candidates = filter!(!isempty, [libname, "libpython3", "libpython"])
    found = Libdl.find_library(candidates)
    if !isempty(found)
        h = Libdl.dlopen(found, Libdl.RTLD_LAZY | Libdl.RTLD_GLOBAL)
        _libpy[] = h
    end

    # Step 2 — export sys.path so the embedded Python finds the modena package.
    haskey(ENV, "PYTHONPATH") && return
    try
        raw = readchomp(`python3 -c "import sys; print(':'.join(p for p in sys.path if p))"`)
        paths = strip(split(raw, "\n")[end])
        isempty(paths) || (ENV["PYTHONPATH"] = paths)
    catch e
        e isa InterruptException && rethrow(e)
    end
end

# Convenience: resolve a symbol from the open library handle.
@inline _sym(name::Symbol) = Libdl.dlsym(_lib[], name)

# ── Exceptions ────────────────────────────────────────────────────────────────

"""
Thrown by `call!` when the surrogate was retrained mid-call (return code 100).
Decrement your time step and retry.
"""
struct ParametersUpdated <: Exception end

"""
Thrown by `call!` when the workflow signals exit-and-restart (return code 200).
Pass `e.code` to `exit()`.
"""
struct ExitAndRestart <: Exception
    code::Int
end

"""
Thrown by `call!` when the model is not in the database and must be
initialised from its module (return code 201).  Not a successful termination.
Pass `e.code` to `exit()`.
"""
struct ExitNoRestart <: Exception
    code::Int
end

"""Thrown by `call!` on any other non-zero return code."""
struct ModenaError <: Exception
    code::Int
end

Base.showerror(io::IO, ::ParametersUpdated) =
    print(io, "Modena: surrogate parameters updated — retry this time step")
Base.showerror(io::IO, e::ExitAndRestart) =
    print(io, "Modena: exit and restart requested (code $(e.code))")
Base.showerror(io::IO, e::ExitNoRestart) =
    print(io, "Modena: exit without restart requested (code $(e.code))")
Base.showerror(io::IO, e::ModenaError) =
    print(io, "Modena: unexpected return code $(e.code)")

# ── Model ─────────────────────────────────────────────────────────────────────

"""
    Model(id)

Load a MoDeNa surrogate model by its database ID and allocate input/output
vectors.  The model, inputs, and outputs are freed automatically when the
`Model` object is garbage-collected.

All input and output positions are resolved once here and cached, so later
named access via `set!(m, name, v)` and `output(m, name)` is a plain `Dict`
lookup — no calls into the embedded Python.  This matters because `check`
releases the GIL for the time-step loop; resolving a name after that point
would call `PyObject_CallMethod` without the GIL and segfault the process.

The same caching happens in the C++ wrapper (`modena::Model`).  It has one
consequence worth knowing: `modena_model_inputs_argPos` marks a position as
"used", so after construction every input counts as queried and `check` can
no longer catch an input the application forgot to `set!`.
"""
mutable struct Model
    _model  ::Ptr{Cvoid}
    _inputs ::Ptr{Cvoid}
    _outputs::Ptr{Cvoid}
    _input_pos ::Dict{String, Int}
    _output_pos::Dict{String, Int}

    function Model(id::AbstractString)
        mptr = ccall(_sym(:modena_model_new), Ptr{Cvoid}, (Cstring,), id)
        mptr == C_NULL && error("modena_model_new: model '$id' not found in database")
        iptr = ccall(_sym(:modena_inputs_new),  Ptr{Cvoid}, (Ptr{Cvoid},), mptr)
        optr = ccall(_sym(:modena_outputs_new), Ptr{Cvoid}, (Ptr{Cvoid},), mptr)
        m = new(mptr, iptr, optr, Dict{String, Int}(), Dict{String, Int}())
        # Register the finalizer before the (Python-calling) name resolution
        # below, so a failure there still frees the C allocations.
        finalizer(_destroy!, m)
        for name in inputs_names(m)
            m._input_pos[name] = _inputs_argPos(m, name)
        end
        for name in outputs_names(m)
            m._output_pos[name] = _outputs_argPos(m, name)
        end
        m
    end
end

function _destroy!(m::Model)
    m._inputs  != C_NULL && ccall(_sym(:modena_inputs_destroy),  Cvoid, (Ptr{Cvoid},), m._inputs)
    m._outputs != C_NULL && ccall(_sym(:modena_outputs_destroy), Cvoid, (Ptr{Cvoid},), m._outputs)
    if m._model != C_NULL
        # modena_model_t is a Python extension type (PyObject_HEAD).  Calling
        # modena_model_destroy() directly frees the memory while ob_refcnt is
        # still 1; Py_Finalize() at process exit may then access the freed
        # block and segfault.  The correct path is Py_DecRef(), which
        # decrements ob_refcnt to 0 and lets Python call tp_dealloc
        # (= modena_model_t_dealloc = modena_model_destroy) at the right time.
        py_decref = _libpy[] != C_NULL ? Libdl.dlsym_e(_libpy[], :Py_DecRef) : C_NULL
        if py_decref != C_NULL
            ccall(py_decref, Cvoid, (Ptr{Cvoid},), m._model)
        else
            # libpython not available — fall back to direct destroy.  Rare on
            # normal Linux setups; this path risks a stale refcount at Py_Finalize.
            ccall(_sym(:modena_model_destroy), Cvoid, (Ptr{Cvoid},), m._model)
        end
    end
    m._inputs = m._outputs = m._model = C_NULL
    nothing
end

# ── Positional access ─────────────────────────────────────────────────────────

# Raw argPos lookups — these call into the embedded Python and are only safe
# before `check` releases the GIL.  Used once each, from the `Model` ctor.
_inputs_argPos(m::Model, name::AbstractString)::Int =
    Int(ccall(_sym(:modena_model_inputs_argPos), Csize_t, (Ptr{Cvoid}, Cstring), m._model, name))

_outputs_argPos(m::Model, name::AbstractString)::Int =
    Int(ccall(_sym(:modena_model_outputs_argPos), Csize_t, (Ptr{Cvoid}, Cstring), m._model, name))

"""
    input_pos(m, name) -> Int

Return the 0-based position index of the input named `name`.
Cache the result before the simulation loop, then use `set!(m, pos, value)`.

Resolved from the cache built at construction — a `Dict` lookup, safe to call
after `check`.  Throws `KeyError` if `name` is not a declared input.
"""
input_pos(m::Model, name::AbstractString)::Int = m._input_pos[name]

"""
    output_pos(m, name) -> Int

Return the 0-based position index of the output named `name`.

Resolved from the cache built at construction — a `Dict` lookup, safe to call
after `check`.  Throws `KeyError` if `name` is not a declared output.
"""
output_pos(m::Model, name::AbstractString)::Int = m._output_pos[name]

"""
    check(m)

Finish the setup phase and release the GIL for the simulation loop.

Call once after all `input_pos` calls and before entering the loop.  Beyond
the GIL handover, libmodena verifies here that every input position has been
queried — though because `Model` resolves all of them at construction, that
check always passes from Julia.
"""
function check(m::Model)
    ccall(_sym(:modena_model_argPos_check), Cvoid, (Ptr{Cvoid},), m._model)
end

"""
    set!(m, i::Integer, value)

Set input at 0-based position `i` to `value`.
"""
function set!(m::Model, i::Integer, value::Real)
    ccall(_sym(:modena_inputs_set), Cvoid,
          (Ptr{Cvoid}, Csize_t, Cdouble), m._inputs, Csize_t(i), Float64(value))
end

"""
    output(m, i::Integer) -> Float64

Get output at 0-based position `i` after a successful `call!`.
"""
function output(m::Model, i::Integer)::Float64
    ccall(_sym(:modena_outputs_get), Cdouble, (Ptr{Cvoid}, Csize_t), m._outputs, Csize_t(i))
end

# ── Named access ──────────────────────────────────────────────────────────────

"""
    set!(m, name::AbstractString, value)

Set input by name.  Costs one `Dict` lookup over the positional form; safe
to use after `check`.
"""
function set!(m::Model, name::AbstractString, value::Real)
    set!(m, input_pos(m, name), value)
end

"""
    output(m, name::AbstractString) -> Float64

Get output by name.  Costs one `Dict` lookup over the positional form; safe
to use after `check`.
"""
function output(m::Model, name::AbstractString)::Float64
    output(m, output_pos(m, name))
end

# ── Evaluation ────────────────────────────────────────────────────────────────

"""
    call!(m)

Evaluate the surrogate model with the current inputs.

Throws:
- `ParametersUpdated` — model was retrained; decrement time and retry the step
- `ExitAndRestart`    — workflow requests exit-and-restart; call `exit(e.code)`
- `ExitNoRestart`     — workflow requests clean exit; call `exit(e.code)`
- `ModenaError`       — unexpected non-zero return code
"""
function call!(m::Model)
    ret = Int(ccall(_sym(:modena_model_call), Cint,
                    (Ptr{Cvoid}, Ptr{Cvoid}, Ptr{Cvoid}),
                    m._model, m._inputs, m._outputs))
    ret ==   0 && return
    ret == 100 && throw(ParametersUpdated())
    ret == 200 && throw(ExitAndRestart(ret))
    ret == 201 && throw(ExitNoRestart(ret))
    throw(ModenaError(ret))
end

# ── Metadata ──────────────────────────────────────────────────────────────────

"""Number of inputs the model expects."""
inputs_size(m::Model)::Int =
    Int(ccall(_sym(:modena_model_inputs_size), Csize_t, (Ptr{Cvoid},), m._model))

"""Number of outputs the model produces."""
outputs_size(m::Model)::Int =
    Int(ccall(_sym(:modena_model_outputs_size), Csize_t, (Ptr{Cvoid},), m._model))

"""Number of fitted parameters."""
parameters_size(m::Model)::Int =
    Int(ccall(_sym(:modena_model_parameters_size), Csize_t, (Ptr{Cvoid},), m._model))

function _read_name_array(ptr::Ptr{Ptr{UInt8}}, n::Int)::Vector{String}
    [unsafe_string(unsafe_load(ptr, i)) for i in 1:n]
end

"""Names of all inputs, in positional order."""
function inputs_names(m::Model)::Vector{String}
    ptr = ccall(_sym(:modena_model_inputs_names), Ptr{Ptr{UInt8}}, (Ptr{Cvoid},), m._model)
    _read_name_array(ptr, inputs_size(m))
end

"""Names of all outputs, in positional order."""
function outputs_names(m::Model)::Vector{String}
    ptr = ccall(_sym(:modena_model_outputs_names), Ptr{Ptr{UInt8}}, (Ptr{Cvoid},), m._model)
    _read_name_array(ptr, outputs_size(m))
end

"""Names of all fitted parameters, in positional order."""
function parameters_names(m::Model)::Vector{String}
    ptr = ccall(_sym(:modena_model_parameters_names), Ptr{Ptr{UInt8}}, (Ptr{Cvoid},), m._model)
    _read_name_array(ptr, parameters_size(m))
end

"""Fitted value of one parameter by argPos index (0-based, matches C API)."""
parameter(m::Model, i::Integer)::Float64 =
    ccall(_sym(:modena_model_parameters_get), Cdouble,
          (Ptr{Cvoid}, Csize_t), m._model, Csize_t(i))

"""Fitted value of one parameter by declared name.

Throws `KeyError(name)` if `name` is not a declared parameter.
"""
function parameter(m::Model, name::AbstractString)::Float64
    names = parameters_names(m)
    idx = findfirst(==(name), names)
    idx === nothing && throw(KeyError(name))
    parameter(m, idx - 1)   # Julia is 1-based; C API is 0-based
end

"""Fitted parameters as a `Dict{String, Float64}` keyed by declared name.

The Julia equivalent of Python's `model.named_parameters()`.
"""
function parameters(m::Model)::Dict{String, Float64}
    names = parameters_names(m)
    Dict(name => parameter(m, i - 1) for (i, name) in enumerate(names))
end

# ── Exports ───────────────────────────────────────────────────────────────────

export Model
export ParametersUpdated, ExitAndRestart, ExitNoRestart, ModenaError
export input_pos, output_pos, check, set!, output, call!
export inputs_size, outputs_size, parameters_size
export inputs_names, outputs_names, parameters_names
export parameter, parameters

end # module Modena
