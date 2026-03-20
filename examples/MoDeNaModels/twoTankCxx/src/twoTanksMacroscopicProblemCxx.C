/**
@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2016 MoDeNa Consortium, All rights reserved.

License
    This file is part of Modena.

    Modena is free software; you can redistribute it and/or modify it under
    the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 3 of the License, or (at your option)
    any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.

@endcond
@file
Two-tank problem solved using the MoDeNa C++ wrapper.

This example is the C++ counterpart of twoTank/src/twoTanksMacroscopicProblem.C.
It shows how the modena::Model class from <modena/modena.hpp> replaces manual
C handle and error-code management with RAII and exceptions:

  - The model, input vector and output vector are owned by one object whose
    destructor releases all resources automatically.
  - modena_error_occurred() polling is replaced by catch blocks.
  - Input positions are cached once before the loop for zero-overhead access
    inside the hot path.

@author     Henrik Rusche
@author     Sigve Karolius
@copyright  2014-2016, MoDeNa Project. GNU Public License.
@ingroup    twoTankCxx
*/

#include <iostream>
#include <modena/modena.hpp>

int
main(int argc, char *argv[])
{
    const double D = 0.01;

    double p0 = 3e5;
    double p1 = 10000;
    double V0 = 0.1;
    double V1 = 1;
    double T  = 300;

    double t = 0.0;
    const double deltat = 1e-3;
    const double tend   = 5.5;

    double m0 = p0*V0/287.1/T;
    double m1 = p1*V1/287.1/T;

    double rho0 = m0/V0;
    double rho1 = m1/V1;

    try
    {
        // Instantiate the model.  The constructor fetches the model from the
        // MoDeNa database and allocates the input/output vectors.
        modena::Model model("flowRate");

        // Print model metadata.
        std::cout << "inputs:\n";
        for (const auto& n : model.inputs_names())
            std::cout << "  " << n << '\n';

        std::cout << "outputs:\n";
        for (const auto& n : model.outputs_names())
            std::cout << "  " << n << '\n';

        std::cout << "parameters:\n";
        for (const auto& n : model.parameters_names())
            std::cout << "  " << n << '\n';

        // Cache argument positions once before the loop.  This avoids a
        // string lookup on every iteration and allows modena to verify that
        // all declared inputs have been addressed.
        const std::size_t Dpos      = model.input_pos("D");
        const std::size_t rho0Pos   = model.input_pos("rho0");
        const std::size_t p0Pos     = model.input_pos("p0");
        const std::size_t p1Byp0Pos = model.input_pos("p1Byp0");
        model.check();

        while (t + deltat < tend + 1e-10)
        {
            t += deltat;

            // Set the input vector using cached positions (fast path).
            if (p0 > p1)
            {
                model.set(Dpos,      D);
                model.set(rho0Pos,   rho0);
                model.set(p0Pos,     p0);
                model.set(p1Byp0Pos, p1/p0);
            }
            else
            {
                model.set(Dpos,      D);
                model.set(rho0Pos,   rho1);
                model.set(p0Pos,     p1);
                model.set(p1Byp0Pos, p0/p1);
            }

            // Call the surrogate model.
            // ParametersUpdated (ret==100): the surrogate was retrained
            // mid-call; skip the state update and retry this time step.
            try
            {
                model.call();
            }
            catch (const modena::ParametersUpdated&)
            {
                t -= deltat;   // stay at the same time step
                continue;
            }

            // Fetch result by position.
            const double mdot = model.output(0);

            if (p0 > p1)
            {
                m0 -= mdot*deltat;
                m1 += mdot*deltat;
            }
            else
            {
                m0 += mdot*deltat;
                m1 -= mdot*deltat;
            }

            rho0 = m0/V0;
            rho1 = m1/V1;
            p0   = m0/V0*287.1*T;
            p1   = m1/V1*287.1*T;

            std::cout
                << "t = "    << t
                << " rho0 = " << rho0
                << " p0 = "   << p0
                << " p1 = "   << p1
                << '\n';
        }
    }
    catch (const modena::Exception& e)
    {
        // All non-zero return codes (including ExitAndRestart / ExitNoRestart)
        // end up here.  Return the code to the workflow manager (lpad).
        return e.code;
    }

    return 0;
}

// ************************************************************************* //
