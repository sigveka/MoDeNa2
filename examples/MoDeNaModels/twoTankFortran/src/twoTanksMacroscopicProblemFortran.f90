!
!   ooo        ooooo           oooooooooo.             ooooo      ooo
!   `88.       .888'           `888'   `Y8b            `888b.     `8'
!    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
!    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
!    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
!    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
!   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o
!
!Copyright
!    2014-2016 MoDeNa Consortium, All rights reserved.
!
!License
!    This file is part of Modena.
!
!    Modena is free software; you can redistribute it and/or modify it under
!    the terms of the GNU General Public License as published by the Free
!    Software Foundation, either version 3 of the License, or (at your option)
!    any later version.
!
!    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
!    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
!    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
!    details.
!
!    You should have received a copy of the GNU General Public License along
!    with Modena.  If not, see <http://www.gnu.org/licenses/>.
!
!Description
!    Two-tank problem solved using the MoDeNa Fortran OOP wrapper.
!
!    This example is the Fortran counterpart of
!    twoTank/src/twoTanksMacroscopicProblem.C. It shows how the modena_model
!    derived type from the fmodena_oop module replaces raw C pointer management:
!
!      - model, inputs and outputs are encapsulated in a single derived type
!        whose finaliser releases all C resources automatically.
!      - Input positions are cached once before the loop via m%input_pos().
!      - The simulation loop calls m%set() / m%call() / m%get_output().
!
!Authors
!    Henrik Rusche
!    Pavel Ferkl
!    Sigve Karolius
!
program twoTanksMacroscopicProblemFortran

    use iso_c_binding
    use fmodena_oop

    implicit none

    integer, parameter :: dp = selected_real_kind(15)

    real(dp), parameter :: D      = 0.01_dp
    real(dp), parameter :: deltat = 1.0e-3_dp
    real(dp), parameter :: tend   = 5.5_dp

    real(dp) :: p0   = 3.0e5_dp
    real(dp) :: p1   = 10000.0_dp
    real(dp) :: V0   = 0.1_dp
    real(dp) :: V1   = 1.0_dp
    real(dp) :: temp = 300.0_dp

    real(dp) :: t    = 0.0_dp
    real(dp) :: m0, m1, rho0, rho1, mdot

    integer(c_int) :: ret

    ! The model owns all three C handles.  They are released automatically
    ! when the variable goes out of scope (Fortran 2003 finaliser).
    type(modena_model) :: model

    ! Cached argument positions — resolved once, used every iteration.
    integer(c_size_t) :: Dpos, rho0Pos, p0Pos, p1Byp0Pos

    m0   = p0*V0/287.1_dp/temp
    m1   = p1*V1/287.1_dp/temp
    rho0 = m0/V0
    rho1 = m1/V1

    ! Fetch the model from the MoDeNa database and allocate I/O vectors.
    call model%init("flowRate")

    ! Cache input positions and verify all inputs have been addressed.
    Dpos      = model%input_pos("D")
    rho0Pos   = model%input_pos("rho0")
    p0Pos     = model%input_pos("p0")
    p1Byp0Pos = model%input_pos("p1Byp0")
    call model%check()

    do while (t + deltat < tend + 1.0e-10_dp)

        t = t + deltat

        if (p0 > p1) then
            call model%set(Dpos,      D)
            call model%set(rho0Pos,   rho0)
            call model%set(p0Pos,     p0)
            call model%set(p1Byp0Pos, p1/p0)
        else
            call model%set(Dpos,      D)
            call model%set(rho0Pos,   rho1)
            call model%set(p0Pos,     p1)
            call model%set(p1Byp0Pos, p0/p1)
        end if

        ! Call the surrogate.  Non-zero return codes signal workflow events:
        !   100 = parameters updated (OutOfBounds) — retry the time step
        !   200 = exit and restart the simulation
        !   201 = exit; no restart required
        ret = model%call()

        if (ret == 100) then
            ! Model was retrained mid-step; discard this result and retry.
            t = t - deltat
            cycle
        else if (ret /= 0) then
            ! Pass the workflow exit code to lpad / FireWorks.
            call exit(ret)
        end if

        mdot = model%get_output(0_c_size_t)

        if (p0 > p1) then
            m0 = m0 - mdot*deltat
            m1 = m1 + mdot*deltat
        else
            m0 = m0 + mdot*deltat
            m1 = m1 - mdot*deltat
        end if

        rho0 = m0/V0
        rho1 = m1/V1
        p0   = m0/V0*287.1_dp*temp
        p1   = m1/V1*287.1_dp*temp

        write(*,*) "t = ", t, " rho0 = ", rho0, " p0 = ", p0, " p1 = ", p1

    end do

    ! model goes out of scope here; Fortran finaliser destroys it automatically.
    call exit(0)

end program twoTanksMacroscopicProblemFortran

! *************************************************************************** !
