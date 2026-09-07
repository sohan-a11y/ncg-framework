# NCG Bitstream Generation and Programming Script
# 
# This script generates the bitstream and programs the FPGA
# for the NCG design on Alveo U50/U280.
#
# Usage: source generate_bitstream.tcl after successful implementation

# ============================================================================
# CONFIGURATION
# ============================================================================

set project_name "ncg_u50"  # Default, can be overridden
set target_board "u50"
set bitstream_name "ncg_top"

# Parse arguments
if {$argc > 0} {
    set project_name [lindex $argv 0]
}
if {$argc > 1} {
    set target_board [lindex $argv 1]
}

set project_dir [file normalize "."]
set runs_dir [file join $project_dir $project_name "$project_name.runs"]
set impl_dir [file join $runs_dir "impl_1"]

puts "======================================================================"
puts "NCG Bitstream Generation"
puts "======================================================================"
puts "Project: $project_name"
puts "Board: $target_board"
puts "Impl Dir: $impl_dir"
puts "======================================================================"

# ============================================================================
# CHECK IMPLEMENTATION STATUS
# ============================================================================

if {![file exists [file join $impl_dir "ncg_top.dcp"]]} {
    puts "ERROR: Implementation not found. Run implementation first."
    exit 1
}

# Open implemented design
open_checkpoint [file join $impl_dir "ncg_top.dcp"]

# ============================================================================
# BITSTREAM SETTINGS
# ============================================================================

# General bitstream settings
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.CONFIGRATE 66 [current_design]
set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]
set_property BITSTREAM.CONFIG.SPI_FALL_EDGE YES [current_design]

# Encryption (optional - for production)
# set_property BITSTREAM.ENCRYPTION.ENCRYPT YES [current_design]
# set_property BITSTREAM.ENCRYPTION.KEYFILE <keyfile.nky> [current_design]

# Startup settings
set_property BITSTREAM.STARTUP.STARTUPCLK CCLK [current_design]
set_property BITSTREAM.STARTUP.DONE_CYCLE 4 [current_design]
set_property BITSTREAM.STARTUP.GTS_CYCLE 5 [current_design]
set_property BITSTREAM.STARTUP.GWE_CYCLE 6 [current_design]

# Readback and verification
set_property BITSTREAM.CONFIG.UNUSEDPIN PULLUP [current_design]
set_property BITSTREAM.CONFIG.OVERTEMPPOWERDOWN Enable [current_design]

# ============================================================================
# GENERATE BITSTREAM
# ============================================================================

puts "======================================================================"
puts "Generating bitstream..."
puts "======================================================================"

write_bitstream -force [file join $project_dir "bitstream" "${bitstream_name}.bit"]

# Generate additional formats
write_bitstream -force -bin_file [file join $project_dir "bitstream" "${bitstream_name}.bin"]
write_bitstream -force -msk_file [file join $project_dir "bitstream" "${bitstream_name}.msk"]

# Generate debug probes file (for ILA)
write_debug_probes -force [file join $project_dir "bitstream" "${bitstream_name}_debug_probes.ltx"]

# Generate BIT file for JTAG
write_bitstream -force -bit [file join $project_dir "bitstream" "${bitstream_name}_jtag.bit"]

# Generate PR bitstream (if using partial reconfiguration)
# write_bitstream -force -partial -cell <pblock_name> [file join $project_dir "bitstream" "${bitstream_name}_pr.bit"]

puts "======================================================================"
puts "Bitstream generated successfully!"
puts "======================================================================"

# Report bitstream size
set bitstream_size [file size [file join $project_dir "bitstream" "${bitstream_name}.bit"]]
puts "Bitstream size: [expr {$bitstream_size / 1024 / 1024}] MB"

# ============================================================================
# VERIFY BITSTREAM
# ============================================================================

# Verify bitstream checksum
# verify_bitstream [file join $project_dir "bitstream" "${bitstream_name}.bit"]

# ============================================================================
# PROGRAMMING COMMANDS (for reference)
# ============================================================================

puts "======================================================================"
puts "Programming Commands (run in Vivado TCL or hw_server):"
puts "======================================================================"
puts ""
puts "# Connect to hardware server"
puts "connect_hw_server -url localhost:3121"
puts ""
puts "# Open hardware target"
puts "open_hw_target"
puts ""
puts "# Program device"
puts "current_hw_device [lindex [get_hw_devices] 0]"
puts "program_hw_devices [file join $project_dir \"bitstream\" \"${bitstream_name}.bit\"]"
puts ""
puts "# Verify programming"
puts "verify_hw_devices [file join $project_dir \"bitstream\" \"${bitstream_name}.bit\"]"
puts ""
puts "# For JTAG programming via hw_server:"
puts "open_hw_manager"
puts "connect_hw_server"
puts "open_hw_target"
puts "current_hw_device [lindex [get_hw_devices] 0]"
puts "program_hw_devices -bitstream [file join $project_dir \"bitstream\" \"${bitstream_name}.bit\"]"
puts ""
puts "# For flash programming (if supported):"
puts "program_flash -device [lindex [get_hw_devices] 0] -bitstream [file join $project_dir \"bitstream\" \"${bitstream_name}.bit\"]"
puts ""

# ============================================================================
# GENERATE REPORT
# ============================================================================

write_bitstream -force -report [file join $project_dir "bitstream" "${bitstream_name}_bitstream_report.rpt"]

puts "======================================================================"
puts "Bitstream generation complete!"
puts "Bitstream: [file join $project_dir \"bitstream\" \"${bitstream_name}.bit\"]"
puts "Debug probes: [file join $project_dir \"bitstream\" \"${bitstream_name}_debug_probes.ltx\"]"
puts "======================================================================"