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

\*---------------------------------------------------------------------------*/

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

template<class Thermo>
inline Foam::modenaConstTransport<Thermo>::modenaConstTransport
(
    const Thermo& t,
    const scalar mu,
    const scalar Pr
)
:
    Thermo(t),
    mu_(mu),
    rPr_(1.0/Pr)
{}


template<class Thermo>
inline Foam::modenaConstTransport<Thermo>::modenaConstTransport
(
    const word& name,
    const modenaConstTransport& ct
)
:
    Thermo(name, ct),
    mu_(ct.mu_),
    rPr_(ct.rPr_)
{}


template<class Thermo>
inline Foam::autoPtr<Foam::modenaConstTransport<Thermo>>
Foam::modenaConstTransport<Thermo>::clone() const
{
    return autoPtr<modenaConstTransport<Thermo>>
    (
        new modenaConstTransport<Thermo>(*this)
    );
}


template<class Thermo>
inline Foam::autoPtr<Foam::modenaConstTransport<Thermo>>
Foam::modenaConstTransport<Thermo>::New
(
    Istream& is
)
{
    return autoPtr<modenaConstTransport<Thermo>>
    (
        new modenaConstTransport<Thermo>(is)
    );
}


template<class Thermo>
inline Foam::autoPtr<Foam::modenaConstTransport<Thermo>>
Foam::modenaConstTransport<Thermo>::New
(
    const dictionary& dict
)
{
    return autoPtr<modenaConstTransport<Thermo>>
    (
        new modenaConstTransport<Thermo>(dict)
    );
}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

template<class Thermo>
inline Foam::scalar Foam::modenaConstTransport<Thermo>::mu
(
    const scalar p,
    const scalar T
) const
{
    return mu_;
}


template<class Thermo>
inline Foam::scalar Foam::modenaConstTransport<Thermo>::kappa
(
    const scalar p,
    const scalar T
) const
{
    return this->Cp(p, T)*mu(p, T)*rPr_;
}


template<class Thermo>
inline Foam::scalar Foam::modenaConstTransport<Thermo>::alphah
(
    const scalar p,
    const scalar T
) const
{
    return mu(p, T)*rPr_;
}


// * * * * * * * * * * * * * * * Member Operators  * * * * * * * * * * * * * //

template<class Thermo>
inline void Foam::modenaConstTransport<Thermo>::operator=
(
    const modenaConstTransport<Thermo>& ct
)
{
    Thermo::operator=(ct);

    mu_ = ct.mu_;
    rPr_ = ct.rPr_;
}


template<class Thermo>
inline void Foam::modenaConstTransport<Thermo>::operator+=
(
    const modenaConstTransport<Thermo>& st
)
{
    scalar molr1 = this->nMoles();

    Thermo::operator+=(st);

    if (mag(molr1) + mag(st.nMoles()) > SMALL)
    {
        molr1 /= this->nMoles();
        scalar molr2 = st.nMoles()/this->nMoles();

        mu_ = molr1*mu_ + molr2*st.mu_;
        rPr_ = 1.0/(molr1/rPr_ + molr2/st.rPr_);
    }
}


template<class Thermo>
inline void Foam::modenaConstTransport<Thermo>::operator-=
(
    const modenaConstTransport<Thermo>& st
)
{
    scalar molr1 = this->nMoles();

    Thermo::operator-=(st);

    if (mag(molr1) + mag(st.nMoles()) > SMALL)
    {
        molr1 /= this->nMoles();
        scalar molr2 = st.nMoles()/this->nMoles();

        mu_ = molr1*mu_ - molr2*st.mu_;
        rPr_ = 1.0/(molr1/rPr_ - molr2/st.rPr_);
    }
}


template<class Thermo>
inline void Foam::modenaConstTransport<Thermo>::operator*=
(
    const scalar s
)
{
    Thermo::operator*=(s);
}


// * * * * * * * * * * * * * * * Friend Operators  * * * * * * * * * * * * * //

template<class Thermo>
inline Foam::modenaConstTransport<Thermo> Foam::operator+
(
    const modenaConstTransport<Thermo>& ct1,
    const modenaConstTransport<Thermo>& ct2
)
{
    Thermo t
    (
        static_cast<const Thermo&>(ct1) + static_cast<const Thermo&>(ct2)
    );

    if (mag(ct1.nMoles()) + mag(ct2.nMoles()) < SMALL)
    {
        return modenaConstTransport<Thermo>
        (
            t,
            0,
            ct1.rPr_
        );
    }
    else
    {
        scalar molr1 = ct1.nMoles()/t.nMoles();
        scalar molr2 = ct2.nMoles()/t.nMoles();

        return modenaConstTransport<Thermo>
        (
            t,
            molr1*ct1.mu_ + molr2*ct2.mu_,
            1.0/(molr1/ct1.rPr_ + molr2/ct2.rPr_)
        );
    }
}


template<class Thermo>
inline Foam::modenaConstTransport<Thermo> Foam::operator-
(
    const modenaConstTransport<Thermo>& ct1,
    const modenaConstTransport<Thermo>& ct2
)
{
    Thermo t
    (
        static_cast<const Thermo&>(ct1) - static_cast<const Thermo&>(ct2)
    );

    if (mag(ct1.nMoles()) + mag(ct2.nMoles()) < SMALL)
    {
        return modenaConstTransport<Thermo>
        (
            t,
            0,
            ct1.rPr_
        );
    }
    else
    {
        scalar molr1 = ct1.nMoles()/t.nMoles();
        scalar molr2 = ct2.nMoles()/t.nMoles();

        return modenaConstTransport<Thermo>
        (
            t,
            molr1*ct1.mu_ - molr2*ct2.mu_,
            1.0/(molr1/ct1.rPr_ - molr2/ct2.rPr_)
        );
    }
}


template<class Thermo>
inline Foam::modenaConstTransport<Thermo> Foam::operator*
(
    const scalar s,
    const modenaConstTransport<Thermo>& ct
)
{
    return modenaConstTransport<Thermo>
    (
        s*static_cast<const Thermo&>(ct),
        ct.mu_,
        1.0/ct.rPr_
    );
}


template<class Thermo>
inline Foam::modenaConstTransport<Thermo> Foam::operator==
(
    const modenaConstTransport<Thermo>& ct1,
    const modenaConstTransport<Thermo>& ct2
)
{
    return ct2 - ct1;
}


// ************************************************************************* //
