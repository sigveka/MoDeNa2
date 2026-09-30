
.PHONY: all clean distclean help

all: help

clean:
	rm -rf build launcher_*

distclean: clean
	rm -rf build models func_* modena.log

help:
	@echo "Usage:"
	@echo "  ./buildModels   — build and install the fullerEtAlDiffusion package"
	@echo "  ./initModels    — register fullerEtAlDiffusion[A=H2O,B=N2] in the database"
	@echo "  ./workflow      — run fullerEtAlDiffusionTest through FireWorks"
	@echo ""
	@echo "  make clean      — remove build artefacts"
	@echo "  make distclean  — remove build artefacts and installed models"
