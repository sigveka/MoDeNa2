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
    Foam::error

Description
    Class to handle errors and exceptions in a simple, consistent stream-based
    manner.

    The error class is globally instantiated with a title string. Errors,
    messages and other data are piped to the messageStream class in the
    standard manner.  Manipulators are supplied for exit and abort which may
    terminate the program or throw an exception depending on whether the
    exception handling has been switched on (off by default).

Usage
    \code
        error << "message1" << "message2" << FoamDataType << exit(errNo);
        error << "message1" << "message2" << FoamDataType << abort();
    \endcode

SourceFiles
    error.C

\*---------------------------------------------------------------------------*/

#ifndef error_H
#define error_H

#include "messageStream.H"
#include "error.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

// Forward declaration of friend functions and operators
class myerror;

/*---------------------------------------------------------------------------*\
                            Class error Declaration
\*---------------------------------------------------------------------------*/

class myerror
:
    error
{};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
