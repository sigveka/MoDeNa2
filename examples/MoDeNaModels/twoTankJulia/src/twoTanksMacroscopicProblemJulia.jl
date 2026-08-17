#!/usr/bin/env julia
#=
@file
Two-tank problem solved using the MoDeNa Julia wrapper.

This example is the Julia counterpart of twoTankCxx.  It demonstrates the
same workflow — caching input positions before the loop, retrying on
ParametersUpdated, and propagating exit codes — using the Modena.jl wrapper
instead of modena::Model from C++.

Requires the Modena.jl package to be registered in Julia's package manager.
This is done automatically when modena is installed via cmake --install.
If not yet registered, run:
  julia -e 'using Pkg; Pkg.develop(PackageSpec(path="<prefix>/share/julia/packages/Modena"))'

@author    Sigve Karolius
@copyright 2014-2016, MoDeNa Project. GNU Public License.
@ingroup   twoTanksJulia
=#

using Modena

# ── Physical parameters ──────────────────────────────────────────────────────
const R      = 287.1    # specific gas constant for air [J/(kg·K)]
const T_gas  = 300.0    # temperature [K]
const D      = 0.01     # orifice diameter [m]
const V0     = 0.1      # volume of tank 0 [m³]
const V1     = 1.0      # volume of tank 1 [m³]
const deltat = 1e-3     # time step [s]
const tend   = 5.5      # end time [s]

p0 = 3e5
p1 = 1e4
m0 = p0 * V0 / R / T_gas
m1 = p1 * V1 / R / T_gas

rho0 = m0 / V0
rho1 = m1 / V1

# ── Load surrogate model ─────────────────────────────────────────────────────
model = Model("flowRate")

println("inputs:")
for n in inputs_names(model);     println("  ", n); end
println("outputs:")
for n in outputs_names(model);    println("  ", n); end
println("parameters:")
for n in parameters_names(model); println("  ", n); end

# Cache argument positions once before the loop.
Dpos      = input_pos(model, "D")
rho0Pos   = input_pos(model, "rho0")
p0Pos     = input_pos(model, "p0")
p1Byp0Pos = input_pos(model, "p1Byp0")
check(model)

# ── Time-stepping loop ───────────────────────────────────────────────────────
t = 0.0
while t + deltat < tend + 1e-10
    global t, m0, m1, rho0, rho1, p0, p1

    t += deltat

    # Set inputs — always flow from high to low pressure.
    if p0 > p1
        set!(model, Dpos,      D)
        set!(model, rho0Pos,   rho0)
        set!(model, p0Pos,     p0)
        set!(model, p1Byp0Pos, p1 / p0)
    else
        set!(model, Dpos,      D)
        set!(model, rho0Pos,   rho1)
        set!(model, p0Pos,     p1)
        set!(model, p1Byp0Pos, p0 / p1)
    end

    try
        call!(model)
    catch e
        if e isa ParametersUpdated
            t -= deltat    # stay at the same time step and retry
            continue
        elseif e isa ExitAndRestart || e isa ExitAndInitialise
            exit(e.code)
        else
            rethrow()
        end
    end

    mdot = output(model, 0)

    if p0 > p1
        m0 -= mdot * deltat
        m1 += mdot * deltat
    else
        m0 += mdot * deltat
        m1 -= mdot * deltat
    end

    rho0 = m0 / V0
    rho1 = m1 / V1
    p0   = m0 / V0 * R * T_gas
    p1   = m1 / V1 * R * T_gas

    println("t = $t  rho0 = $rho0  p0 = $p0  p1 = $p1")
end
# vim: set nospell
