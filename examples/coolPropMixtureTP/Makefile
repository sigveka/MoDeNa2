
.PHONY: all clean distclean help

all: help

clean:
	rm -rf build launcher_*

distclean: clean
	rm -rf build models func_* modena.log

help:
	@echo "Usage:"
	@echo "  ./buildModels   — build and install the coolPropMixtureTP package"
	@echo "  ./initModels    — sample (T, p) with LHS and compositions with CASTRO, fit"
	@echo "  ./workflow      — validate the surrogate against CoolProp"
	@echo ""
	@echo "  make clean      — remove build artefacts"
	@echo "  make distclean  — remove build artefacts and installed models"
