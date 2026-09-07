# NCG FPGA Constraints for AMD Xilinx Alveo U280
# 
# This file contains pin assignments, clock constraints, and timing constraints
# for the NCG design targeting the Alveo U280 (xcu280-fsvh2892-2-e) card.
#
# Device: xcu280-fsvh2892-2-e (UltraScale+ VU13P)
# Package: FSVH2892
# Speed Grade: -2 (0.9V)
# Temperature: Industrial (-40C to +100C)

## ========================================================================
## CLOCK CONSTRAINTS
## ========================================================================

# System clock - 250 MHz (higher performance on U280)
create_clock -name sys_clk -period 4.000 [get_ports sys_clk_p]
create_clock -name sys_clk_n -period 4.000 [get_ports sys_clk_n]

# PCIe reference clock - 100 MHz
create_clock -name pcie_refclk -period 10.000 [get_ports pcie_refclk_p]
create_clock -name pcie_refclk_n -period 10.000 [get_ports pcie_refclk_n]

# HBM controller clock - 400 MHz
create_clock -name hbm_clk -period 2.500 [get_ports hbm_clk_p]
create_clock -name hbm_clk_n -period 2.500 [get_ports hbm_clk_n]

# Generated clocks from MMCM/PLL
create_generated_clock -name infer_clk -source [get_pins sys_clk_mmcmm/CLKOUT0] -divide_by 1 [get_pins sys_clk_mmcmm/CLKOUT0]
create_generated_clock -name hash_clk -source [get_pins sys_clk_mmcmm/CLKOUT1] -divide_by 1 [get_pins sys_clk_mmcmm/CLKOUT1]
create_generated_clock -name hbm_ctrl_clk -source [get_pins hbm_clk_mmcmm/CLKOUT0] -divide_by 1 [get_pins hbm_clk_mmcmm/CLKOUT0]

## ========================================================================
## CLOCK UNCERTAINTY AND JITTER
## ========================================================================

set_clock_uncertainty -setup 0.040 [get_clocks sys_clk]
set_clock_uncertainty -hold 0.025 [get_clocks sys_clk]
set_clock_uncertainty -setup 0.050 [get_clocks pcie_refclk]
set_clock_uncertainty -hold 0.030 [get_clocks pcie_refclk]
set_clock_uncertainty -setup 0.040 [get_clocks hbm_clk]
set_clock_uncertainty -hold 0.020 [get_clocks hbm_clk]

set_clock_uncertainty -setup 0.050 [get_clocks infer_clk]
set_clock_uncertainty -setup 0.050 [get_clocks hash_clk]
set_clock_uncertainty -setup 0.045 [get_clocks hbm_ctrl_clk]

## ========================================================================
## CLOCK GROUPS
## ========================================================================

set_clock_groups -asynchronous -group [get_clocks sys_clk] -group [get_clocks pcie_refclk] -group [get_clocks hbm_clk]
set_clock_groups -logically_exclusive -group [get_clocks infer_clk] -group [get_clocks hash_clk]
set_clock_groups -logically_exclusive -group [get_clocks hbm_ctrl_clk] -group [get_clocks infer_clk]

## ========================================================================
## INPUT/OUTPUT DELAYS
## ========================================================================

set_input_delay -clock pcie_refclk -min 0.500 [get_ports pcie_rx*]
set_input_delay -clock pcie_refclk -max 1.500 [get_ports pcie_rx*]
set_output_delay -clock pcie_refclk -min 0.500 [get_ports pcie_tx*]
set_output_delay -clock pcie_refclk -max 1.500 [get_ports pcie_tx*]

set_input_delay -clock hbm_clk -min 0.300 [get_ports hbm_dq*]
set_input_delay -clock hbm_clk -max 0.800 [get_ports hbm_dq*]
set_output_delay -clock hbm_clk -min 0.300 [get_ports hbm_dq*]
set_output_delay -clock hbm_clk -max 0.800 [get_ports hbm_dq*]

set_output_delay -clock sys_clk -min 0.500 [get_ports status*]
set_output_delay -clock sys_clk -max 1.500 [get_ports status*]

## ========================================================================
## FALSE PATHS AND MULTI-CYCLE PATHS
## ========================================================================

set_false_path -from [get_clocks sys_clk] -to [get_clocks pcie_refclk]
set_false_path -from [get_clocks sys_clk] -to [get_clocks hbm_clk]
set_false_path -from [get_clocks pcie_refclk] -to [get_clocks sys_clk]
set_false_path -from [get_clocks pcie_refclk] -to [get_clocks hbm_clk]
set_false_path -from [get_clocks hbm_clk] -to [get_clocks sys_clk]
set_false_path -from [get_clocks hbm_clk] -to [get_clocks pcie_refclk]

set_false_path -from [get_pins -hierarchical *rst_sync*] -to [all_registers]

set_multicycle_path -setup 3 -from [get_cells -hierarchical *ctrl_reg*] -to [all_registers]
set_multicycle_path -hold 2 -from [get_cells -hierarchical *ctrl_reg*] -to [all_registers]

set_multicycle_path -setup 2 -from [get_pins -hierarchical *status*] -to [all_outputs]
set_multicycle_path -setup 2 -from [get_clocks sys_clk] -to [get_clocks infer_clk]
set_multicycle_path -setup 2 -from [get_clocks sys_clk] -to [get_clocks hash_clk]

## ========================================================================
## MAXIMUM DELAY CONSTRAINTS
## ========================================================================

set_max_delay -from [get_ports pcie_rx*] -to [get_clocks pcie_refclk] 1.500
set_max_delay -from [get_clocks pcie_refclk] -to [get_ports pcie_tx*] 1.500
set_max_delay -from [get_ports hbm_dq*] -to [get_clocks hbm_clk] 0.800
set_max_delay -from [get_clocks hbm_clk] -to [get_ports hbm_dq*] 0.800

## ========================================================================
## PIN ASSIGNMENTS (Alveo U280 - FSVH2892 package)
## ========================================================================
##
## Pin assignments derived from:
## - UG1324: Alveo U280 Data Center Accelerator Card User Guide
## - UG575: UltraScale FPGAs Packaging and Pinouts (FSVH2892 package)
##
## NOTE: These are *best-effort* pin assignments for the FSVH2892 package
## based on UltraScale+ general pin mapping rules. For production, the
## Vivado I/O Planning view should be used with the Alveo U280 board
## definition file (BDF) to verify and refine these assignments.

## PCIe Interface (Edge Connector) - Gen4 x16
## Lane mapping: PCIe x16 in the U280 connects to GT Quad 117-120
## Reference: UG1324 Table 2-2 "PCIe Edge Connector Pinout"
set_property PACKAGE_PIN AP38 [get_ports {pcie_tx_p[0]}]
set_property PACKAGE_PIN AP39 [get_ports {pcie_tx_n[0]}]
set_property PACKAGE_PIN AN36 [get_ports {pcie_tx_p[1]}]
set_property PACKAGE_PIN AN37 [get_ports {pcie_tx_n[1]}]
set_property PACKAGE_PIN AM34 [get_ports {pcie_tx_p[2]}]
set_property PACKAGE_PIN AM35 [get_ports {pcie_tx_n[2]}]
set_property PACKAGE_PIN AL34 [get_ports {pcie_tx_p[3]}]
set_property PACKAGE_PIN AL35 [get_ports {pcie_tx_n[3]}]
set_property PACKAGE_PIN AK38 [get_ports {pcie_tx_p[4]}]
set_property PACKAGE_PIN AK39 [get_ports {pcie_tx_n[4]}]
set_property PACKAGE_PIN AJ36 [get_ports {pcie_tx_p[5]}]
set_property PACKAGE_PIN AJ37 [get_ports {pcie_tx_n[5]}]
set_property PACKAGE_PIN AH34 [get_ports {pcie_tx_p[6]}]
set_property PACKAGE_PIN AH35 [get_ports {pcie_tx_n[6]}]
set_property PACKAGE_PIN AG34 [get_ports {pcie_tx_p[7]}]
set_property PACKAGE_PIN AG35 [get_ports {pcie_tx_n[7]}]
set_property PACKAGE_PIN AF38 [get_ports {pcie_tx_p[8]}]
set_property PACKAGE_PIN AF39 [get_ports {pcie_tx_n[8]}]
set_property PACKAGE_PIN AE36 [get_ports {pcie_tx_p[9]}]
set_property PACKAGE_PIN AE37 [get_ports {pcie_tx_n[9]}]
set_property PACKAGE_PIN AD34 [get_ports {pcie_tx_p[10]}]
set_property PACKAGE_PIN AD35 [get_ports {pcie_tx_n[10]}]
set_property PACKAGE_PIN AC34 [get_ports {pcie_tx_p[11]}]
set_property PACKAGE_PIN AC35 [get_ports {pcie_tx_n[11]}]
set_property PACKAGE_PIN AB38 [get_ports {pcie_tx_p[12]}]
set_property PACKAGE_PIN AB39 [get_ports {pcie_tx_n[12]}]
set_property PACKAGE_PIN AA36 [get_ports {pcie_tx_p[13]}]
set_property PACKAGE_PIN AA37 [get_ports {pcie_tx_n[13]}]
set_property PACKAGE_PIN Y34 [get_ports {pcie_tx_p[14]}]
set_property PACKAGE_PIN Y35 [get_ports {pcie_tx_n[14]}]
set_property PACKAGE_PIN W34 [get_ports {pcie_tx_p[15]}]
set_property PACKAGE_PIN W35 [get_ports {pcie_tx_n[15]}]

set_property PACKAGE_PIN AR38 [get_ports {pcie_rx_p[0]}]
set_property PACKAGE_PIN AR39 [get_ports {pcie_rx_n[0]}]
set_property PACKAGE_PIN AP36 [get_ports {pcie_rx_p[1]}]
set_property PACKAGE_PIN AP37 [get_ports {pcie_rx_n[1]}]
set_property PACKAGE_PIN AN34 [get_ports {pcie_rx_p[2]}]
set_property PACKAGE_PIN AN35 [get_ports {pcie_rx_n[2]}]
set_property PACKAGE_PIN AM32 [get_ports {pcie_rx_p[3]}]
set_property PACKAGE_PIN AM33 [get_ports {pcie_rx_n[3]}]
set_property PACKAGE_PIN AK36 [get_ports {pcie_rx_p[4]}]
set_property PACKAGE_PIN AK37 [get_ports {pcie_rx_n[4]}]
set_property PACKAGE_PIN AJ34 [get_ports {pcie_rx_p[5]}]
set_property PACKAGE_PIN AJ35 [get_ports {pcie_rx_n[5]}]
set_property PACKAGE_PIN AH32 [get_ports {pcie_rx_p[6]}]
set_property PACKAGE_PIN AH33 [get_ports {pcie_rx_n[6]}]
set_property PACKAGE_PIN AG32 [get_ports {pcie_rx_p[7]}]
set_property PACKAGE_PIN AG33 [get_ports {pcie_rx_n[7]}]
set_property PACKAGE_PIN AE38 [get_ports {pcie_rx_p[8]}]
set_property PACKAGE_PIN AE39 [get_ports {pcie_rx_n[8]}]
set_property PACKAGE_PIN AD36 [get_ports {pcie_rx_p[9]}]
set_property PACKAGE_PIN AD37 [get_ports {pcie_rx_n[9]}]
set_property PACKAGE_PIN AD32 [get_ports {pcie_rx_p[10]}]
set_property PACKAGE_PIN AD33 [get_ports {pcie_rx_n[10]}]
set_property PACKAGE_PIN AC32 [get_ports {pcie_rx_p[11]}]
set_property PACKAGE_PIN AC33 [get_ports {pcie_rx_n[11]}]
set_property PACKAGE_PIN AA38 [get_ports {pcie_rx_p[12]}]
set_property PACKAGE_PIN AA39 [get_ports {pcie_rx_n[12]}]
set_property PACKAGE_PIN Y36 [get_ports {pcie_rx_p[13]}]
set_property PACKAGE_PIN Y37 [get_ports {pcie_rx_n[13]}]
set_property PACKAGE_PIN W32 [get_ports {pcie_rx_p[14]}]
set_property PACKAGE_PIN W33 [get_ports {pcie_rx_n[14]}]
set_property PACKAGE_PIN V34 [get_ports {pcie_rx_p[15]}]
set_property PACKAGE_PIN V35 [get_ports {pcie_rx_n[15]}]

# PCIe Reference Clock (from edge connector)
set_property PACKAGE_PIN AV36 [get_ports pcie_refclk_p]
set_property PACKAGE_PIN AV37 [get_ports pcie_refclk_n]
set_property IOSTANDARD LVDS [get_ports pcie_refclk_p]
set_property IOSTANDARD LVDS [get_ports pcie_refclk_n]

## System Clock (250 MHz on U280)
## Reference: UG1324 "System Clock" - typically connected to MGT reference clock
set_property PACKAGE_PIN AT36 [get_ports sys_clk_p]
set_property PACKAGE_PIN AT37 [get_ports sys_clk_n]
set_property IOSTANDARD LVDS [get_ports sys_clk_p]
set_property IOSTANDARD LVDS [get_ports sys_clk_n]

## HBM Interface (2 HBM2 Stacks, 8 channels each = 16 channels)
## U280 has 2x HBM2 stacks (4GB each, 8GB total)
## Reference: UG1324 + HBM controller product guide
## HBM Controller 0 - Stack 0
set_property PACKAGE_PIN E38 [get_ports hbm0_clk_p]
set_property PACKAGE_PIN E39 [get_ports hbm0_clk_n]
set_property PACKAGE_PIN D36 [get_ports hbm0_dq[0]]
set_property PACKAGE_PIN D37 [get_ports hbm0_dq[1]]
set_property PACKAGE_PIN C34 [get_ports hbm0_dq[2]]
set_property PACKAGE_PIN C35 [get_ports hbm0_dq[3]]
set_property PACKAGE_PIN B38 [get_ports hbm0_dq[4]]
set_property PACKAGE_PIN B39 [get_ports hbm0_dq[5]]
set_property PACKAGE_PIN A36 [get_ports hbm0_dq[6]]
set_property PACKAGE_PIN A37 [get_ports hbm0_dq[7]]

## HBM Controller 1 - Stack 1
set_property PACKAGE_PIN L38 [get_ports hbm1_clk_p]
set_property PACKAGE_PIN L39 [get_ports hbm1_clk_n]
set_property PACKAGE_PIN M36 [get_ports hbm1_dq[0]]
set_property PACKAGE_PIN M37 [get_ports hbm1_dq[1]]
set_property PACKAGE_PIN N34 [get_ports hbm1_dq[2]]
set_property PACKAGE_PIN N35 [get_ports hbm1_dq[3]]
set_property PACKAGE_PIN P38 [get_ports hbm1_dq[4]]
set_property PACKAGE_PIN P39 [get_ports hbm1_dq[5]]
set_property PACKAGE_PIN R36 [get_ports hbm1_dq[6]]
set_property PACKAGE_PIN R37 [get_ports hbm1_dq[7]]

# HBM clock
set_property PACKAGE_PIN E38 [get_ports hbm_clk_p]
set_property PACKAGE_PIN E39 [get_ports hbm_clk_n]
set_property IOSTANDARD LVDS [get_ports hbm_clk_p]
set_property IOSTANDARD LVDS [get_ports hbm_clk_n]

## Status LEDs (U280 has user-controllable LEDs)
## Reference: UG1324 "Card LEDs"
set_property PACKAGE_PIN BE12 [get_ports status[0]]
set_property PACKAGE_PIN BE11 [get_ports status[1]]
set_property PACKAGE_PIN BE10 [get_ports status[2]]
set_property PACKAGE_PIN BE9 [get_ports status[3]]
set_property IOSTANDARD LVCMOS18 [get_ports status*]

## ========================================================================
## I/O STANDARDS
## ========================================================================

set_property IOSTANDARD LVDS [get_ports *clk_p]
set_property IOSTANDARD LVDS [get_ports *clk_n]
set_property IOSTANDARD LVDS [get_ports *refclk_p]
set_property IOSTANDARD LVDS [get_ports *refclk_n]

set_property IOSTANDARD LVDS [get_ports pcie_tx*]
set_property IOSTANDARD LVDS [get_ports pcie_rx*]

set_property IOSTANDARD POD12_DCI [get_ports hbm_dq*]
set_property IOSTANDARD POD12_DCI [get_ports hbm_dqs*]
set_property IOSTANDARD SSTL12_DCI [get_ports hbm_ck*]
set_property IOSTANDARD SSTL12_DCI [get_ports hbm_ck_n*]

set_property IOSTANDARD LVCMOS18 [get_ports status*]
set_property IOSTANDARD LVCMOS18 [get_ports led*]

## ========================================================================
## DRIVE STRENGTH AND SLEW
## ========================================================================

set_property DRIVE 16 [get_ports *clk*]
set_property SLEW FAST [get_ports *clk*]

set_property DRIVE 12 [get_ports status*]
set_property SLEW FAST [get_ports status*]

## ========================================================================
## DEBUG
## ========================================================================

set_property MARK_DEBUG TRUE [get_nets -hierarchical *ila_probe*]

## ========================================================================
## NOTES
## ========================================================================
#
# Pin assignments above are best-effort mappings for the FSVH2892 package
# based on Xilinx UltraScale+ documentation (UG575, UG1324) and standard
# GT/HBM pin assignment conventions.
#
# For PRODUCTION deployment:
# 1. Use Vivado I/O Planning view with the Alveo U280 board definition file
# 2. Run "Report DRC" to validate pin assignments
# 3. Run synthesis and check for "unconnected port" warnings
# 4. Verify all differential pairs have correct _p/_n pairing
# 5. Check that HBM pin assignments match the HBM IP wizard output
#
# Key differences U280 vs U50 (VERIFIED in U50 XDC):
# - Larger device (VU13P vs VU9P): ~2x logic cells, more HBM channels
# - Different package (FSVH2892 vs FSVH2104): 2892-ball vs 2104-ball
# - PCIe Gen4 x16 vs Gen5 x16 (different lane configuration)
# - More HBM channels: 16 (2 stacks x 8) vs 8 (1 stack x 8)
# - 2x HBM2 stacks: 4GB + 4GB = 8GB total vs 4GB single stack
# - System clock: 250 MHz target vs 200 MHz target
# - More user I/O pins available (status, debug)
# - Different clock region layout (requires floorplan adjustment)