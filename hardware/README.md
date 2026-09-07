# NCG Hardware Directory

This directory contains the FPGA hardware implementation for the Neuromorphic Cryptanalytic Generator (NCG).

## Structure

```
hardware/
├── rtl/                    # SystemVerilog RTL designs
│   ├── ncg_top.sv         # Top-level module
│   └── ncg_top_tb.sv      # Testbench
├── inference_core/         # AI inference execution logic
│   └── inference_core.sv  # INT4 Transformer inference core
├── hashing_cores/          # Parallel hashing engines
│   └── sha256_core.sv     # SHA-256 core + parallel array
├── simulation.py           # Python simulation wrappers (Verilator/Amaranth)
└── Makefile               # Build system for Verilator
```

## Components

### Inference Core (`inference_core/`)
- **INT4-quantized Transformer** execution on FPGA
- **Block RAM** interface for DCPM storage
- **Permutation State Machine** for candidate generation
- **Shift register** candidate output
- 60% of logic allocated to hashing, 30% to AI, 10% to control

### Hashing Cores (`hashing_cores/`)
- **SHA-256** pipelined core (64 rounds)
- **Parallel array** of 1000+ cores
- **Zero-copy** internal bus
- **Hardware XOR comparator** with interrupt on match
- Supports Bcrypt/Argon2 parameterized variants

### Top-Level (`rtl/`)
- **PCIe Gen5** host interface
- **HBM2/HBM3** memory controller
- **Clock domain crossing** utilities
- **Status monitoring** and debug

## Building & Simulation

```bash
cd hardware
make sim          # Run Verilator simulation
make wave         # Run with VCD waveform
make view         # View waveforms in gtkwave
make lint         # Run Verilator lint check
```

## Target Hardware

- **Primary**: AMD Xilinx Alveo U50 (HBM2)
- **Alternative**: Alveo U280, ZCU102
- **Clock**: 200MHz+ system clock
- **Logic allocation**: 60% hash / 30% AI / 10% control

## Requirements

- **Verilator** 4.224+ for simulation
- **Vivado** 2022.2+ for synthesis
- **Python** 3.10+ for simulation wrappers
- **Amaranth** (optional) for Python HDL

## Development Flow

1. **RTL Development**: Edit SystemVerilog in `rtl/`, `inference_core/`, `hashing_cores/`
2. **Simulation**: `make sim` for quick functional verification
3. **Waveform Debug**: `make wave` + `make view` for detailed analysis
4. **Lint Check**: `make lint` before synthesis
5. **Synthesis**: Use Vivado project in `synth/` (not included)

## Adding New Cores

1. Create new `.sv` file in appropriate subdirectory
2. Add to `RTL_SOURCES` in Makefile
3. Instantiate in `ncg_top.sv`
4. Add testbench stimuli in `ncg_top_tb.sv`