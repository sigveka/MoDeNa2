/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright (C) 2011-2015 OpenFOAM Foundation
     \\/     M anipulation  |
-------------------------------------------------------------------------------
License
    This file is part of OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

Application
    modenaLaplacianFoam

Description
    Solves a simple Laplace equation, e.g. for thermal diffusion in a solid.
    When run with -MoDeNaRun the thermal diffusivity DT is evaluated via a
    MoDeNa surrogate model instead of the constant value in transportProperties.

\*---------------------------------------------------------------------------*/

#include "fvCFD.H"
#include "fvOptions.H"
#include "simpleControl.H"
#include <modena/modena.hpp>
#include <memory>

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

int main(int argc, char *argv[])
{
    argList::addBoolOption
    (
        "MoDeNaRun",
        "Perform Run Using MoDeNa Surrogate Models"
    );

    #include "setRootCase.H"

    const int MODENA_RUN = args.optionFound("MoDeNaRun") ? 1 : 0;

    #include "createTime.H"
    #include "createMesh.H"

    simpleControl simple(mesh);

    #include "createFields.H"

    // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

    Info<< "\nCalculating temperature distribution\n" << endl;

    while (simple.loop())
    {
        Info<< "Time = " << runTime.timeName() << nl << endl;

        while (simple.correctNonOrthogonal())
        {
            if (MODENA_RUN)
            {
                try
                {
                    forAll(T, celli)
                    {
                        modelPtr->set(Tpos, T[celli]);
                        modelPtr->call();
                        DT[celli] = modelPtr->output(DTpos);
                    }
                }
                catch (const modena::Exception& e)
                {
                    return e.code;
                }
            }

            fvScalarMatrix TEqn
            (
                fvm::ddt(T) == fvm::laplacian(DT, T)
            );

            TEqn.solve();
        }

        #include "write.H"

        Info<< "ExecutionTime = " << runTime.elapsedCpuTime() << " s"
            << "  ClockTime = " << runTime.elapsedClockTime() << " s"
            << nl << endl;
    }

    Info<< "End\n" << endl;

    return 0;
}

// ************************************************************************* //
