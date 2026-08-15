# Tests for the modena R wrapper.
#
# Unit tests (no libmodena required) verify the R-level structure: that the
# Modena class exists and has the expected interface.
#
# Integration tests (require libmodena + MongoDB) are tagged with
# skip_if_no_libmodena() and are skipped automatically in environments where
# libmodena.so is not available.

library(modena)

# ── Helper ──────────────────────────────────────────────────────────────── #

skip_if_no_libmodena <- function() {
    lib_dir <- Sys.getenv("MODENA_LIB_DIR", unset = "")
    if (nchar(lib_dir) > 0L) {
        lib_path <- file.path(lib_dir, "libmodena.so")
        if (!file.exists(lib_path))
            skip(paste("libmodena.so not found at", lib_path))
        return(invisible(NULL))
    }
    result <- tryCatch({
        raw <- system(
            "python3 -c \"import modena; print(modena.MODENA_LIB_DIR)\"",
            intern = TRUE, ignore.stderr = TRUE
        )
        trimws(tail(raw, 1L))
    }, error = function(e) "")
    if (nchar(result) == 0L || !file.exists(file.path(result, "libmodena.so")))
        skip("libmodena not available (set MODENA_LIB_DIR or install MoDeNa)")
}

# ── Unit tests: package structure ───────────────────────────────────────── #

test_that("Modena class generator exists and is a reference class generator", {
    expect_true(exists("Modena"))
    expect_true(is(Modena, "envRefClass"))
})

test_that("Modena class has expected methods", {
    expected <- c(
        "initialize", "input_pos", "output_pos", "check",
        "set", "output", "call",
        "inputs_size", "outputs_size", "parameters_size",
        "inputs_names", "outputs_names", "parameters_names",
        # Phase 3 named-parameter accessors
        "parameters", "get_parameter",
        "show"
    )
    defined <- ls(Modena$def@refMethods)
    for (m in expected)
        expect_true(m %in% defined,
                    info = paste("method not found:", m))
})

test_that("Modena class has expected fields", {
    fields <- names(Modena$def@fieldClasses)
    expect_true(".model"   %in% fields)
    expect_true(".inputs"  %in% fields)
    expect_true(".outputs" %in% fields)
})

test_that("Modena$new() requires a character id", {
    skip_if_no_libmodena()
    expect_error(Modena$new(123L),   regexp = "character")
    expect_error(Modena$new(c("a", "b")), regexp = "character")
})

# ── Integration tests: require libmodena + live MongoDB ─────────────────── #

test_that("Modena$new() errors on an unknown model id", {
    skip_if_no_libmodena()
    expect_error(
        Modena$new("__nonexistent_model_xyz__"),
        regexp = "not found"
    )
})

test_that("model reports non-zero inputs/outputs after loading flowRate", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({
            m <- Modena$new("flowRate"); FALSE
        }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m <- Modena$new("flowRate")
    expect_gt(m$inputs_size(),  0L)
    expect_gt(m$outputs_size(), 0L)
})

test_that("input_pos / output_pos return non-negative integers for flowRate", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m      <- Modena$new("flowRate")
    pos_D  <- m$input_pos("D")
    pos_q  <- m$output_pos("flowRate")
    expect_type(pos_D, "integer")
    expect_type(pos_q, "integer")
    expect_gte(pos_D, 0L)
    expect_gte(pos_q, 0L)
})

test_that("inputs_names / outputs_names return character vectors for flowRate", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m <- Modena$new("flowRate")
    expect_type(m$inputs_names(),  "character")
    expect_type(m$outputs_names(), "character")
    expect_true("D" %in% m$inputs_names())
    expect_true("flowRate" %in% m$outputs_names())
})

test_that("$call() returns an integer return code", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m     <- Modena$new("flowRate")
    pos_D      <- m$input_pos("D")
    pos_rho0   <- m$input_pos("rho0")
    pos_p0     <- m$input_pos("p0")
    pos_p1Byp0 <- m$input_pos("p1Byp0")
    m$check()

    m$set(pos_D,      0.01)
    m$set(pos_rho0,   3.4)
    m$set(pos_p0,     2.8e5)
    m$set(pos_p1Byp0, 0.03)

    ret <- m$call()
    expect_type(ret, "integer")
    expect_true(ret %in% c(0L, 100L, 200L, 201L))
})

test_that("$parameters() returns a named numeric vector for flowRate", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m <- Modena$new("flowRate")
    vals <- m$parameters()
    # Every fitted parameter is a finite double keyed by its declared name.
    expect_type(vals, "double")
    expect_true(!is.null(names(vals)))
    expect_setequal(names(vals), m$parameters_names())
    expect_true(all(is.finite(vals)))
})

test_that("$get_parameter() returns the value of a specific parameter", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m <- Modena$new("flowRate")
    name <- m$parameters_names()[1L]
    val  <- m$get_parameter(name)
    expect_type(val, "double")
    expect_true(is.finite(val))
    # Consistent with the named-vector accessor
    expect_equal(val, unname(m$parameters()[[name]]))
})

test_that("$get_parameter() errors on unknown parameter name", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m <- Modena$new("flowRate")
    expect_error(m$get_parameter("__no_such_parameter__"),
                 regexp = "unknown parameter")
})

test_that("$output() returns a finite numeric after a successful call", {
    skip_if_no_libmodena()
    skip_if(
        tryCatch({ m <- Modena$new("flowRate"); FALSE }, error = function(e) TRUE),
        "flowRate model not in database"
    )
    m <- Modena$new("flowRate")
    m$set(m$input_pos("D"),      0.01)
    m$set(m$input_pos("rho0"),   3.4)
    m$set(m$input_pos("p0"),     2.8e5)
    m$set(m$input_pos("p1Byp0"), 0.03)
    m$check()

    ret <- m$call()
    if (ret == 0L) {
        val <- m$output(m$output_pos("flowRate"))
        expect_type(val, "double")
        expect_true(is.finite(val))
    } else {
        skip(paste("model call returned", ret, "— skipping output check"))
    }
})
