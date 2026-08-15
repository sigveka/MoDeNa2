
.PHONY: all clean distclean help

all: help

clean:
	rm -rf build launcher_*

distclean: clean
	rm -rf build models func_* modena.log

help:
	@echo "Usage:"
	@echo "  ./buildModels   — build and install the coolPropMixture package"
	@echo "  ./initModels    — sample compositions with CASTRO, fit the surrogate"
	@echo "  ./workflow      — validate the surrogate against CoolProp"
	@echo ""
	@echo "  make clean      — remove build artefacts"
	@echo "  make distclean  — remove build artefacts and installed models"
