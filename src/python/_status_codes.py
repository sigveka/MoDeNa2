"""
@namespace  python._status_codes
@brief      THE definition of the MoDeNa workflow protocol status codes.

These numbers used to be written out in five languages plus the docs, and every
copy drifted independently: "201 = clean exit" survived in six documents while
handleReturnCode() had always treated 201 as "model needs initialising".

They are defined here, in Python, because Python is the layer that produces
them -- ``SurrogateModel.exception*()`` returns them and ``handleReturnCode()``
dispatches on them.  At configure time CMake reads ``STATUS_CODES`` below and
generates the C enum, the Fortran parameters, the MATLAB constants and the R
constants from it, so adding a code here reaches every binding.

Import the names from ``modena.Strategy``, which re-exports them.

@see docs/return-codes.md, src/status-codes.cmake
"""

#: (NAME, VALUE, DESCRIPTION) in the order the generated files list them.
#:
#: DESCRIPTION becomes the doc comment in every language and the
#: modena_error_message() text.  It may not contain '|' or ';' -- CMake parses
#: this table with '|' as the field separator and splits lists on semicolons.
STATUS_CODES = (
    ('OK', 0,
     'Success -- the outputs are valid'),
    ('INTERNAL_ERROR', 1,
     'Internal error in libmodena (allocation, CPython call)'),
    ('RETRAINED', 100,
     'Surrogate retrained mid-run -- retry this step in-process, do not exit'),
    ('OUT_OF_BOUNDS', 200,
     "Input outside the surrogate's trained domain -- exit, FireWorks retrains and re-queues"),
    ('MODEL_NOT_IN_DATABASE', 201,
     'Surrogate model not in database -- exit, FireWorks initialises it from its module'),
    ('PARAMETERS_NOT_VALID', 202,
     'Surrogate model has no valid fitted parameters -- exit, FireWorks runs its initialisation workflow'),
    ('INDEX_SET_NOT_IN_DATABASE', 401,
     'Index set not in database -- is the model package on MODENA_PATH?'),
)

# Bind each name at module level.  Done from the table rather than written out
# a second time, so the two cannot disagree.
globals().update({name: value for name, value, _desc in STATUS_CODES})

__all__ = [name for name, _value, _desc in STATUS_CODES] + ['STATUS_CODES']
