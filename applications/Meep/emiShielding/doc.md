# surfaceImpedance[material=Cu]

Leontovich surface impedance of copper computed from the complex permittivity
via a 1D Meep FDTD verification and an analytical formula.

## Physics

The **Leontovich surface impedance** $Z_s(\omega, d)$ characterises how a
thin metal slab of thickness $d$ responds to an impinging plane wave at
angular frequency $\omega$.  It enters the Leontovich impedance boundary
condition

$$\mathbf{E}_\parallel = Z_s\,(\hat{n} \times \mathbf{H}_\parallel)$$

used on metal surfaces in 3D FEM solvers (NGSolve), eliminating the need to
resolve the skin depth $\delta = \sqrt{2/(\mu_0\,\sigma\,\omega)}$ in the
volumetric mesh.

The complex wave vector inside the slab is

$$k_\text{slab} = \frac{\omega}{c}\sqrt{\varepsilon(\omega)}$$

where $\varepsilon(\omega) = \varepsilon_1(\omega) + i\,\varepsilon_2(\omega)$
is supplied by the `dielectricFunction[material=Cu]` surrogate.  The exact
surface impedance of a free-standing slab backed by vacuum is

$$Z_s(\omega, d) = \frac{Z_\text{slab}}{\tanh(i\,k_\text{slab}\,d)}$$

with $Z_\text{slab} = Z_0 / \sqrt{\varepsilon}$ and $Z_0 = 376.73\,\Omega$.
This formula is exact in both the thick-film limit
($d \gg \delta$, recovers $Z_s \to Z_\text{slab}$) and the thin-film limit
($d \ll \delta$, recovers the sheet-resistance result).

If the optional **Meep** package is installed, a pair of 1D FDTD simulations
(reference pulse + slab pulse) verifies the field decay at each training point
before the analytical $Z_s$ is returned.  Without Meep the exact task uses
the analytical formula only.

## Inputs and outputs

| Name | Symbol | Range | Units |
|---|---|---|---|
| `omega_eV` | $\omega$ | 0.5 – 6.0 | eV |
| `d_nm` | $d$ | 10 – 500 | nm |
| `Zs_real` | $\mathrm{Re}(Z_s)$ | ≥ 0 | Ω |
| `Zs_imag` | $\mathrm{Im}(Z_s)$ | — | Ω |

## Surrogate form

A bilinear polynomial in $\omega$ and $d$:

$$Z_s(\omega, d) \approx (a_0 + a_1\omega + a_2 d + a_3\omega d)
                       + i\,(b_0 + b_1\omega + b_2 d + b_3\omega d)$$

Separate coefficient sets $(a_i)$ and $(b_i)$ are fitted for the real and
imaginary parts.  The bilinear form captures the dominant $d^{-1}$ sheet
resistance scaling and the $\omega^{1/2}$ skin-depth dependence over the
training range.

## Limitations

- **Plane-wave assumption** — $Z_s$ is derived for normal incidence; grazing
  incidence corrections are not included.
- **Thin-slab training range** — the bilinear surrogate is fitted in the
  10–500 nm range; bulk copper (microns and above) falls outside the valid
  domain and will trigger backward mapping.
- **Inherited IPA error** — permittivity is taken from the
  `dielectricFunction` surrogate (IPA/PBE); see that model's limitations.
