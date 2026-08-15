# thermalDiffusion[material=Cu]

Thermal conductivity of copper as a function of temperature computed by
equilibrium molecular dynamics using the Green-Kubo method.

## Physics

The **thermal conductivity** $\kappa(T)$ relates the heat flux to the
temperature gradient via Fourier's law $\mathbf{q} = -\kappa\,\nabla T$.
For metals, $\kappa$ decreases with temperature due to increased
electron–phonon and phonon–phonon scattering.

The exact task uses the **Green-Kubo relation**

$$\kappa = \frac{1}{3\,k_B\,T^2\,V}
  \int_0^\infty \langle \mathbf{J}(t) \cdot \mathbf{J}(0) \rangle\, dt$$

where $\mathbf{J}$ is the instantaneous heat-current vector,
$\langle \mathbf{J}(t) \cdot \mathbf{J}(0) \rangle$ is its autocorrelation
function (HCACF), $V$ is the simulation cell volume, and $T$ is the
equilibrium temperature.

Copper is modelled with the **Mishin EAM potential** (`Cu_u3.eam`), which
accurately reproduces elastic constants, stacking fault energies, and
diffusion barriers.  The simulation protocol is:

1. Equilibrate an FCC supercell ($6 \times 6 \times 6$ unit cells,
   864 atoms) in the NVT ensemble for 100 ps.
2. Run NVE production for 1 ns, accumulating the HCACF via
   `compute heat/flux` + `fix ave/correlate`.
3. Integrate the HCACF with the trapezoidal rule, truncating at the first
   zero crossing.

## Inputs and outputs

| Name | Symbol | Range | Units |
|---|---|---|---|
| `T` | $T$ | 300 – 1300 | K |
| `kappa` | $\kappa(T)$ | > 0 | W m⁻¹ K⁻¹ |

## Surrogate form

A quadratic polynomial in $T$:

$$\kappa(T) = r_0 + r_1\,T + r_2\,T^2$$

The quadratic captures both the $\kappa \sim T^{-1}$ phonon–phonon
scattering regime (high $T$) and the saturation near the melting point,
over the 300–1300 K training range.

## Limitations

- **Classical MD** — quantum zero-point effects are neglected; results below
  ~200 K are unreliable.
- **EAM potential** — pair-functional models do not include electronic
  contributions to heat transport explicitly; the Green-Kubo result
  represents the phonon (lattice) contribution only.  For copper, the
  electronic contribution is dominant at low $T$ and is not captured.
- **Statistical noise** — each HCACF integral has ~5–10 % statistical
  uncertainty from a single 1 ns trajectory; multiple independent runs
  are averaged to reduce this in the training set.
- **Defect-free crystal** — grain boundaries, vacancies, and dislocations
  reduce $\kappa$ in real samples and are not represented.
