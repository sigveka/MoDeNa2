/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright (C) 2011-2014 OpenFOAM Foundation
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

#include "myerror.H"
#include "OStringStream.H"
#include "fileName.H"
#include "dictionary.H"
#include "JobInfo.H"
#include "Pstream.H"
#include "OSspecific.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

void Foam::myerror::exit(const int errNo)
{
    if (!throwExceptions_ && JobInfo::constructed)
    {
        jobInfo.add("FatalError", operator dictionary());
        jobInfo.exit();
    }

    if (abort_)
    {
        abort();
    }

    if (Pstream::parRun())
    {
        Perr<< endl << *this << endl
            << "\nFOAM parallel run exiting\n" << endl;
        Pstream::exit(errNo);
    }
    else
    {
        if (throwExceptions_)
        {
            // Make a copy of the error to throw
            error errorException(*this);

            // Rewind the message buffer for the next error message
            messageStreamPtr_->rewind();

            throw errorException;
        }
        else
        {
            Perr<< endl << *this << endl
                << "\nFOAM exiting\n" << endl;
            ::exit(errNo);
        }
    }
}

// ************************************************************************* //
