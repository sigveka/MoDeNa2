# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# THE definition of the MoDeNa workflow protocol status codes.
#
# These numbers used to be written out in five languages plus the docs, and
# every copy drifted independently: "201 = clean exit" survived in six
# documents while handleReturnCode() had always treated 201 as "model needs
# initialising".  Add a code here and every binding picks it up.
#
# Format:  NAME|VALUE|DESCRIPTION
#   NAME         bare; each generator applies its own prefix
#                (MODENA_ for C/Fortran/R, none for Python/MATLAB)
#   DESCRIPTION  one line.  Used as the doc comment in every language and as
#                the modena_error_message() text.  May not contain '|' (the
#                field separator) or ';' -- CMake splits lists on semicolons,
#                so one inside a description silently shreds the entry.
#
# Consumed by modena_status_block(), below, which renders the list into
# whichever language a template asks for.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# Read the table out of the Python module rather than restating it here.
# Python is where the codes are produced (SurrogateModel.exception*() returns
# them, handleReturnCode() dispatches on them), so it is the source; this file
# only renders it into the languages that cannot import Python.
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c
        "import sys; sys.path.insert(0, sys.argv[1]); import _status_codes as s; print(chr(10).join('%s|%d|%s' % c for c in s.STATUS_CODES))"
        "${CMAKE_CURRENT_LIST_DIR}/python"
    OUTPUT_VARIABLE _status_raw
    RESULT_VARIABLE _status_rc
    ERROR_VARIABLE  _status_err
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(NOT _status_rc EQUAL 0)
    message(FATAL_ERROR
        "Could not read src/python/_status_codes.py:\n${_status_err}")
endif()
string(REPLACE "\n" ";" MODENA_STATUS_CODES "${_status_raw}")
list(LENGTH MODENA_STATUS_CODES _status_count)
if(_status_count LESS 1)
    message(FATAL_ERROR "src/python/_status_codes.py yielded no status codes")
endif()
message(STATUS "MoDeNa status codes: ${_status_count} read from _status_codes.py")

# modena_status_block(<out_var> <language>)
#
# Render MODENA_STATUS_CODES as declarations in <language>, one per line, and
# store the result in <out_var>.  Templates embed it as @MODENA_STATUS_BLOCK@.
function(modena_status_block out_var language)
    set(_lines "")

    # Widest name, so the generated columns line up in every language.
    set(_width 0)
    foreach(_entry IN LISTS MODENA_STATUS_CODES)
        string(REPLACE "|" ";" _parts "${_entry}")
        list(GET _parts 0 _name)
        string(LENGTH "${_name}" _len)
        if(_len GREATER _width)
            set(_width ${_len})
        endif()
    endforeach()
    if(language STREQUAL "c" OR language STREQUAL "fortran"
       OR language STREQUAL "r")
        math(EXPR _width "${_width} + 7")     # room for the MODENA_ prefix
    endif()

    list(LENGTH MODENA_STATUS_CODES _count)
    set(_i 0)
    foreach(_entry IN LISTS MODENA_STATUS_CODES)
        string(REPLACE "|" ";" _parts "${_entry}")
        list(GET _parts 0 _name)
        list(GET _parts 1 _value)
        list(GET _parts 2 _desc)
        math(EXPR _i "${_i} + 1")

        if(language STREQUAL "c" OR language STREQUAL "fortran"
           OR language STREQUAL "r")
            set(_sym "MODENA_${_name}")
        else()
            set(_sym "${_name}")
        endif()

        # Pad the symbol so the values align.
        set(_pad "${_sym}")
        string(LENGTH "${_pad}" _len)
        while(_len LESS _width)
            set(_pad "${_pad} ")
            string(LENGTH "${_pad}" _len)
        endwhile()

        if(language STREQUAL "c")
            set(_comma ",")
            if(_i EQUAL _count)
                set(_comma "")
            endif()
            list(APPEND _lines "    ${_pad} = ${_value}${_comma} /**< ${_desc} */")
        elseif(language STREQUAL "python")
            list(APPEND _lines "${_pad} = ${_value}  #: ${_desc}")
        elseif(language STREQUAL "fortran")
            list(APPEND _lines "    !> ${_desc}")
            list(APPEND _lines "    integer(c_int), parameter, public :: ${_pad} = ${_value}")
        elseif(language STREQUAL "matlab")
            list(APPEND _lines "        % ${_desc}")
            list(APPEND _lines "        ${_pad} = ${_value}")
        elseif(language STREQUAL "r")
            list(APPEND _lines "#' @rdname modena-status-codes")
            list(APPEND _lines "#' @export")
            list(APPEND _lines "${_pad} <- ${_value}L")
            list(APPEND _lines "")
        else()
            message(FATAL_ERROR "modena_status_block: unknown language '${language}'")
        endif()
    endforeach()

    string(REPLACE ";" "\n" _joined "${_lines}")
    set(${out_var} "${_joined}" PARENT_SCOPE)
endfunction()

# modena_status_message_table(<out_var>)
#
# Render the C initialiser rows for modena_errordesc[], so the human-readable
# text lives with the code it describes rather than in a second list.
function(modena_status_message_table out_var)
    set(_lines "")
    foreach(_entry IN LISTS MODENA_STATUS_CODES)
        string(REPLACE "|" ";" _parts "${_entry}")
        list(GET _parts 0 _name)
        list(GET _parts 2 _desc)
        list(APPEND _lines "    { MODENA_${_name}, \"${_desc}\" },")
    endforeach()
    string(REPLACE ";" "\n" _joined "${_lines}")
    set(${out_var} "${_joined}" PARENT_SCOPE)
endfunction()

# modena_status_exports(<out_var>)
#
# Render the R NAMESPACE export() lines.  Generated because NAMESPACE is not
# roxygen-built here, so adding a code would otherwise mean remembering to
# export it by hand -- exactly the manual step this file exists to remove.
function(modena_status_exports out_var)
    set(_lines "")
    foreach(_entry IN LISTS MODENA_STATUS_CODES)
        string(REPLACE "|" ";" _parts "${_entry}")
        list(GET _parts 0 _name)
        list(APPEND _lines "export(MODENA_${_name})")
    endforeach()
    string(REPLACE ";" "\n" _joined "${_lines}")
    set(${out_var} "${_joined}" PARENT_SCOPE)
endfunction()
