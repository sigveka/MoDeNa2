# twoTanksR

Same two-tank problem as `twoTanks`, but with the macroscopic solver written
in **R** using the MoDeNa R wrapper.

**Macroscopic solver:** `twoTanksMacroscopicProblemR` (R)
**Surrogate model:** `flowRate` (polynomial, backward mapping)

See [`../twoTanks/README.md`](../twoTanks/README.md) for a full explanation of
the model-definition philosophy and how `modena.toml` connects the surrogate
definition to the macroscopic solver task.

## How to run

```bash
# 1. Compile and install model packages
./buildModels

# 2. Initialise surrogate in the database
./initModels

# 3. Run the simulation
./workflow
```
