# twoTanksPython

Same two-tank problem as `twoTanks`, but with the macroscopic solver written
in **pure Python** (`twoTanksSim.py`), launched as a subprocess by FireWorks.
Useful for prototyping: no compilation step required for the solver itself.

**Macroscopic solver:** `twoTanksSim.py` (Python subprocess)
**Surrogate model:** `flowRate` (polynomial, backward mapping)

See [`../twoTanks/README.md`](../twoTanks/README.md) for a full explanation of
the model-definition philosophy and how `modena.toml` connects the surrogate
definition to the macroscopic solver task.

## How to run

```bash
# 1. Install model packages
./buildModels

# 2. Initialise surrogate in the database
./initModels

# 3. Run the simulation
./workflow
```
