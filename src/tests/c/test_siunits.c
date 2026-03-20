/*
 * test_siunits.c
 *
 * Unit tests for the modena_siunits_t type and its associated functions:
 *
 *   modena_siunits_new()      -- allocates a siunits struct
 *   modena_siunits_destroy()  -- frees it
 *   modena_siunits_get()      -- reads one exponent  [NOT YET IMPLEMENTED]
 *
 * The six SI exponent indices are:
 *   0 = kg   (mass)
 *   1 = m    (length)
 *   2 = s    (time)
 *   3 = A    (electric current)
 *   4 = K    (thermodynamic temperature)
 *   5 = mol  (amount of substance)
 *
 * Known exponent vectors used below:
 *   Pa  = kg·m⁻¹·s⁻²  -> { 1, -1, -2,  0,  0,  0 }
 *   K   = K             -> { 0,  0,  0,  0,  1,  0 }
 *   dim = dimensionless -> { 0,  0,  0,  0,  0,  0 }
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>

/* Include only the header that declares modena_siunits_t.
 * inputsoutputs.h pulls in inline.h and <stddef.h> only — no Python.h. */
#include "inputsoutputs.h"

/* -------------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------------- */

static void set_exponents(modena_siunits_t *u, int e0, int e1, int e2,
                          int e3, int e4, int e5)
{
    u->exponents[0] = e0;
    u->exponents[1] = e1;
    u->exponents[2] = e2;
    u->exponents[3] = e3;
    u->exponents[4] = e4;
    u->exponents[5] = e5;
}

static int exponents_equal(const modena_siunits_t *a, const modena_siunits_t *b)
{
    return memcmp(a->exponents, b->exponents, 6 * sizeof(int)) == 0;
}

/* -------------------------------------------------------------------------
 * Tests
 * ------------------------------------------------------------------------- */

static void test_new_returns_non_null(void)
{
    modena_siunits_t *u = modena_siunits_new();
    assert(u != NULL);
    modena_siunits_destroy(u);
    printf("PASS  test_new_returns_non_null\n");
}

static void test_destroy_does_not_crash(void)
{
    modena_siunits_t *u = modena_siunits_new();
    modena_siunits_destroy(u);   /* must not crash or valgrind-report a leak */
    printf("PASS  test_destroy_does_not_crash\n");
}

static void test_exponents_are_writable(void)
{
    modena_siunits_t *u = modena_siunits_new();
    /* Pa = kg·m⁻¹·s⁻² */
    set_exponents(u, 1, -1, -2, 0, 0, 0);
    assert(u->exponents[0] ==  1);
    assert(u->exponents[1] == -1);
    assert(u->exponents[2] == -2);
    assert(u->exponents[3] ==  0);
    assert(u->exponents[4] ==  0);
    assert(u->exponents[5] ==  0);
    modena_siunits_destroy(u);
    printf("PASS  test_exponents_are_writable\n");
}

static void test_two_instances_are_independent(void)
{
    modena_siunits_t *pa = modena_siunits_new();
    modena_siunits_t *k  = modena_siunits_new();

    set_exponents(pa,  1, -1, -2, 0, 0, 0);  /* Pa  */
    set_exponents(k,   0,  0,  0, 0, 1, 0);  /* K   */

    assert(!exponents_equal(pa, k));
    assert(pa->exponents[0] ==  1);
    assert(k->exponents[4]  ==  1);

    modena_siunits_destroy(pa);
    modena_siunits_destroy(k);
    printf("PASS  test_two_instances_are_independent\n");
}

static void test_dimensionless_all_zeros(void)
{
    modena_siunits_t *u = modena_siunits_new();
    set_exponents(u, 0, 0, 0, 0, 0, 0);
    for (int i = 0; i < 6; i++)
    {
        assert(u->exponents[i] == 0);
    }
    modena_siunits_destroy(u);
    printf("PASS  test_dimensionless_all_zeros\n");
}

static void test_exponent_array_size(void)
{
    /* Ensure the struct has exactly 6 exponent slots.
     * sizeof(int[6]) == 6 * sizeof(int) */
    modena_siunits_t *u = modena_siunits_new();
    assert(sizeof(u->exponents) == 6 * sizeof(int));
    modena_siunits_destroy(u);
    printf("PASS  test_exponent_array_size\n");
}

/* -------------------------------------------------------------------------
 * modena_siunits_get() — declared in inputsoutputs.h but NOT YET implemented
 * in inputsoutputs.c.  These tests are compiled out until the implementation
 * is added.  Remove the #if 0 / #endif once the function body exists.
 * ------------------------------------------------------------------------- */
#if 0
static void test_siunits_get_reads_exponent(void)
{
    modena_siunits_t *u = modena_siunits_new();
    set_exponents(u, 1, -1, -2, 0, 0, 0);   /* Pa */
    assert(modena_siunits_get(u, 0) ==  1);
    assert(modena_siunits_get(u, 1) == -1);
    assert(modena_siunits_get(u, 2) == -2);
    assert(modena_siunits_get(u, 5) ==  0);
    modena_siunits_destroy(u);
    printf("PASS  test_siunits_get_reads_exponent\n");
}
#endif   /* modena_siunits_get not yet implemented */

/* -------------------------------------------------------------------------
 * main
 * ------------------------------------------------------------------------- */

int main(void)
{
    printf("-- modena C unit tests: siunits --\n");

    test_new_returns_non_null();
    test_destroy_does_not_crash();
    test_exponents_are_writable();
    test_two_instances_are_independent();
    test_dimensionless_all_zeros();
    test_exponent_array_size();

    printf("-- All siunits tests passed. --\n");
    return 0;
}
