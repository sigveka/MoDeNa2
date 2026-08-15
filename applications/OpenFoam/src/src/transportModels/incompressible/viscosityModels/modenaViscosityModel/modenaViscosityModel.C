/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright (C) 2011 OpenFOAM Foundation
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

#include "modenaViscosityModel.H"
#include "addToRunTimeSelectionTable.H"
#include "surfaceFields.H"
#include "fvcGrad.H"

// * * * * * * * * * * * * * * Static Data Members * * * * * * * * * * * * * //

namespace Foam
{
namespace viscosityModels
{
    defineTypeNameAndDebug(modenaViscosityModel, 0);
    addToRunTimeSelectionTable(viscosityModel, modenaViscosityModel, dictionary);
}
}

// * * * * * * * * * * * * Private Member Functions  * * * * * * * * * * * * //

Foam::tmp<Foam::volScalarField>
Foam::viscosityModels::modenaViscosityModel::calcNu() const
{
    const Time& time = U_.time();
    const fvMesh& mesh = U_.mesh();
    const objectRegistry& db = U_.db();

    volScalarField epsilon = strainRate();

    volScalarField nuField
    (
        IOobject
        (
            "nu_",
            time.timeName(),
            db,
            IOobject::NO_READ,
            IOobject::NO_WRITE,
            false
        ),
        mesh,
        dimensionedScalar("zero", dimViscosity, 0)
    );

    try
    {
        const std::size_t pos_dgdt = model_.input_pos("dgdt");
        const std::size_t pos_mu   = model_.output_pos("mu");

        forAll(mesh.C(), celli)
        {
            model_.set(pos_dgdt, epsilon[celli]);
            model_.call();
            nuField[celli] = model_.output(pos_mu);
        }
    }
    catch (const modena::Exception& e)
    {
        Foam::error err(e.what());
        err.exit(e.code);
    }

    return tmp<volScalarField>(new volScalarField(nuField));
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::viscosityModels::modenaViscosityModel::modenaViscosityModel
(
    const word& name,
    const dictionary& viscosityProperties,
    const volVectorField& U,
    const surfaceScalarField& phi
)
try
:
    viscosityModel(name, viscosityProperties, U, phi),
    modenaViscosityModelCoeffs_
    (
        viscosityProperties.subDict(typeName + "Coeffs")
    ),
    model_
    (
        Foam::word(modenaViscosityModelCoeffs_.lookup("surrogateModel"))
    ),
    nu_
    (
        IOobject
        (
            "nu",
            U_.time().timeName(),
            U_.db(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        calcNu()
    )
{}
catch (const modena::Exception& e)
{
    Foam::error err(e.what());
    err.exit(e.code);
}


// * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * * //

bool Foam::viscosityModels::modenaViscosityModel::read
(
    const dictionary& viscosityProperties
)
{
    viscosityModel::read(viscosityProperties);

    modenaViscosityModelCoeffs_ =
        viscosityProperties.subDict(typeName + "Coeffs");
    modenaViscosityModelCoeffs_.lookup("surrogateModel") >> surrogateModel_;

    return true;
}

// ************************************************************************* //
