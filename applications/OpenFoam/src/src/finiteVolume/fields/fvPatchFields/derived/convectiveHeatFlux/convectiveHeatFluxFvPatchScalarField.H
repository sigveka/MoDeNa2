/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright (C) 2011-2016 OpenFOAM Foundation
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

Class
    Foam::convectiveHeatFluxFvPatchScalarField

Description
    Provides a convective heat flux BC

Usage
    \table
        Property     | Description             | Required    | Default value
        T            | Temperature field name  | no          | T
        h            |                         | yes         | --
        k            |                         | yes         | --
        Tsur         | Environment Temperature | yes         | --
        phi          | Flux field name         | no          | phi
        psi          | Compressibility field name | no       | thermo:psi
        gamma        | ratio of specific heats (Cp/Cv) | yes |
        T0           | reference temperature   | yes         |
    \endtable

    Example of the boundary condition specification:
    \verbatim
    <patchName>
    {
        type            convectiveHeatFlux;
        T0              uniform 300;
    }
    \endverbatim

SourceFiles
    convectiveHeatFluxFvPatchScalarField.C

See also
    Foam::fixedGradientFvPatchField

\*---------------------------------------------------------------------------*/

#ifndef convectiveHeatFluxFvPatchScalarField_H
#define convectiveHeatFluxFvPatchScalarField_H

#include "fixedGradientFvPatchFields.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

/*---------------------------------------------------------------------------*\
             Class convectiveHeatFluxFvPatchScalarField Declaration
\*---------------------------------------------------------------------------*/

class convectiveHeatFluxFvPatchScalarField
:
    public fixedGradientFvPatchScalarField
{
    // Private data

        //- Name of the velocity field
        word TName_;

public:

    //- Runtime type information
    TypeName("convectiveHeatFlux");


    // Constructors

        //- Construct from patch and internal field
        convectiveHeatFluxFvPatchScalarField
        (
            const fvPatch&,
            const DimensionedField<scalar, volMesh>&
        );

        //- Construct from patch, internal field and dictionary
        convectiveHeatFluxFvPatchScalarField
        (
            const fvPatch&,
            const DimensionedField<scalar, volMesh>&,
            const dictionary&
        );

        //- Construct by mapping given convectiveHeatFluxFvPatchScalarField
        //  onto a new patch
        convectiveHeatFluxFvPatchScalarField
        (
            const convectiveHeatFluxFvPatchScalarField&,
            const fvPatch&,
            const DimensionedField<scalar, volMesh>&,
            const fvPatchFieldMapper&
        );

        //- Construct as copy
        convectiveHeatFluxFvPatchScalarField
        (
            const convectiveHeatFluxFvPatchScalarField&
        );

        //- Construct and return a clone
        virtual tmp<fvPatchScalarField> clone() const
        {
            return tmp<fvPatchScalarField>
            (
                new convectiveHeatFluxFvPatchScalarField(*this)
            );
        }

        //- Construct as copy setting internal field reference
        convectiveHeatFluxFvPatchScalarField
        (
            const convectiveHeatFluxFvPatchScalarField&,
            const DimensionedField<scalar, volMesh>&
        );

        //- Construct and return a clone setting internal field reference
        virtual tmp<fvPatchScalarField> clone
        (
            const DimensionedField<scalar, volMesh>& iF
        ) const
        {
            return tmp<fvPatchScalarField>
            (
                new convectiveHeatFluxFvPatchScalarField(*this, iF)
            );
        }


        // Evaluation functions

            //- Update the coefficients associated with the patch field
            virtual void updateCoeffs();


        //- Write
        virtual void write(Ostream&) const;
};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
