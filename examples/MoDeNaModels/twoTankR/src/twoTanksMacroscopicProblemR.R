#!/usr/bin/env Rscript
#
# @file
# Two-tank problem solved using the MoDeNa R wrapper.
#
# This example is the R counterpart of twoTanksJulia.  It demonstrates the
# same workflow — caching input positions before the loop, retrying on return
# code 100 (surrogate retrained), and propagating exit codes — using the
# modena R package instead of Modena.jl.
#
# Requires the modena R package to be installed.  This is done automatically
# when modena is installed via cmake --install -DWITH_R=ON.
# If not yet installed, run:
#   R CMD INSTALL <prefix>/share/modena/R/modena
#
# @author    MoDeNa Project
# @copyright 2014-2026, MoDeNa Project. GNU Public License.
# @ingroup   twoTanksR

library(modena)

# ── Physical parameters ──────────────────────────────────────────────────────
R_gas  <- 287.1   # specific gas constant for air [J/(kg·K)]
T_gas  <- 300.0   # temperature [K]
D      <- 0.01    # orifice diameter [m]
V0     <- 0.1     # volume of tank 0 [m³]
V1     <- 1.0     # volume of tank 1 [m³]
deltat <- 1e-3    # time step [s]
tend   <- 5.5     # end time [s]

p0 <- 3e5
p1 <- 1e4
m0 <- p0 * V0 / R_gas / T_gas
m1 <- p1 * V1 / R_gas / T_gas

rho0 <- m0 / V0
rho1 <- m1 / V1

# ── Load surrogate model ─────────────────────────────────────────────────────
model <- Modena$new("flowRate")

cat("inputs:\n");     for (n in model$inputs_names())     cat("  ", n, "\n")
cat("outputs:\n");    for (n in model$outputs_names())    cat("  ", n, "\n")
cat("parameters:\n"); for (n in model$parameters_names()) cat("  ", n, "\n")

# Cache argument positions once before the loop.
pos_D      <- model$input_pos("D")
pos_rho0   <- model$input_pos("rho0")
pos_p0     <- model$input_pos("p0")
pos_p1Byp0 <- model$input_pos("p1Byp0")
pos_mdot   <- model$output_pos("flowRate")
model$check()

# ── Time-stepping loop ───────────────────────────────────────────────────────
t <- 0.0
while (t + deltat < tend + 1e-10) {
    t <- t + deltat

    # Set inputs — always flow from high to low pressure.
    if (p0 > p1) {
        model$set(pos_D,      D)
        model$set(pos_rho0,   rho0)
        model$set(pos_p0,     p0)
        model$set(pos_p1Byp0, p1 / p0)
    } else {
        model$set(pos_D,      D)
        model$set(pos_rho0,   rho1)
        model$set(pos_p0,     p1)
        model$set(pos_p1Byp0, p0 / p1)
    }

    ret <- model$call()

    if (ret == 100L) {
        t <- t - deltat   # surrogate retrained — stay at same step and retry
        next
    }
    if (ret != 0L) {
        quit(status = ret)
    }

    mdot <- model$output(pos_mdot)

    if (p0 > p1) {
        m0 <- m0 - mdot * deltat
        m1 <- m1 + mdot * deltat
    } else {
        m0 <- m0 + mdot * deltat
        m1 <- m1 - mdot * deltat
    }

    rho0 <- m0 / V0
    rho1 <- m1 / V1
    p0   <- m0 / V0 * R_gas * T_gas
    p1   <- m1 / V1 * R_gas * T_gas

    cat(sprintf("t = %.4f  rho0 = %.4f  p0 = %.2f  p1 = %.2f\n",
                t, rho0, p0, p1))
}
