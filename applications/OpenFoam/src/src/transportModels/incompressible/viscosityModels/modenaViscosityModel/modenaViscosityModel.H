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

Namespace
    Foam::viscosityModels

Description
    A namespace for various incompressible viscosityModel implementations.

Class
    Foam::viscosityModels::modenaViscosityModel

Description
    An incompressible viscosity model that evaluates viscosity via a MoDeNa
    surrogate model.

SourceFiles
    modenaViscosityModel.C

\*---------------------------------------------------------------------------*/

#ifndef modenaViscosityModel_H
#define modenaViscosityModel_H

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
                Class modenaViscosityModel Declaration
\*---------------------------------------------------------------------------*/

class modenaViscosityModel
:
    public viscosityModel
{

private:
    // Private data

        dictionary modenaViscosityModelCoeffs_;
        modena::Model model_;
        word surrogateModel_;

        volScalarField nu_;


    // Private Member Functions

        tmp<volScalarField> calcNu() const;


public:

    //- Runtime type information
    TypeName("modenaViscosityModel");


    // Constructors

        //- Construct from components
        modenaViscosityModel
        (
            const word& name,
            const dictionary& viscosityProperties,
            const volVectorField& U,
            const surfaceScalarField& phi
        );


    //- Destructor
    virtual ~modenaViscosityModel()
    {}


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
