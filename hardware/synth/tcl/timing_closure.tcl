# NCG Timing Closure Script
# 
# This script applies timing closure techniques for the NCG design
# targeting 200-250 MHz system clock on Alveo U50/U280.
#
# Usage: source timing_closure.tcl after opening implemented design

# ============================================================================
# CONFIGURATION
# ============================================================================

set target_freq_mhz 250
set target_period_ns [expr {1000.0 / $target_freq_mhz}]
set target_ns [expr {$target_period_ns - 0.5}]  # 0.5ns margin

puts "======================================================================"
puts "NCG Timing Closure - Target: ${target_freq_mhz} MHz (${target_period_ns} ns period)"
puts "======================================================================"

# ============================================================================
# TIMING ANALYSIS
# ============================================================================

# Report timing summary
report_timing_summary -file timing_summary_pre.rpt

# Check worst negative slack (WNS)
set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
puts "Worst Negative Slack (Setup): $wns ns"

set whs [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
puts "Worst Hold Slack: $whs ns"

# ============================================================================
# CRITICAL PATH ANALYSIS
# ============================================================================

# Report top 10 critical paths
report_timing -max_paths 10 -setup -sort_by slack -file critical_paths.rpt

# Report clock domain crossing paths
report_cdc -file cdc_report.rpt

# ============================================================================
# OPTIMIZATION TECHNIQUES
# ============================================================================

# 1. Enable physical optimization
set_property PHYS_OPT true [current_run]

# 2. Enable retiming
set_property RETIMING true [current_run]

# 3. Enable register duplication for high fanout
set_property REG_DUPLICATION true [current_run]

# 4. Enable LUT combining
set_property LUT_COMBINING true [current_run]

# 5. Enable BUFG insertion for high fanout clocks
set_property BUFG_INSERTION true [current_run]

# ============================================================================
# PIPELINING FOR CRITICAL PATHS
# ============================================================================

# Add pipeline registers to critical paths
# This would be done in RTL, but we can use physical optimization

# Enable automatic pipelining for long paths
set_property AUTO_PIPELINING true [current_run]

# ============================================================================
# PLACEMENT OPTIMIZATION
# ============================================================================

# Enable congestion-aware placement
set_property CONGESTION_AWARE_PLACEMENT true [current_run]

# Enable global placement with timing-driven
set_property TIMING_DRIVEN_PLACEMENT true [current_run]

# ============================================================================
# ROUTING OPTIMIZATION
# ============================================================================

# Enable timing-driven routing
set_property TIMING_DRIVEN_ROUTING true [current_run]

# Enable delay-based cleanup
set_property DELAY_BASED_CLEANUP true [current_run]

# ============================================================================
# CLOCK TREE OPTIMIZATION
# ============================================================================

# Optimize clock tree for skew
set_property CLOCK_TREE_SYNTHESIS true [current_run]

# Optimize BUFG placement
set_property BUFG_OPTIMIZATION true [current_run]

# ============================================================================
# MULTI-CYCLE PATH CONSTRAINTS (for known slow paths)
# ============================================================================

# Multi-cycle for control/status paths
# (Already in XDC, but ensure they're applied)
# set_multicycle_path -setup 3 -from [get_cells *ctrl_reg*] -to [all_registers]

# ============================================================================
# FALSE PATHS (already in XDC)
# ============================================================================

# ============================================================================
# MAX DELAY CONSTRAINTS
# ============================================================================

# Constrain long combinational paths
# set_max_delay -from [get_pins *hashing*sha256*] -to [get_clocks sys_clk] 4.0

# ============================================================================
# HBM INTERFACE TIMING
# ============================================================================

# HBM interface has its own timing constraints from IP
# Ensure HBM clock domain is properly constrained

# ============================================================================
# PCIe INTERFACE TIMING
# ============================================================================

# PCIe interface timing from IP
# Ensure PCIe refclk domain is properly constrained

# ============================================================================
# REPORT TIMING AFTER OPTIMIZATION
# ============================================================================

# Run post-route timing analysis
report_timing_summary -file timing_summary_post.rpt
report_timing -max_paths 20 -setup -sort_by slack -file critical_paths_post.rpt

# Check final WNS
set final_wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
puts "Final Worst Negative Slack: $final_wns ns"

if {$final_wns >= 0} {
    puts "SUCCESS: Timing closure achieved!"
} else {
    puts "WARNING: Timing not met. WNS = $final_wns ns"
    
    # Additional optimization attempts
    puts "Attempting additional optimizations..."
    
    # Try different placement strategies
    set_property PLACER.ENABLE_RQL true [current_run]
    
    # Try router with more iterations
    set_property ROUTER.ITERATIONS 50 [current_run]
    
    # Try incremental compile
    set_property INCREMENTAL_COMPILE true [current_run]
}

# ============================================================================
# POWER ANALYSIS
# ============================================================================

# Run power analysis
report_power -file power_report.rpt

# ============================================================================
# UTILIZATION REPORT
# ============================================================================

report_utilization -file utilization.rpt

# ============================================================================
# FINAL REPORT
# ============================================================================

puts "======================================================================"
puts "Timing Closure Complete"
puts "======================================================================"
puts "Target Frequency: ${target_freq_mhz} MHz"
puts "Final WNS: $final_wns ns"
puts "Target Met: [expr {$final_wns >= 0 ? \"YES\" : \"NO\"}]"
puts "======================================================================"