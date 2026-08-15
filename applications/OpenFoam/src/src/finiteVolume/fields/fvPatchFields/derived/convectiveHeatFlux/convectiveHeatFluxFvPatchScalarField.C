/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright (C) 2011-2012 OpenFOAM Foundation
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

#include "convectiveHeatFluxFvPatchScalarField.H"
#include "addToRunTimeSelectionTable.H"
#include "fvPatchFieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::convectiveHeatFluxFvPatchScalarField::convectiveHeatFluxFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, volMesh>& iF
)
:
    fixedGradientFvPatchScalarField(p, iF),
    TName_("T")
{}


Foam::convectiveHeatFluxFvPatchScalarField::convectiveHeatFluxFvPatchScalarField
(
    const convectiveHeatFluxFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, volMesh>& iF,
    const fvPatchFieldMapper& mapper
)
:
    fixedGradientFvPatchScalarField(ptf, p, iF, mapper),
    TName_(ptf.TName_)
{}


Foam::convectiveHeatFluxFvPatchScalarField::convectiveHeatFluxFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, volMesh>& iF,
    const dictionary& dict
)
:
    fixedGradientFvPatchScalarField(p, iF),
    TName_(dict.lookupOrDefault<word>("T", "T"))
{
        fvPatchField<scalar>::operator=(patchInternalField());
        gradient() = 0.0;
}


Foam::convectiveHeatFluxFvPatchScalarField::convectiveHeatFluxFvPatchScalarField
(
    const convectiveHeatFluxFvPatchScalarField& tppsf
)
:
    fixedGradientFvPatchScalarField(tppsf),
    TName_(tppsf.TName_)
{}


Foam::convectiveHeatFluxFvPatchScalarField::convectiveHeatFluxFvPatchScalarField
(
    const convectiveHeatFluxFvPatchScalarField& tppsf,
    const DimensionedField<scalar, volMesh>& iF
)
:
    fixedGradientFvPatchScalarField(tppsf, iF),
    TName_(tppsf.TName_)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::convectiveHeatFluxFvPatchScalarField::updateCoeffs()
{
    if (updated())
    {
        return;
    }

    const fvPatchField<scalar>& T =
        patch().lookupPatchField<volScalarField, scalar>(TName_);

    const dictionary& TP =
        db().lookupObject<IOdictionary>("transportProperties");

    dimensionedScalar h (TP.lookup("h"));
    dimensionedScalar k (TP.lookup("k"));
    dimensionedScalar Tsur (TP.lookup("Tsur"));

    gradient() = - (h.value() / k.value()) * (T - Tsur.value());

    fixedGradientFvPatchScalarField::updateCoeffs();
}


void Foam::convectiveHeatFluxFvPatchScalarField::write(Ostream& os) const
{
    fvPatchScalarField::write(os);
    writeEntryIfDifferent<word>(os, "T", "T", TName_);
    writeEntry("value", os);
}


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{
    makePatchTypeField
    (
        fvPatchScalarField,
        convectiveHeatFluxFvPatchScalarField
    );
}

// ************************************************************************* //
