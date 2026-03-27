# twoTanksChained

Demonstrates **chained surrogate models**: the flow-rate surrogate itself
depends on an ideal-gas surrogate (`flowRate_idealGas → flowRate`), showing
how MoDeNa handles multi-level model hierarchies.

**Macroscopic solver:** `twoTanksMacroscopicProblem` (C)
**Surrogate models:** `flowRate_idealGas`, `flowRate` (chained, backward mapping)

See [`../twoTanks/README.md`](../twoTanks/README.md) for a full explanation of
the model-definition philosophy and how `modena.toml` connects the surrogate
definition to the macroscopic solver task.

## How to run

```bash
# 1. Compile and install model packages
./buildModels

# 2. Initialise surrogates in the database
./initModels

# 3. Run the simulation
./workflow
```
