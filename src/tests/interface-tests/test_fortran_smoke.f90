!
! test_fortran_smoke.f90
!
! Smoke test for the Fortran 2003 OOP wrapper (fmodena_oop).
!
! Loads the `flowRate` surrogate model, evaluates it at one known-good
! point, asserts the resulting mass flow rate is finite and positive.
! Same coverage as test_cpp_smoke.C but via the Fortran binding.
!
! Requires the `flowRate` model to be initialized in the MongoDB pointed
! to by MODENA_URI (default mongodb://localhost:27017/test).  If missing,
! init raises modena_ParametersNotValid / modena_DoesNotExist and the
! process exits with a non-zero code — CTest catches that.
!
program test_fortran_smoke

    use fmodena_oop
    use iso_c_binding
    implicit none

    type(modena_model) :: m
    integer(c_size_t)  :: Dpos, rho0Pos, p0Pos, p1Byp0Pos, mdotPos
    integer(c_int)     :: ret
    real(c_double)     :: mdot

    ! ── Load ────────────────────────────────────────────────────────────
    call m%init("flowRate")

    ! ── Cache positions ────────────────────────────────────────────────
    Dpos      = m%input_pos("D")
    rho0Pos   = m%input_pos("rho0")
    p0Pos     = m%input_pos("p0")
    p1Byp0Pos = m%input_pos("p1Byp0")
    mdotPos   = m%output_pos("flowRate")
    call m%check()

    ! ── Evaluate at a known-good point ─────────────────────────────────
    call m%set(Dpos,      0.01_c_double)
    call m%set(rho0Pos,   3.4_c_double)
    call m%set(p0Pos,     3.0e5_c_double)
    call m%set(p1Byp0Pos, 0.03_c_double)

    ret = m%call()
    if (ret /= 0) then
        write(0,*) "modena_model_call returned non-zero: ", ret
        call exit(1)
    end if

    mdot = m%get_output(mdotPos)

    ! ── Assertions ─────────────────────────────────────────────────────
    if (mdot /= mdot) then                   ! NaN check via self-inequality
        write(0,*) "flowRate output is NaN"
        call exit(1)
    end if
    if (mdot <= 0.0_c_double) then
        write(0,*) "flowRate output must be positive, got ", mdot
        call exit(1)
    end if
    if (mdot < 1.0e-4_c_double .or. mdot > 1.0_c_double) then
        write(0,*) "flowRate output out of loose range [1e-4, 1.0]: ", mdot
        call exit(1)
    end if

    print '(A, ES12.5, A)', &
        "PASS  test_fortran_smoke  (flowRate mdot = ", mdot, " kg/s)"

    ! m destroyed automatically by the Fortran finalizer

end program test_fortran_smoke
