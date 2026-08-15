    // Temperature Field

    solve
    (
        fvm::ddt(rho*Cp, T) + rho*Cp*fvm::div(phi, T) == fvm::laplacian(k, T)
    );

