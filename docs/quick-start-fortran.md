# Quick-Start — Calling MoDeNa Models from Fortran

This guide covers the Fortran 2003 OOP wrapper (`fmodena_oop`).  It provides
a single derived type `modena_model` that owns all C handles and releases them
automatically via a `final` procedure when the variable goes out of scope.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `libmodena` | Installed by MoDeNa's CMake build |
| gfortran ≥ 4.9 | Fortran 2003 `final` procedures required |
| CMake ≥ 3.0 | For `find_package(MODENA)` |
| MongoDB running | `MODENA_URI` must point to a populated database |

```bash
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
export PYTHONPATH="${PYTHONPATH}:${HOME}/lib/python3.10/site-packages"
```

---

## CMake integration

```cmake
cmake_minimum_required(VERSION 3.0)
project(myApp Fortran)

find_package(MODENA REQUIRED)

add_executable(myApp main.f90)
target_link_libraries(myApp MODENA::fmodena_oop)
```

---

## The pattern

```
1. Declare     type(modena_model) :: m
2. Init once   call m%init("id")
3. Cache once  pos = m%input_pos("name")   — before the loop
4. Per step    m%set → m%call → m%get_output
5. Finalise    automatic when m goes out of scope
```

---

## Return codes

`m%call()` returns an `integer(c_int)`:

| Code | Meaning | Required action |
|------|---------|----------------|
| `0` | Success | Continue normally |
| `100` | Surrogate retrained | Decrement time, retry step (`cycle`) |
| `200` | Exit and restart | `call exit(ret)` — FireWorks relaunches |
| `201` | Clean exit | `call exit(ret)` — workflow complete |

---

## Example — twoTanks

Adapted from
`examples/MoDeNaModels/twoTankFortran/src/twoTanksMacroscopicProblemFortran.f90`.

```fortran
program twoTanks
    use iso_c_binding
    use fmodena_oop
    implicit none

    integer, parameter :: dp = selected_real_kind(15)

    ! Physical constants and initial conditions
    real(dp), parameter :: D      = 0.01_dp
    real(dp), parameter :: R      = 287.1_dp
    real(dp), parameter :: T_gas  = 300.0_dp
    real(dp), parameter :: V0     = 0.1_dp,   V1     = 1.0_dp
    real(dp), parameter :: deltat = 1.0e-3_dp, tend  = 5.5_dp

    real(dp) :: p0 = 3.0e5_dp, p1 = 1.0e4_dp
    real(dp) :: m0, m1, rho0, rho1, mdot, t

    ! ── 1. Declare the model variable ──────────────────────────────────────
    type(modena_model)  :: model
    integer(c_size_t)   :: pos_D, pos_rho0, pos_p0, pos_p1p0
    integer(c_int)      :: ret

    m0   = p0 * V0 / R / T_gas
    m1   = p1 * V1 / R / T_gas
    rho0 = m0 / V0
    rho1 = m1 / V1
    t    = 0.0_dp

    ! ── 2. Initialise — loads from database, allocates I/O vectors ─────────
    call model%init("flowRate")

    ! ── 3. Cache input positions (once, before the loop) ───────────────────
    pos_D    = model%input_pos("D")
    pos_rho0 = model%input_pos("rho0")
    pos_p0   = model%input_pos("p0")
    pos_p1p0 = model%input_pos("p1Byp0")
    call model%check()   ! verify every declared input was queried

    ! ── 4. Time-step loop ──────────────────────────────────────────────────
    do while (t + deltat < tend + 1.0e-10_dp)

        t = t + deltat

        if (p0 > p1) then
            call model%set(pos_D,    D)
            call model%set(pos_rho0, rho0)
            call model%set(pos_p0,   p0)
            call model%set(pos_p1p0, p1 / p0)
        else
            call model%set(pos_D,    D)
            call model%set(pos_rho0, rho1)
            call model%set(pos_p0,   p1)
            call model%set(pos_p1p0, p0 / p1)
        end if

        ret = model%call()

        if (ret == 100) then
            t = t - deltat   ! surrogate retrained — retry this step
            cycle
        else if (ret /= 0) then
            call exit(ret)   ! 200/201 — let FireWorks handle restart
        end if

        mdot = model%get_output(0_c_size_t)

        if (p0 > p1) then
            m0 = m0 - mdot * deltat
            m1 = m1 + mdot * deltat
        else
            m0 = m0 + mdot * deltat
            m1 = m1 - mdot * deltat
        end if

        rho0 = m0 / V0;   p0 = rho0 * R * T_gas
        rho1 = m1 / V1;   p1 = rho1 * R * T_gas

        write(*, '(A,F7.4,A,F8.1,A,F8.1)') &
            't=', t, '  p0=', p0, '  p1=', p1

    end do

    ! ── 5. model finaliser runs automatically here ─────────────────────────
    call exit(0)

end program twoTanks
```

---

## Notes on `c_size_t` positions

`input_pos` and `output_pos` return `integer(c_size_t)`.  Always pass
positions as `c_size_t` literals or variables to avoid implicit conversion
warnings:

```fortran
! Declare positions as c_size_t
integer(c_size_t) :: pos_D

! Use c_size_t literal when calling get_output by index
mdot = model%get_output(0_c_size_t)
```

---

## Low-level bindings

`fmodena_oop` wraps the lower-level `fmodena` module which provides direct
Fortran bindings to every C function via `iso_c_binding`.  Use `fmodena`
directly only if you need functionality not exposed by the OOP wrapper:

```fortran
use fmodena   ! direct C bindings
use fmodena_oop   ! recommended OOP wrapper
```
