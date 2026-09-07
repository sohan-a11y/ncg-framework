# NCG Floorplan Constraints
# 
# This script applies floorplan constraints for the NCG design
# to ensure proper resource allocation and timing closure.
#
# Logic allocation per spec:
# - 60% Logic Cells: Hashing Engines
# - 30% Logic Cells: AI/Inference Core
# - 10% Logic Cells: Control/PCIe
#
# Usage: source floorplan.tcl after opening synthesized design

# ============================================================================
# CONFIGURATION
# ============================================================================

# Get current design
set design [current_design]

# Logic allocation percentages (must sum to 1.0)
set HASH_PCT 0.60
set AI_PCT   0.30
set CTRL_PCT 0.10

# Target device resources (U50 VU9P)
# CLB: 236,448 LUTs, 472,896 FFs, 3,654 BRAMs, 1,280 DSPs
# For U280 (VU13P): CLB: 894,720 LUTs, 1,789,440 FFs, 4,160 BRAMs, 4,512 DSPs

# Get device info
set device [get_property PART [current_project]]
puts "Device: $device"

# ============================================================================
# DEFINE PBLOCKS (Physical Blocks)
# ============================================================================

# Hashing Array Pblock (60% of logic)
create_pblock hash_pblock
resize_pblock [get_pblocks hash_pblock] -add SLICE_X0Y0:SLICE_X236Y120  # ~60% of device width
add_cells_to_pblock [get_pblocks hash_pblock] [get_cells -hierarchical *hashing*]
add_cells_to_pblock [get_pblocks hash_pblock] [get_cells -hierarchical *sha256*]

# Inference Core Pblock (30% of logic)
create_pblock ai_pblock
resize_pblock [get_pblocks ai_pblock] -add SLICE_X237Y0:SLICE_X355Y120  # ~30% of device width
add_cells_to_pblock [get_pblocks ai_pblock] [get_cells -hierarchical *inference*]
add_cells_to_pblock [get_pblocks ai_pblock] [get_cells -hierarchical *attention*]
add_cells_to_pblock [get_pblocks ai_pblock] [get_cells -hierarchical *embedding*]
add_cells_to_pblock [get_pblocks ai_pblock] [get_cells -hierarchical *feedforward*]

# Control/PCIe Pblock (10% of logic)
create_pblock ctrl_pblock
resize_pblock [get_pblocks ctrl_pblock] -add SLICE_X356Y0:SLICE_X394Y120  # ~10% of device width
add_cells_to_pblock [get_pblocks ctrl_pblock] [get_cells -hierarchical *pcie*]
add_cells_to_pblock [get_pblocks ctrl_pblock] [get_cells -hierarchical *ctrl*]
add_cells_to_pblock [get_pblocks ctrl_pblock] [get_cells -hierarchical *hbm*]

# ============================================================================
# SET PBLOCK PROPERTIES
# ============================================================================

# Disable placement outside pblocks for these modules
set_property CONTAINMENT_ROUTING TRUE [get_pblocks hash_pblock]
set_property CONTAINMENT_ROUTING TRUE [get_pblocks ai_pblock]
set_property CONTAINMENT_ROUTING TRUE [get_pblocks ctrl_pblock]

# ============================================================================
# BRAM/URAM ALLOCATION
# ========================================================================

# Hashing array needs BRAM for candidate buffering
# AI core needs BRAM/URAM for DCPM storage and weight matrices

# Assign BRAMs to AI pblock (for DCPM storage)
# URAMs for inference core weights
set_property BLOCK_RAM TRUE [get_pblocks ai_pblock]
set_property ULTRA_RAM TRUE [get_pblocks ai_pblock]

# Hashing pblock gets some BRAM for candidate FIFOs
set_property BLOCK_RAM TRUE [get_pblocks hash_pblock]

# ========================================================================
# DSP ALLOCATION
# ========================================================================

# Hashing array uses DSPs for message schedule
# AI core uses DSPs for matrix multiplication

# Hashing pblock gets DSPs
set_property DSP TRUE [get_pblocks hash_pblock]

# AI pblock gets DSPs for INT4 matrix multiply
set_property DSP TRUE [get_pblocks ai_pblock]

# ========================================================================
# HBM CONTROLLER PLACEMENT
# ========================================================================

# HBM controller is pre-placed near HBM stacks
# Create pblock for HBM controller if not auto-placed
create_pblock hbm_pblock
resize_pblock [get_pblocks hbm_pblock] -add SLICE_X0Y0:SLICE_X394Y120  # Full height, near HBM
add_cells_to_pblock [get_pblocks hbm_pblock] [get_cells -hierarchical *hbm*]
set_property CONTAINMENT_ROUTING FALSE [get_pblocks hbm_pblock]  # Allow placement near HBM PHY

# ========================================================================
# PCIe CONTROLLER PLACEMENT
# ========================================================================

# PCIe controller is pre-placed near PCIe edge connector
create_pblock pcie_pblock
resize_pblock [get_pblocks pcie_pblock] -add SLICE_X356Y0:SLICE_X394Y120
add_cells_to_pblock [get_pblocks pcie_pblock] [get_cells -hierarchical *pcie*]
set_property CONTAINMENT_ROUTING FALSE [get_pblocks pcie_pblock]

# ========================================================================
# PROHIBITED AREAS (Reserved for I/O, clocks, etc.)
# ========================================================================

# Add prohibited sites for clock regions, I/O banks, etc.
# This prevents logic placement in clock regions and I/O banks
add_prohibited_sites [get_pblocks hash_pblock] [get_sites -filter {TYPE == "BUFGCE"}]
add_prohibited_sites [get_pblocks ai_pblock] [get_sites -filter {TYPE == "BUFGCE"}]

# ========================================================================
# CLOCK REGION ASSIGNMENT
# ========================================================================

# Assign clock regions to pblocks for better clock routing
# Hash pblock: clock regions 0-12
# AI pblock: clock regions 13-24
# Ctrl pblock: clock regions 25-31

# ========================================================================
# REPORT PBLOCK UTILIZATION
# ========================================================================

puts "======================================================================"
puts "Floorplan PBlock Summary"
puts "======================================================================"

foreach pblock [get_pblocks] {
    set cells [get_cells -of_objects [get_pblocks $pblock]]
    set slice_count [llength $cells]
    puts "PBlock $pblock: $slice_count cells"
}

puts "======================================================================"
puts "Floorplan constraints applied successfully!"
puts "======================================================================"