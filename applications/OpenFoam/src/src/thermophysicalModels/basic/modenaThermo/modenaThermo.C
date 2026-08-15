/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright (C) 2012 OpenFOAM Foundation
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

\*---------------------------------------------------------------------------*/

#include "modenaThermo.H"

/* * * * * * * * * * * * * * * private static data * * * * * * * * * * * * * */

namespace Foam
{
    defineTypeNameAndDebug(modenaThermo, 0);
    defineRunTimeSelectionTable(modenaThermo, fvMesh);
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::modenaThermo::modenaThermo(const fvMesh& mesh, const word& phaseName)
:
    basicThermo(mesh, phaseName)
{}



Foam::modenaThermo::modenaThermo
(
    const fvMesh& mesh,
    const dictionary& dict,
    const word& phaseName
)
try
  :
    basicThermo(mesh, dict, phaseName)
{ /* Construction block */
}
catch(const Modena::modenaException& e)
{
   //Foam::error::error << "message1" << FoamDataType << Foam::error::exit(e.errorCode());
   //Foam::error::error << "message1" << Foam::error::exit(e.errorCode());
   Foam::error err(e.what());
   err.exit(e.errorCode());
}


// * * * * * * * * * * * * * * * * Selectors * * * * * * * * * * * * * * * * //

Foam::autoPtr<Foam::modenaThermo> Foam::modenaThermo::New
(
    const fvMesh& mesh,
    const word& phaseName
)
{
    return basicThermo::New<modenaThermo>(mesh, phaseName);
}


// * * * * * * * * * * * * * * * * Destructor  * * * * * * * * * * * * * * * //

Foam::modenaThermo::~modenaThermo()
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

Foam::tmp<Foam::volScalarField> Foam::modenaThermo::nu() const
{
    return mu()/rho();
}


Foam::tmp<Foam::scalarField> Foam::modenaThermo::nu(const label patchi) const
{
    return mu(patchi)/rho(patchi);
}


// ************************************************************************* //
