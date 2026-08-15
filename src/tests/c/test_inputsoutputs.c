/*
 * test_inputsoutputs.c
 *
 * Unit tests for the pure-C allocators and inline set/get helpers:
 *
 *   modena_inputs_new / modena_inputs_destroy      -- alloc + free
 *   modena_outputs_new / modena_outputs_destroy    -- alloc + free
 *   modena_inputs_set / modena_inputs_get          -- roundtrip
 *   modena_outputs_get                             -- direct-array read
 *
 * These functions read only inputs_internal_size / outputs_size from the
 * passed-in modena_model_t, so we construct a bare zero-initialised struct
 * on the heap and populate just those two fields.  Python is not
 * initialised — the PyObject_HEAD prefix carries garbage-but-unused nulls.
 */

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <Python.h>            /* for PyObject_HEAD in modena_model_t */
#include "inputsoutputs.h"
#include "model.h"

/* -------------------------------------------------------------------------
 * Helper — heap-allocate a bare modena_model_t sized for tests
 * ------------------------------------------------------------------------- */

static modena_model_t *fake_model(size_t inputs_internal, size_t outputs)
{
    modena_model_t *m = calloc(1, sizeof(modena_model_t));
    assert(m != NULL);
    m->inputs_internal_size = inputs_internal;
    m->outputs_size = outputs;
    return m;
}

/* -------------------------------------------------------------------------
 * Tests — modena_inputs_new / destroy
 * ------------------------------------------------------------------------- */

static void test_inputs_new_allocates_correct_size(void)
{
    modena_model_t *m = fake_model(4, 2);
    modena_inputs_t *in = modena_inputs_new(m);
    assert(in != NULL);
    assert(in->inputs != NULL);
    assert(in->inherited_inputs == NULL);   /* per contract, not allocated */

    /* Writing past index 3 would corrupt heap — trust malloc size == 4*sizeof(double) */
    for (size_t i = 0; i < 4; i++) in->inputs[i] = 0.0;

    modena_inputs_destroy(in);
    free(m);
    printf("PASS  test_inputs_new_allocates_correct_size\n");
}

static void test_inputs_destroy_null_inherited_is_safe(void)
{
    modena_model_t *m = fake_model(1, 1);
    modena_inputs_t *in = modena_inputs_new(m);
    /* inherited_inputs must be NULL after new(); destroy() must not crash */
    assert(in->inherited_inputs == NULL);
    modena_inputs_destroy(in);   /* free(NULL) is well-defined */
    free(m);
    printf("PASS  test_inputs_destroy_null_inherited_is_safe\n");
}

static void test_outputs_new_allocates_correct_size(void)
{
    modena_model_t *m = fake_model(2, 3);
    modena_outputs_t *out = modena_outputs_new(m);
    assert(out != NULL);
    assert(out->outputs != NULL);
    for (size_t i = 0; i < 3; i++) out->outputs[i] = 0.0;
    modena_outputs_destroy(out);
    free(m);
    printf("PASS  test_outputs_new_allocates_correct_size\n");
}

/* -------------------------------------------------------------------------
 * Tests — inline set/get roundtrip (from inline.h via inputsoutputs.h)
 * ------------------------------------------------------------------------- */

static void test_inputs_set_get_roundtrip(void)
{
    modena_model_t *m = fake_model(3, 1);
    modena_inputs_t *in = modena_inputs_new(m);

    modena_inputs_set(in, 0, 3.14);
    modena_inputs_set(in, 1, -2.5);
    modena_inputs_set(in, 2, 1e6);

    /* Values read back must equal what was written */
    assert(modena_inputs_get(in, 0) == 3.14);
    assert(modena_inputs_get(in, 1) == -2.5);
    assert(modena_inputs_get(in, 2) == 1e6);

    modena_inputs_destroy(in);
    free(m);
    printf("PASS  test_inputs_set_get_roundtrip\n");
}

static void test_outputs_get_reads_from_array(void)
{
    modena_model_t *m = fake_model(1, 2);
    modena_outputs_t *out = modena_outputs_new(m);
    out->outputs[0] = 42.0;
    out->outputs[1] = -7.5;
    assert(modena_outputs_get(out, 0) == 42.0);
    assert(modena_outputs_get(out, 1) == -7.5);
    modena_outputs_destroy(out);
    free(m);
    printf("PASS  test_outputs_get_reads_from_array\n");
}

static void test_inputs_overwrite_last_write_wins(void)
{
    /* Multiple writes to the same slot must yield the last value. */
    modena_model_t *m = fake_model(1, 1);
    modena_inputs_t *in = modena_inputs_new(m);
    modena_inputs_set(in, 0, 1.0);
    modena_inputs_set(in, 0, 2.0);
    modena_inputs_set(in, 0, 3.0);
    assert(modena_inputs_get(in, 0) == 3.0);
    modena_inputs_destroy(in);
    free(m);
    printf("PASS  test_inputs_overwrite_last_write_wins\n");
}

/* -------------------------------------------------------------------------
 * Tests — allocations are independent per instance
 * ------------------------------------------------------------------------- */

static void test_two_inputs_instances_are_independent(void)
{
    modena_model_t *m = fake_model(2, 1);
    modena_inputs_t *a = modena_inputs_new(m);
    modena_inputs_t *b = modena_inputs_new(m);

    modena_inputs_set(a, 0, 1.0); modena_inputs_set(a, 1, 2.0);
    modena_inputs_set(b, 0, 10.0); modena_inputs_set(b, 1, 20.0);

    /* Writes to b must not affect a */
    assert(modena_inputs_get(a, 0) == 1.0);
    assert(modena_inputs_get(a, 1) == 2.0);
    assert(modena_inputs_get(b, 0) == 10.0);
    assert(modena_inputs_get(b, 1) == 20.0);

    modena_inputs_destroy(a);
    modena_inputs_destroy(b);
    free(m);
    printf("PASS  test_two_inputs_instances_are_independent\n");
}

/* -------------------------------------------------------------------------
 * main
 * ------------------------------------------------------------------------- */

int main(void)
{
    printf("-- modena C unit tests: inputs/outputs --\n");

    test_inputs_new_allocates_correct_size();
    test_inputs_destroy_null_inherited_is_safe();
    test_outputs_new_allocates_correct_size();
    test_inputs_set_get_roundtrip();
    test_outputs_get_reads_from_array();
    test_inputs_overwrite_last_write_wins();
    test_two_inputs_instances_are_independent();

    printf("-- All inputs/outputs tests passed. --\n");
    return 0;
}
