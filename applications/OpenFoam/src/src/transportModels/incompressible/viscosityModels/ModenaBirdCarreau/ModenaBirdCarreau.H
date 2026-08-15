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

Class
    Foam::viscosityModels::ModenaBirdCarreau

Description
    An incompressible Bird-Carreau non-Newtonian viscosity model.

    The Bird-Carreau-Yasuda form is also supported if the optional "a"
    coefficient is specified.  "a" defaults to 2 for the Bird-Carreau model.

SourceFiles
    ModenaBirdCarreau.C

\*---------------------------------------------------------------------------*/

#ifndef ModenaBirdCarreau_H
#define ModenaBirdCarreau_H

#include "viscosityModel.H"
#include "dimensionedScalar.H"
#include "volFields.H"
#include "error.H"
#include <modena/modena.hpp>


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{
namespace viscosityModels
{


/*---------------------------------------------------------------------------*\
                           Class BirdCarreau Declaration
\*---------------------------------------------------------------------------*/

class ModenaBirdCarreau
:
    public viscosityModel
{
    // Private data

        dictionary ModenaBirdCarreauCoeffs_;
        modena::Model model_;
        word surrogateModel_;

        volScalarField nu_;

    // Private Member Functions

        //- Calculate and return the laminar viscosity
        tmp<volScalarField> calcNu() const;


public:

    //- Runtime type information
    TypeName("ModenaBirdCarreau");


    // Constructors

        //- Construct from components
        ModenaBirdCarreau
        (
            const word& name,
            const dictionary& viscosityProperties,
            const volVectorField& U,
            const surfaceScalarField& phi
        );


    //- Destructor
    ~ModenaBirdCarreau()
    { }


    // Member Functions

        //- Return the laminar viscosity
        tmp<volScalarField> nu() const
        {
            return nu_;
        }

        //- Return the laminar viscosity for patch
        tmp<scalarField> nu(const label patchi) const
        {
            return nu_.boundaryField()[patchi];
        }

        //- Correct the laminar viscosity
        void correct()
        {
            nu_ = calcNu();
        }

        //- Read transportProperties dictionary
        bool read(const dictionary& viscosityProperties);
};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace viscosityModels
} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
