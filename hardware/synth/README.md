# NCG Hardware Synthesis Documentation

This directory contains all the hardware synthesis infrastructure for the NCG framework,
including RTL designs, Vivado project scripts, constraint files, and deployment tools.

## Directory Structure

```
synth/
├── constraints/           # XDC constraint files
│   ├── alveo_u50.xdc     # Alveo U50 pin/timing constraints
│   └── alveo_u280.xdc    # Alveo U280 pin/timing constraints
├── tcl/                   # Vivado TCL scripts
│   ├── create_project.tcl      # Project creation
│   ├── floorplan.tcl           # Logic allocation floorplan
│   ├── timing_closure.tcl      # Timing closure optimizations
│   └── generate_bitstream.tcl  # Bitstream generation
├── scripts/               # Deployment and validation scripts
│   ├── deploy.sh               # FPGA deployment script
│   ├── create_package.sh       # Deployment package creator
│   └── validate.py             # Hardware validation
├── ip/                    # Generated IP (gitignored)
└── README.md              # This file
```

## Quick Start

### 1. Create Vivado Project

```bash
# For Alveo U50
vivado -mode batch -source tcl/create_project.tcl -tclargs u50 ncg_u50

# For Alveo U280
vivado -mode batch -source tcl/create_project.tcl -tclargs u280 ncg_u280
```

### 2. Run Synthesis & Implementation

```bash
# In Vivado TCL console (or via make)
launch_runs synth_1
launch_runs impl_1
```

### 3. Apply Floorplan (Optional but Recommended)

```tcl
source tcl/floorplan.tcl
```

### 4. Timing Closure

```tcl
source tcl/timing_closure.tcl
```

### 5. Generate Bitstream

```tcl
source tcl/generate_bitstream.tcl
```

### 6. Deploy to Hardware

```bash
# Using deployment script
./scripts/deploy.sh bitstream/ncg_top.bit [device_bdf] [--verify]

# Or create deployment package
./scripts/create_package.sh -b bitstream/ncg_top.bit -x ncg_top.xclbin
```

## Hardware Architecture

### NCG Top-Level Modules

```
ncg_top
├── PCIe Interface (Gen4/5 x16)
│   ├── AXI-Lite Control Interface
│   └── AXI-MM Data Interface
├── Inference Core (30% logic)
│   ├── Token Embedding
│   ├── Transformer Blocks (6 layers)
│   ├── INT4 Quantized Attention
│   ├── Feed-Forward Network
│   └── DCPM Output Head
├── Hashing Array (60% logic)
│   ├── SHA-256 Cores (1024 instances)
│   ├── Candidate Buffer
│   └── Match Detection
└── HBM Controller (10% logic)
    ├── 2x HBM2 Stacks (U50) / 4x HBM2 (U280)
    └── DCPM Storage
```

### Logic Allocation

| Module | Allocation | Resources |
|--------|------------|-----------|
| Hashing Array | 60% | ~140K LUTs, 768 DSPs |
| Inference Core | 30% | ~70K LUTs, 384 DSPs |
| Control/PCIe | 10% | ~23K LUTs |

### Memory Map

| Region | Address Range | Size | Purpose |
|--------|---------------|------|---------|
| Control Regs | 0x0000 - 0x0FFF | 4KB | PCIe BAR0 |
| DCPM BRAM | 0x1000 - 0xFFFF | 60KB | Inference Core |
| Candidate FIFO | 0x10000 - 0x1FFFF | 64KB | Hashing Array |
| HBM DCPM | 0x100000000 - | 4GB | Bulk DCPM Storage |

## Clock Domains

| Domain | Frequency | Source | Purpose |
|--------|-----------|--------|---------|
| sys_clk | 200-250 MHz | PCIe Refclk | System logic |
| pcie_clk | 250 MHz | PCIe PHY | PCIe Interface |
| hbm_clk | 400 MHz | HBM PHY | HBM Controller |
| infer_clk | 200-250 MHz | MMCM | Inference Core |
| hash_clk | 200-250 MHz | MMCM | Hashing Array |

## Timing Constraints

- Target: 250 MHz (4.0 ns period) on U280, 200 MHz (5.0 ns) on U50
- Setup margin: 0.5 ns
- Hold margin: 0.3 ns
- Multi-cycle paths for control/status: 2-3 cycles
- False paths across async clock domains

## FPGA Resource Estimates (U50)

| Resource | Available | Used | Utilization |
|----------|-----------|------|-------------|
| LUTs | 1,182,240 | ~235K | ~20% |
| FFs | 2,364,480 | ~470K | ~20% |
| BRAM | 3,654 | ~800 | ~22% |
| URAM | 960 | ~200 | ~21% |
| DSPs | 6,840 | ~1,500 | ~22% |
| HBM | 8GB | 4GB | 50% |

## Power Estimation

| Component | Power (W) |
|-----------|-----------|
| Inference Core | ~15W |
| Hashing Array | ~25W |
| PCIe Interface | ~5W |
| HBM Controller | ~10W |
| **Total** | **~55W** |

## Deployment

### Prerequisites

- XRT 2022.2+ installed
- Alveo U50/U280 in PCIe Gen4/5 slot
- Linux kernel 5.4+
- Root access for deployment

### Deployment Steps

```bash
# 1. Program bitstream
xbutil program -p ncg_top.bit -d 0000:01:00.0

# 2. Load XCLBIN
xbutil load -p ncg.xclbin -d 0000:01:00.0

# 3. Verify
xbutil examine -r -d 0000:01:00.0
```

### Validation

```bash
python3 scripts/validate.py --device 0000:01:00.0 --xclbin ncg.xclbin
```

## Troubleshooting

### Bitstream Not Loading
- Check PCIe link status: `lspci -vv -s 0000:01:00.0`
- Verify bitstream matches device: `xbutil examine -r`
- Check power: `xbutil examine -p`

### Timing Violations
- Run timing closure script
- Check floorplan constraints
- Increase clock period if needed

### HBM Not Working
- Verify HBM IP configuration
- Check HBM temperature: `xbutil examine -t`
- Verify HBM calibration in ILA

## File List

### RTL Sources
- `rtl/ncg_top.sv` - Top-level integration
- `rtl/inference_core/inference_core.sv` - AI inference core
- `rtl/hashing_cores/sha256_core.sv` - SHA-256 hashing

### Testbenches
- `rtl/ncg_top_tb.sv` - Top-level integration test
- `rtl/inference_core_tb.sv` - Inference core test
- `rtl/sha256_core_tb.sv` - SHA-256 core test
- `rtl/sha256_array_tb.sv` - Parallel array test

### Constraints
- `constraints/alveo_u50.xdc` - U50 pin/timing constraints
- `constraints/alveo_u280.xdc` - U280 pin/timing constraints

### Scripts
- `tcl/create_project.tcl` - Project creation
- `tcl/floorplan.tcl` - Logic allocation
- `tcl/timing_closure.tcl` - Timing optimization
- `tcl/generate_bitstream.tcl` - Bitstream generation
- `scripts/deploy.sh` - Hardware deployment
- `scripts/create_package.sh` - Package creation
- `scripts/validate.py` - Hardware validation

## License

Apache 2.0 - See LICENSE file in project root.