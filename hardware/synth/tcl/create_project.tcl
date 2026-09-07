# NCG Vivado Project Creation Script
# 
# This script creates a Vivado project for the NCG design targeting
# Alveo U50 or U280 accelerator cards.
#
# Usage: vivado -mode batch -source create_project.tcl -tclargs <target_board> <project_name>
#   target_board: u50 | u280
#   project_name: optional, defaults to ncg_<board>

# ============================================================================
# PARSE ARGUMENTS
# ============================================================================

set target_board [lindex $argv 0]
if {$target_board == ""} {
    set target_board "u50"
}

set project_name [lindex $argv 1]
if {$project_name == ""} {
    set project_name "ncg_${target_board}"
}

# ============================================================================
# CONFIGURATION
# ============================================================================

set project_dir [file normalize "."]
set rtl_dir [file join $project_dir "rtl"]
set constraints_dir [file join $project_dir "constraints"]
set ip_dir [file join $project_dir "ip"]

# Board-specific configuration
switch $target_board {
    u50 {
        set part "xcu50-fsvh2104-2-e"
        set board_part "xilinx.com:alveo_u50:part0:1.0"
        set constraints_file [file join $constraints_dir "alveo_u50.xdc"]
        set clock_period_ns 5.0
        set pcie_gen 5
        set pcie_lanes 16
        set hbm_channels 8
    }
    u280 {
        set part "xcu280-fsvh2892-2-e"
        set board_part "xilinx.com:alveo_u280:part0:1.0"
        set constraints_file [file join $constraints_dir "alveo_u280.xdc"]
        set clock_period_ns 4.0
        set pcie_gen 4
        set pcie_lanes 16
        set hbm_channels 16
    }
    default {
        puts "ERROR: Unknown target board '$target_board'. Use 'u50' or 'u280'."
        exit 1
    }
}

puts "======================================================================"
puts "NCG Vivado Project Creation"
puts "======================================================================"
puts "Target Board: $target_board"
puts "Part: $part"
puts "Board Part: $board_part"
puts "Project Name: $project_name"
puts "Clock Period: ${clock_period_ns} ns"
puts "PCIe: Gen${pcie_gen} x${pcie_lanes}"
puts "HBM Channels: $hbm_channels"
puts "Constraints: $constraints_file"
puts "======================================================================"

# ============================================================================
# CREATE PROJECT
# ============================================================================

create_project -force -part $part $project_name [file join $project_dir $project_name]

# Set board part for board-aware IP
set_property board_part $board_part [current_project]

# ============================================================================
# ADD SOURCES
# ============================================================================

# RTL sources
add_files -norecurse \
    [file join $rtl_dir "ncg_top.sv"] \
    [file join $rtl_dir "inference_core/inference_core.sv"] \
    [file join $rtl_dir "hashing_cores/sha256_core.sv"]

# Constraints
add_files -fileset constrs_1 -norecurse $constraints_file

# ============================================================================
# SET TOP MODULE
# ============================================================================

set_property top ncg_top [current_fileset]

# ============================================================================
# ADD IP INTEGRATION (PCIe, HBM, DMA)
# ============================================================================

# PCIe IP
set pcie_ip_name "pcie4c_uscale_plus_0"
if {$pcie_gen == 5} {
    set pcie_ip_name "pcie5_uscale_plus_0"
}

create_ip -name xilinx.com:ip:pcie4_uscale_plus -vendor xilinx.com -library ip -version 4.0 -module_name $pcie_ip_name
configure_ip -quiet \
    -prop_values { \
        PCIE_CAPABILITY_LINK_SPEED:16 \
        PCIE_CAPABILITY_MAX_LINK_WIDTH:16 \
        PF0_COMMAND_DPARITY_ERROR_RESPONSE:TRUE \
        PF0_COMMAND_PARITY_ERROR_RESPONSE:TRUE \
        PF0_DEVICE_PORT_TYPE:0x0 \
        PF0_LINK_CAPABILITIES_MAX_LINK_SPEED:16 \
        PF0_LINK_CAPABILITIES_MAX_LINK_WIDTH:16 \
        PF0_MSI_CAPABILITY:TRUE \
        PF0_MSIX_CAPABILITY:TRUE \
        PL_LINK_CAP_MAX_LINK_SPEED:16 \
        PL_LINK_CAP_MAX_LINK_WIDTH:16 \
        REFCLK_FREQ:1 \
        SYS_CLK_FREQ:2 \
    } $pcie_ip_name

# HBM Controller IP
set hbm_ip_name "hbm_ctrl_0"
create_ip -name xilinx.com:ip:hbm_controller -vendor xilinx.com -library ip -version 1.0 -module_name $hbm_ip_name
configure_ip -quiet \
    -prop_values { \
        HBM_CHANNELS:$hbm_channels \
        HBM_STACKS:1 \
        HBM_CHANNELS_PER_STACK:8 \
        DATA_WIDTH:256 \
        AXI_DATA_WIDTH:512 \
        ENABLE_ECC:TRUE \
        ENABLE_REFRESH:TRUE \
        CMD_FIFO_DEPTH:1024 \
    } $hbm_ip_name

# AXI DMA IP (for high-bandwidth data transfer)
set dma_ip_name "axi_dma_0"
create_ip -name xilinx.com:ip:axi_dma -vendor xilinx.com -library ip -version 7.1 -module_name $dma_ip_name
configure_ip -quiet \
    -prop_values { \
        ENABLE_SG:1 \
        INCLUDE_DRE:1 \
        MAX_PKT_LEN:23 \
        MAX_TRANSFER_LEN:23 \
        ADDR_WIDTH:64 \
        DATA_WIDTH:256 \
        ENABLE_MULTI_CHANNEL:1 \
        NUM_CHNL:4 \
    } $dma_ip_name

# AXI Interconnect for memory-mapped access
set interconnect_ip_name "axi_interconnect_0"
create_ip -name xilinx.com:ip:axi_interconnect -vendor xilinx.com -library ip -version 2.0 -module_name $interconnect_ip_name
configure_ip -quiet \
    -prop_values { \
        NUM_MI:4 \
        NUM_SI:2 \
        ADDR_WIDTH:64 \
        DATA_WIDTH:512 \
    } $interconnect_ip_name

# Generate IP output products
generate_target all [get_ips]

# ============================================================================
# BLOCK DESIGN (Optional - for IP integration)
# ============================================================================

# Create block design for IP integration
create_bd_design "ncg_system"
set_property board_part $board_part [current_bd_design .]

# Add IPs to block design
set pcie_inst [create_bd_cell -type ip -vlnv xilinx.com:ip:pcie4_uscale_plus:4.0 $pcie_ip_name]
set hbm_inst [create_bd_cell -type ip -vlnv xilinx.com:ip:hbm_controller:1.0 $hbm_ip_name]
set dma_inst [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 $dma_ip_name]
set interconnect_inst [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.0 $interconnect_ip_name]

# Connect PCIe to interconnect
connect_bd_intf_net -intf_net [get_bd_intf_ports pcie_axi] [get_bd_intf_pins $interconnect_inst/S00_AXI]
connect_bd_intf_net -intf_net [get_bd_intf_pins $pcie_inst/AXI_MM] [get_bd_intf_pins $interconnect_inst/S01_AXI]

# Connect HBM to interconnect
connect_bd_intf_net -intf_net [get_bd_intf_pins $hbm_inst/AXI] [get_bd_intf_pins $interconnect_inst/M00_AXI]

# Connect DMA to interconnect
connect_bd_intf_net -intf_net [get_bd_intf_pins $dma_inst/M_AXI_MM2S] [get_bd_intf_pins $interconnect_inst/M01_AXI]
connect_bd_intf_net -intf_net [get_bd_intf_pins $dma_inst/M_AXI_S2MM] [get_bd_intf_pins $interconnect_inst/M02_AXI]

# Connect RTL top to interconnect
make_bd_intf_pins_external [get_bd_intf_pins $interconnect_inst/M03_AXI]
set_property name "ncg_axi" [get_bd_intf_ports ncg_axi]

# Validate and generate wrapper
validate_bd_design
generate_target all [get_files ncg_system.bd]

# Add block design wrapper to project
add_files -norecurse [glob [file join $project_dir $project_name $project_name.gen sources_1 bd ncg_system hdl ncg_system_wrapper.v]]

# ============================================================================
# SYNTHESIS SETTINGS
# ============================================================================

set_property STEPS.SYNTH_DESIGN.ARGS.MORE_OPTIONS {-retiming -no_timing_driven -gated_clock_conversion on} [current_project]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY full [current_project]
set_property STEPS.SYNTH_DESIGN.ARGS.RESOURCE_SHARING auto [current_project]
set_property STEPS.SYNTH_DESIGN.ARGS.CONTROL_SET_OPT_THRESHOLD auto [current_project]

# ============================================================================
# IMPLEMENTATION SETTINGS
# ============================================================================

# Create implementation runs
create_run -name synth_1 -flow {Vivado Synthesis 2022} -part $part -constrset constrs_1
create_run -name impl_1 -flow {Vivado Implementation 2022} -parent_run synth_1 -constrset constrs_1

# Implementation strategies for timing closure
create_run -name impl_1_timing -flow {Vivado Implementation 2022} -parent_run synth_1 -constrset constrs_1 \
    -strategy "TimingClosure"

create_run -name impl_1_congestion -flow {Vivado Implementation 2022} -parent_run synth_1 -constrset constrs_1 \
    -strategy "CongestionSpreadLogic"

create_run -name impl_1_perf -flow {Vivado Implementation 2022} -parent_run synth_1 -constrset constrs_1 \
    -strategy "PerformanceOptimized"

# ============================================================================
# TIMING CONSTRAINTS (already in XDC)
# ============================================================================

# ============================================================================
# REPORT SETTINGS
# ============================================================================

set_property STEPS.SYNTH_DESIGN.ARGS.MORE_OPTIONS {-no_timing_driven} [current_project]

# ============================================================================
# SAVE PROJECT
# ============================================================================

save_project

puts "======================================================================"
puts "Project '$project_name' created successfully!"
puts "======================================================================"
puts "Next steps:"
puts "  1. Open project: vivado -mode gui $project_name/$project_name.xpr"
puts "  2. Run synthesis: launch_runs synth_1"
puts "  3. Run implementation: launch_runs impl_1"
puts "  4. Generate bitstream: launch_runs impl_1 -to_step write_bitstream"
puts "  5. Program device: open_hw_manager; connect_hw_server; current_hw_device [get_hw_devices]; program_hw_devices [get_hw_devices] [file join $project_dir $project_name $project_name.runs impl_1 ncg_top.bit]"
puts "======================================================================"