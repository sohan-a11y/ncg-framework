# NCG Hardware Makefile
# Supports Verilator and Amaranth simulation with comprehensive testbenches

# Configuration
TOP_MODULE = ncg_top
DESIGN_DIR = rtl
BUILD_DIR = build
VCD_DIR = waves

# Verilator configuration
VERILATOR = verilator
VERILATOR_FLAGS = --cc --trace --trace-structs -O3 -x-initial -x-assign
VERILATOR_INCLUDE = -I$(DESIGN_DIR)/inference_core -I$(DESIGN_DIR)/hashing_cores

# Source files
RTL_SOURCES = \
	$(DESIGN_DIR)/ncg_top.sv \
	$(DESIGN_DIR)/inference_core/inference_core.sv \
	$(DESIGN_DIR)/hashing_cores/sha256_core.sv

# Testbench files
TB_SOURCES = $(DESIGN_DIR)/ncg_top_tb.sv
INF_TB_SOURCES = $(DESIGN_DIR)/inference_core_tb.sv
SHA256_TB_SOURCES = $(DESIGN_DIR)/sha256_core_tb.sv
SHA256_ARR_TB_SOURCES = $(DESIGN_DIR)/sha256_array_tb.sv

# All testbenches
ALL_TB_SOURCES = $(TB_SOURCES) $(INF_TB_SOURCES) $(SHA256_TB_SOURCES) $(SHA256_ARR_TB_SOURCES)

# Default target
all: sim

# Create directories
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(VCD_DIR):
	mkdir -p $(VCD_DIR)

# Verilator compilation
verilate: $(BUILD_DIR)
	cd $(BUILD_DIR) && $(VERILATOR) $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module $(TOP_MODULE) $(RTL_SOURCES) $(TB_SOURCES)

# Build simulation executable
build: verilate
	cd $(BUILD_DIR) && make -f V$(TOP_MODULE).mk V$(TOP_MODULE)

# Build individual testbenches
build-inf: $(BUILD_DIR)
	cd $(BUILD_DIR) && $(VERILATOR) $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module inference_core $(DESIGN_DIR)/inference_core/inference_core.sv $(INF_TB_SOURCES)
	cd $(BUILD_DIR) && make -f Vinference_core.mk Vinference_core

build-sha256: $(BUILD_DIR)
	cd $(BUILD_DIR) && $(VERILATOR) $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module sha256_core $(DESIGN_DIR)/hashing_cores/sha256_core.sv $(SHA256_TB_SOURCES)
	cd $(BUILD_DIR) && make -f Vsha256_core.mk Vsha256_core

build-sha256-arr: $(BUILD_DIR)
	cd $(BUILD_DIR) && $(VERILATOR) $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module sha256_array $(DESIGN_DIR)/hashing_cores/sha256_core.sv $(SHA256_ARR_TB_SOURCES)
	cd $(BUILD_DIR) && make -f Vsha256_array.mk Vsha256_array

# Run simulation
sim: build
	cd $(BUILD_DIR) && ./V$(TOP_MODULE)

# Run individual testbenches
sim-inf: build-inf
	cd $(BUILD_DIR) && ./Vinference_core

sim-sha256: build-sha256
	cd $(BUILD_DIR) && ./Vsha256_core

sim-sha256-arr: build-sha256-arr
	cd $(BUILD_DIR) && ./Vsha256_array

# Run all simulations
sim-all: sim sim-inf sim-sha256 sim-sha256-arr

# Run with waveform generation
wave: build
	cd $(BUILD_DIR) && ./V$(TOP_MODULE) +trace
	mv $(BUILD_DIR)/waveform.vcd $(VCD_DIR)/$(TOP_MODULE).vcd

wave-inf: build-inf
	cd $(BUILD_DIR) && ./Vinference_core +trace
	mv $(BUILD_DIR)/waveform.vcd $(VCD_DIR)/inference_core.vcd

wave-sha256: build-sha256
	cd $(BUILD_DIR) && ./Vsha256_core +trace
	mv $(BUILD_DIR)/waveform.vcd $(VCD_DIR)/sha256_core.vcd

# View waveforms (requires gtkwave)
view: wave
	gtkwave $(VCD_DIR)/$(TOP_MODULE).vcd

view-inf: wave-inf
	gtkwave $(VCD_DIR)/inference_core.vcd

view-sha256: wave-sha256
	gtkwave $(VCD_DIR)/sha256_core.vcd

# Lint with Verilator
lint:
	$(VERILATOR) --lint-only $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module $(TOP_MODULE) $(RTL_SOURCES)

lint-inf:
	$(VERILATOR) --lint-only $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module inference_core $(DESIGN_DIR)/inference_core/inference_core.sv

lint-sha256:
	$(VERILATOR) --lint-only $(VERILATOR_FLAGS) $(VERILATOR_INCLUDE) --top-module sha256_core $(DESIGN_DIR)/hashing_cores/sha256_core.sv

lint-all: lint lint-inf lint-sha256

# Python simulation infrastructure
sim-python:
	python -m hardware.simulation --top-module $(TOP_MODULE) --cycles 50000

# Validation against software reference
validate:
	python -c "
from hardware.simulation import run_full_simulation_suite, SimulationConfig
config = SimulationConfig(top_module='ncg_top', design_dir=Path('rtl'), cycles=50000)
results = run_full_simulation_suite(config)
passed = sum(1 for r in results.values() if r.success)
total = len(results)
print(f'Validation: {passed}/{total} passed')
if passed != total:
    exit(1)
"

# Performance profiling
profile:
	python -c "
from hardware.simulation import VerilatorSimulator, SimulationConfig, profile_hardware_performance
config = SimulationConfig(top_module='ncg_top', design_dir=Path('rtl'), cycles=50000)
sim = VerilatorSimulator(config)
if sim.compile():
    stats = profile_hardware_performance(sim, 'ncg_top', 10)
    print(f'Performance: {stats}')
"

# Generate test report
report:
	python -c "
from hardware.simulation import run_full_simulation_suite, generate_test_report, SimulationConfig
config = SimulationConfig(top_module='ncg_top', design_dir=Path('rtl'), cycles=50000)
results = run_full_simulation_suite(config)
generate_test_report(results, Path('simulation_report.json'))
"

# Run Verilator lint check
lint: lint-all

# Clean build artifacts
clean:
	rm -rf $(BUILD_DIR) $(VCD_DIR)

# Clean everything including Python cache
clean-all: clean
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.vcd" -delete 2>/dev/null || true

# Help
help:
	@echo "NCG Hardware Makefile"
	@echo ""
	@echo "Main Targets:"
	@echo "  all         - Run main simulation (default)"
	@echo "  verilate    - Run Verilator compilation only"
	@echo "  build       - Build main simulation executable"
	@echo "  sim         - Run main simulation"
	@echo "  sim-all     - Run all simulations"
	@echo "  wave        - Run simulation with waveform"
	@echo "  view        - View waveforms with gtkwave"
	@echo ""
	@echo "Module Targets:"
	@echo "  build-inf       - Build inference_core testbench"
	@echo "  build-sha256    - Build sha256_core testbench"
	@echo "  build-sha256-arr - Build sha256_array testbench"
	@echo "  sim-inf         - Run inference_core simulation"
	@echo "  sim-sha256      - Run sha256_core simulation"
	@echo "  sim-sha256-arr  - Run sha256_array simulation"
	@echo ""
	@echo "Waveform Targets:"
	@echo "  wave        - Generate waveform for main simulation"
	@echo "  wave-inf    - Generate waveform for inference_core"
	@echo "  wave-sha256 - Generate waveform for sha256_core"
	@echo "  view        - View main waveform with gtkwave"
	@echo "  view-inf    - View inference_core waveform"
	@echo "  view-sha256 - View sha256_core waveform"
	@echo ""
	@echo "Validation & Profiling:"
	@echo "  validate      - Run validation against software reference"
	@echo "  profile       - Profile hardware performance"
	@echo "  report        - Generate test report"
	@echo ""
	@echo "Linting:"
	@echo "  lint          - Run all lint checks"
	@echo "  lint-inf      - Lint inference_core"
	@echo "  lint-sha256   - Lint sha256_core"
	@echo ""
	@echo "Python Simulation:"
	@echo "  sim-python    - Run via Python simulation infrastructure"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean         - Remove build artifacts"
	@echo "  clean-all     - Remove all build artifacts and cache"
	@echo ""
	@echo "  help          - Show this help"

.PHONY: all verilate build build-inf build-sha256 build-sha256-arr sim sim-inf sim-sha256 sim-sha256-arr sim-all wave wave-inf wave-sha256 view view-inf view-sha256 lint lint-inf lint-sha256 lint-all sim-python validate profile report clean clean-all help