# LibreLane flows, executed inside the container via run.sh.
#
# Each design has a base config (designs/<design>/config.json) plus one
# overlay per variant (designs/<design>/variants/<variant>.json), e.g. the
# std cell library. Runs are tagged runs/<variant>_<timestamp>, and every
# flow run also generates reports in <run>/reports/*.md.
#
# The variant is passed FIRST: LibreLane loads PDK/SCL settings only from the
# first config file. So the base config must not set any key a variant sets.
#
#   make pdk                           # download the sky130 PDK (once)
#   make synth                         # synthesize DESIGN with VARIANT
#   make sta DESIGN=ibex VARIANT=hs    # synthesis + pre-PnR STA
#   make sta-all DESIGN=ibex           # sta for every variant, then compare
#   make compare DESIGN=ibex           # compare latest run of each variant
#   make report                        # (re)generate reports, latest VARIANT run
#   make shell                         # interactive shell in the container
#   make clean                         # remove runs of DESIGN

DESIGN  ?= counter
VARIANT ?= hd

DESIGN_DIR := designs/$(DESIGN)
VARIANTS   := $(basename $(notdir $(wildcard $(DESIGN_DIR)/variants/*.json)))
CONFIGS     = $(DESIGN_DIR)/variants/$(VARIANT).json $(DESIGN_DIR)/config.json
TAG        := $(VARIANT)_$(shell date +%Y-%m-%d_%H-%M-%S)
RUN        := ./run.sh

FLOW = $(RUN) librelane --design-dir $(DESIGN_DIR) --run-tag $(TAG) --to $(1) $(CONFIGS) && \
       $(RUN) python3 scripts/report.py $(DESIGN_DIR)/runs/$(TAG)

.PHONY: pdk synth sta sta-all compare report shell clean

pdk:
	$(RUN) sh scripts/fetch_pdk.sh

synth:
	$(call FLOW,Yosys.Synthesis)

sta:
	$(call FLOW,OpenROAD.STAPrePNR)

sta-all:
	@for v in $(VARIANTS); do $(MAKE) --no-print-directory sta VARIANT=$$v || exit 1; done
	$(MAKE) --no-print-directory compare

compare:
	$(RUN) python3 scripts/compare.py $(DESIGN_DIR)

report:
	$(RUN) python3 scripts/report.py $(DESIGN_DIR) --variant $(VARIANT)

shell:
	$(RUN)

clean:
	rm -rf $(DESIGN_DIR)/runs
