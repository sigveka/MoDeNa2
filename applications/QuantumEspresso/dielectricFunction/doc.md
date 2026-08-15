# dielectricFunction[material=Cu]

Optical dielectric function of copper computed by density-functional
perturbation theory.

## Physics

The complex permittivity $\varepsilon(\omega) = \varepsilon_1(\omega) + i\,\varepsilon_2(\omega)$
describes how a material responds to an electromagnetic field at photon
energy $\omega$.  For metals, $\varepsilon_1 < 0$ at low frequencies
(reflection-dominated) and crosses zero near the plasma edge.

The exact task uses the **independent-particle approximation** (IPA) as
implemented in Quantum ESPRESSO `epsilon.x`.  The imaginary part is computed
via the Ehrenreich–Cohen formula

$$\varepsilon_2(\omega) \propto \sum_{n,m,\mathbf{k}}
  |\langle n\mathbf{k}|\,\hat{\mathbf{p}}\,|m\mathbf{k}\rangle|^2\,
  \delta(\varepsilon_{n\mathbf{k}} - \varepsilon_{m\mathbf{k}} - \omega)$$

and $\varepsilon_1$ is obtained by Kramers–Kronig integration.  The
ground-state charge density is computed with a $8\times8\times8$ k-mesh
(SCF), and the optical matrix elements with a denser $16\times16\times16$
mesh (NSCF).

## Inputs and outputs

| Name | Symbol | Range | Units |
|---|---|---|---|
| `omega_eV` | $\omega$ | 0.5 – 6.0 | eV |
| `eps1` | $\varepsilon_1(\omega)$ | — | dimensionless |
| `eps2` | $\varepsilon_2(\omega)$ | ≥ 0 | dimensionless |

## Surrogate form

Two independent cubic polynomials in $\omega$:

$$\varepsilon_1(\omega) = p_0 + p_1\omega + p_2\omega^2 + p_3\omega^3$$

$$\varepsilon_2(\omega) = q_0 + q_1\omega + q_2\omega^2 + q_3\omega^3$$

The cubic basis captures the Drude-like dispersion of Cu — $\varepsilon_1$
is negative below the plasma edge (~2.1 eV) and rising toward positive
values in the UV.  Initial training uses eleven photon energies with dense
sampling near 2.1 eV where the surrogate needs most support.

## Limitations

- **IPA only** — local-field effects, excitonic corrections, and
  electron–phonon renormalisation are neglected.  IPA overestimates
  $\varepsilon_2$ near the plasma edge by roughly 10–20 %.
- **PBE functional** — the generalised-gradient approximation
  underestimates the d-band onset in Cu; a scissors correction
  (`shift` keyword in `epsilon.in`) can partially compensate.
- **Temperature** — Fermi smearing (Marzari–Vanderbilt) is used to
  mimic finite temperature; full electron–phonon effects are not included.
