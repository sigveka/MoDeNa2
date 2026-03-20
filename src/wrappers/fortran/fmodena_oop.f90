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
!    2014-2026 MoDeNa Consortium, All rights reserved.
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

!>
!! @file
!! Fortran 2003 OOP wrapper for the MoDeNa surrogate-model interface.
!!
!! Provides a single derived type, `modena_model`, that encapsulates the
!! C handles and exposes type-bound procedures, removing all manual pointer
!! management from user code.
!!
!! @par Typical usage
!! @code{.f90}
!!     use fmodena_oop
!!     implicit none
!!
!!     type(modena_model) :: m
!!     integer(c_size_t)  :: Dpos, p0pos
!!     integer(c_int)     :: ret
!!
!!     call m%init("flowRate")
!!
!!     Dpos  = m%input_pos("D")
!!     p0pos = m%input_pos("p0")
!!     call m%check()
!!
!!     ! simulation loop
!!     call m%set(Dpos,  D)
!!     call m%set(p0pos, p0)
!!     ret  = m%call()
!!     if (ret /= 0) call exit(ret)
!!     mdot = m%get_output(0_c_size_t)
!!
!!     ! m is destroyed automatically by the Fortran finalizer
!! @endcode
!!
!! @author Sigve Karolius
!! @copyright  2014-2026, MoDeNa Project. GNU Public License.
!! @defgroup Fortran_OOP_interface_library

!> @{
module fmodena_oop

    use iso_c_binding
    use fmodena

    implicit none

    private
    public :: modena_model

    !> Fortran 2003 derived type wrapping a MoDeNa surrogate model.
    !!
    !! All three C handles (model, inputs, outputs) are owned by this type and
    !! are released automatically when the variable goes out of scope via the
    !! `final` procedure (Fortran 2003).
    type :: modena_model

        private

        type(c_ptr) :: model_   = c_null_ptr !< modena_model_t*
        type(c_ptr) :: inputs_  = c_null_ptr !< modena_inputs_t*
        type(c_ptr) :: outputs_ = c_null_ptr !< modena_outputs_t*

    contains

        !> Initialise the model from the database.
        procedure :: init       => modena_model_init

        !> Look up the position of an input variable by name.
        procedure :: input_pos  => modena_model_input_pos

        !> Look up the position of an output variable by name.
        procedure :: output_pos => modena_model_output_pos

        !> Assert that all input/output positions have been queried.
        procedure :: check      => modena_model_check

        !> Set an input variable value at a cached position.
        procedure :: set        => modena_model_set

        !> Get an output variable value at a cached position.
        procedure :: get_output => modena_model_get_output

        !> Call the surrogate model.  Returns the C return code.
        procedure :: call       => modena_model_call_oop

        !> Finaliser — releases all C resources automatically.
        final :: modena_model_final

    end type modena_model

contains

    ! ---------------------------------------------------------------------- !

    !> Fetch model @p name from the MoDeNa database and allocate the
    !! corresponding input and output vectors.
    subroutine modena_model_init(self, name)
        class(modena_model), intent(inout) :: self
        character(len=*),    intent(in)    :: name

        self%model_   = modena_model_new(trim(name) // c_null_char)
        self%inputs_  = modena_inputs_new(self%model_)
        self%outputs_ = modena_outputs_new(self%model_)

    end subroutine modena_model_init

    ! ---------------------------------------------------------------------- !

    !> Return the argument position of input variable @p name.
    !! Cache the result before the time-step loop and pass it to `set`.
    function modena_model_input_pos(self, name) result(pos)
        class(modena_model), intent(in) :: self
        character(len=*),    intent(in) :: name
        integer(c_size_t) :: pos

        pos = modena_model_inputs_argPos(self%model_, trim(name) // c_null_char)

    end function modena_model_input_pos

    ! ---------------------------------------------------------------------- !

    !> Return the argument position of output variable @p name.
    function modena_model_output_pos(self, name) result(pos)
        class(modena_model), intent(in) :: self
        character(len=*),    intent(in) :: name
        integer(c_size_t) :: pos

        pos = modena_model_outputs_argPos(self%model_, trim(name) // c_null_char)

    end function modena_model_output_pos

    ! ---------------------------------------------------------------------- !

    !> Assert that every input/output position has been queried.
    !! Call once after all `input_pos` / `output_pos` calls.
    subroutine modena_model_check(self)
        class(modena_model), intent(in) :: self

        call modena_model_argPos_check(self%model_)

    end subroutine modena_model_check

    ! ---------------------------------------------------------------------- !

    !> Set the input variable at position @p pos to @p val.
    subroutine modena_model_set(self, pos, val)
        class(modena_model), intent(inout) :: self
        integer(c_size_t),   intent(in)    :: pos
        real(c_double),      intent(in)    :: val

        call modena_inputs_set(self%inputs_, pos, val)

    end subroutine modena_model_set

    ! ---------------------------------------------------------------------- !

    !> Return the value of output variable at position @p pos.
    function modena_model_get_output(self, pos) result(val)
        class(modena_model), intent(in) :: self
        integer(c_size_t),   intent(in) :: pos
        real(c_double) :: val

        val = modena_outputs_get(self%outputs_, pos)

    end function modena_model_get_output

    ! ---------------------------------------------------------------------- !

    !> Call the surrogate model.
    !!
    !! Returns the C return code:
    !!   - 0   success
    !!   - 100 parameters updated (OutOfBounds); retry the current time step
    !!   - 200 exit and restart the simulation
    !!   - 201 exit; no restart required
    function modena_model_call_oop(self) result(ret)
        class(modena_model), intent(inout) :: self
        integer(c_int) :: ret

        ret = modena_model_call(self%model_, self%inputs_, self%outputs_)

    end function modena_model_call_oop

    ! ---------------------------------------------------------------------- !

    !> Fortran 2003 finaliser — automatically releases all C resources when
    !! the variable goes out of scope.  Users do not call this directly.
    subroutine modena_model_final(self)
        type(modena_model), intent(inout) :: self

        if (c_associated(self%model_)) then
            call modena_inputs_destroy (self%inputs_)
            call modena_outputs_destroy(self%outputs_)
            call modena_model_destroy  (self%model_)
            self%model_   = c_null_ptr
            self%inputs_  = c_null_ptr
            self%outputs_ = c_null_ptr
        end if

    end subroutine modena_model_final

end module fmodena_oop

!> @}

! *************************************************************************** !
