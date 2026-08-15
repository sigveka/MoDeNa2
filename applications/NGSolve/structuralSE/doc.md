# structuralSE[geometry=enclosure]

Shielding effectiveness of a metallic enclosure with an aperture computed by
full-wave 3D frequency-domain FEM using NGSolve.

## Physics

The **shielding effectiveness** (SE) quantifies how much a metallic enclosure
attenuates an incident electromagnetic field:

$$\mathrm{SE}(\omega) = -20\log_{10}\!\left(
  \frac{|\mathbf{E}_\text{shielded}(\omega)|}{|\mathbf{E}_\text{incident}(\omega)|}
\right) \quad [\mathrm{dB}]$$

Higher SE means better shielding.  A single rectangular aperture in one wall
is the dominant leakage path; its contribution is modelled exactly by the FEM
mesh.

The exact task solves the **time-harmonic Maxwell curl–curl equation**

$$\nabla \times \mu_r^{-1} \nabla \times \mathbf{E}
  - k_0^2 \varepsilon_r\,\mathbf{E} = \mathbf{0}$$

in the vacuum interior of the box on Nédélec (HCurl) edge elements of order 2.
Metal walls are not meshed; instead the **Leontovich impedance boundary
condition**

$$\hat{n} \times (\mu_r^{-1}\nabla \times \mathbf{E})
  + \frac{1}{Z_s}\,\hat{n} \times (\hat{n} \times \mathbf{E}) = 0
  \quad \text{on } \partial\Omega_\text{wall}$$

is applied, where $Z_s(\omega, d)$ is supplied by the
`surfaceImpedance[material=Cu]` surrogate.  This eliminates the need to
resolve the skin depth — typically $\delta < 1\,\mu\mathrm{m}$ at GHz
frequencies — in a macroscopic 3D mesh.

The geometry is a $20 \times 20 \times 20\,\mathrm{mm}$ box with a
$5 \times 5\,\mathrm{mm}$ aperture in the $z = 0$ face.  A uniform
plane-wave equivalent source (a constant $\mathbf{E}_z$ boundary value) is
applied at the aperture face; the response is sampled at the box centre
$(0, 0, 0)$.

## Inputs and outputs

| Name | Symbol | Range | Units |
|---|---|---|---|
| `omega_GHz` | $\omega / (2\pi)$ | 0.1 – 10 | GHz |
| `SE_dB` | $\mathrm{SE}(\omega)$ | ≥ 0 | dB |

## Surrogate form

A quadratic polynomial in $\omega$:

$$\mathrm{SE}(\omega) = c_0 + c_1\,\omega + c_2\,\omega^2$$

The quadratic captures the roughly linear rise of SE with frequency (aperture
becomes electrically small at low $f$, diffraction-limited at high $f$) while
remaining cheap to evaluate in a host solver.

## Limitations

- **Single geometry** — box dimensions and aperture size are fixed; a
  parametric geometry study requires retraining with additional inputs.
- **IPA/PBE chain** — SE inherits the ~10–20 % error in $\varepsilon_2$ from
  the dielectricFunction base model via $Z_s$.
- **Plane-wave source** — the aperture is excited by a uniform field; near
  field or non-planar sources are not represented.
- **No interior objects** — circuit boards, cables, or other contents of the
  enclosure are not modelled.
