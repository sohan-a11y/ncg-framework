# NCG FPGA Constraints for AMD Xilinx Alveo U50
# 
# This file contains pin assignments, clock constraints, and timing constraints
# for the NCG design targeting the Alveo U50 (xcu50-fsvh2104-2-e) card.
#
# Device: xcu50-fsvh2104-2-e (UltraScale+ VU9P)
# Package: FSVH2104
# Speed Grade: -2 (0.9V)
# Temperature: Industrial (-40C to +100C)

## ========================================================================
## CLOCK CONSTRAINTS
## ========================================================================

# System clock - 200 MHz (from PCIe reference clock via IBUFDS_GTE4)
create_clock -name sys_clk -period 5.000 [get_ports sys_clk_p]
create_clock -name sys_clk_n -period 5.000 [get_ports sys_clk_n]

# PCIe reference clock - 100 MHz (from PCIe edge connector)
create_clock -name pcie_refclk -period 10.000 [get_ports pcie_refclk_p]
create_clock -name pcie_refclk_n -period 10.000 [get_ports pcie_refclk_n]

# HBM controller clock - 400 MHz (HBM2 PHY clock)
create_clock -name hbm_clk -period 2.500 [get_ports hbm_clk_p]
create_clock -name hbm_clk_n -period 2.500 [get_ports hbm_clk_n]

# Generated clocks from MMCM/PLL
# Inference core clock domain
create_generated_clock -name infer_clk -source [get_pins sys_clk_mmcmm/CLKOUT0] -divide_by 1 [get_pins sys_clk_mmcmm/CLKOUT0]

# Hashing array clock domain (can be same or different)
create_generated_clock -name hash_clk -source [get_pins sys_clk_mmcmm/CLKOUT1] -divide_by 1 [get_pins sys_clk_mmcmm/CLKOUT1]

# HBM controller clock domain
create_generated_clock -name hbm_ctrl_clk -source [get_pins hbm_clk_mmcmm/CLKOUT0] -divide_by 1 [get_pins hbm_clk_mmcmm/CLKOUT0]

## ========================================================================
## CLOCK UNCERTAINTY AND JITTER
## ========================================================================

# Clock uncertainty for system clock (200 MHz)
set_clock_uncertainty -setup 0.050 [get_clocks sys_clk]
set_clock_uncertainty -hold 0.030 [get_clocks sys_clk]

# Clock uncertainty for PCIe clock
set_clock_uncertainty -setup 0.050 [get_clocks pcie_refclk]
set_clock_uncertainty -hold 0.030 [get_clocks pcie_refclk]

# Clock uncertainty for HBM clock
set_clock_uncertainty -setup 0.040 [get_clocks hbm_clk]
set_clock_uncertainty -hold 0.020 [get_clocks hbm_clk]

# Generated clock uncertainty
set_clock_uncertainty -setup 0.060 [get_clocks infer_clk]
set_clock_uncertainty -setup 0.060 [get_clocks hash_clk]
set_clock_uncertainty -setup 0.050 [get_clocks hbm_ctrl_clk]

## ========================================================================
## CLOCK GROUPS AND ASYNCHRONOUS CLOCK DOMAINS
## ========================================================================

# Asynchronous clock groups (no CDC needed between these domains)
set_clock_groups -asynchronous -group [get_clocks sys_clk] -group [get_clocks pcie_refclk] -group [get_clocks hbm_clk]

# Synchronous clock groups (CDC required)
set_clock_groups -logically_exclusive -group [get_clocks infer_clk] -group [get_clocks hash_clk]
set_clock_groups -logically_exclusive -group [get_clocks hbm_ctrl_clk] -group [get_clocks infer_clk]

## ========================================================================
## INPUT/OUTPUT DELAYS
## ========================================================================

# PCIe interface delays
set_input_delay -clock pcie_refclk -min 0.500 [get_ports pcie_rx*]
set_input_delay -clock pcie_refclk -max 1.500 [get_ports pcie_rx*]
set_output_delay -clock pcie_refclk -min 0.500 [get_ports pcie_tx*]
set_output_delay -clock pcie_refclk -max 1.500 [get_ports pcie_tx*]

# HBM interface delays
set_input_delay -clock hbm_clk -min 0.300 [get_ports hbm_dq*]
set_input_delay -clock hbm_clk -max 0.800 [get_ports hbm_dq*]
set_output_delay -clock hbm_clk -min 0.300 [get_ports hbm_dq*]
set_output_delay -clock hbm_clk -max 0.800 [get_ports hbm_dq*]

# Status/LED outputs
set_output_delay -clock sys_clk -min 0.500 [get_ports status*]
set_output_delay -clock sys_clk -max 1.500 [get_ports status*]

## ========================================================================
## FALSE PATHS AND MULTI-CYCLE PATHS
## ========================================================================

# False paths across asynchronous clock domains
set_false_path -from [get_clocks sys_clk] -to [get_clocks pcie_refclk]
set_false_path -from [get_clocks sys_clk] -to [get_clocks hbm_clk]
set_false_path -from [get_clocks pcie_refclk] -to [get_clocks sys_clk]
set_false_path -from [get_clocks pcie_refclk] -to [get_clocks hbm_clk]
set_false_path -from [get_clocks hbm_clk] -to [get_clocks sys_clk]
set_false_path -from [get_clocks hbm_clk] -to [get_clocks pcie_refclk]

# False paths from reset logic
set_false_path -from [get_pins -hierarchical *rst_sync*] -to [all_registers]

# Multi-cycle paths for control/status registers (slow paths)
set_multicycle_path -setup 3 -from [get_cells -hierarchical *ctrl_reg*] -to [all_registers]
set_multicycle_path -hold 2 -from [get_cells -hierarchical *ctrl_reg*] -to [all_registers]

# Multi-cycle paths for status outputs
set_multicycle_path -setup 2 -from [get_pins -hierarchical *status*] -to [all_outputs]

# Multi-cycle paths for cross-clock domain paths
set_multicycle_path -setup 2 -from [get_clocks sys_clk] -to [get_clocks infer_clk]
set_multicycle_path -setup 2 -from [get_clocks sys_clk] -to [get_clocks hash_clk]

## ========================================================================
## MAXIMUM DELAY CONSTRAINTS
## ========================================================================

# Max delay for PCIe signals
set_max_delay -from [get_ports pcie_rx*] -to [get_clocks pcie_refclk] 1.500
set_max_delay -from [get_clocks pcie_refclk] -to [get_ports pcie_tx*] 1.500

# Max delay for HBM signals
set_max_delay -from [get_ports hbm_dq*] -to [get_clocks hbm_clk] 0.800
set_max_delay -from [get_clocks hbm_clk] -to [get_ports hbm_dq*] 0.800

## ========================================================================
## PIN ASSIGNMENTS (Alveo U50 - FSVH2104 package)
## ========================================================================

## PCIe Interface (Edge Connector)
# PCIe Gen5 x16 - Lanes 0-15
set_property PACKAGE_PIN AA3  [get_ports pcie_tx_p[0]]
set_property PACKAGE_PIN AA4  [get_ports pcie_tx_n[0]]
set_property PACKAGE_PIN AB1  [get_ports pcie_tx_p[1]]
set_property PACKAGE_PIN AB2  [get_ports pcie_tx_n[1]]
set_property PACKAGE_PIN AC3  [get_ports pcie_tx_p[2]]
set_property PACKAGE_PIN AC4  [get_ports pcie_tx_n[2]]
set_property PACKAGE_PIN AD1  [get_ports pcie_tx_p[3]]
set_property PACKAGE_PIN AD2  [get_ports pcie_tx_n[3]]
set_property PACKAGE_PIN AE3  [get_ports pcie_tx_p[4]]
set_property PACKAGE_PIN AE4  [get_ports pcie_tx_n[4]]
set_property PACKAGE_PIN AF1  [get_ports pcie_tx_p[5]]
set_property PACKAGE_PIN AF2  [get_ports pcie_tx_n[5]]
set_property PACKAGE_PIN AG3  [get_ports pcie_tx_p[6]]
set_property PACKAGE_PIN AG4  [get_ports pcie_tx_n[6]]
set_property PACKAGE_PIN AH1  [get_ports pcie_tx_p[7]]
set_property PACKAGE_PIN AH2  [get_ports pcie_tx_n[7]]
set_property PACKAGE_PIN AJ3  [get_ports pcie_tx_p[8]]
set_property PACKAGE_PIN AJ4  [get_ports pcie_tx_n[8]]
set_property PACKAGE_PIN AK1  [get_ports pcie_tx_p[9]]
set_property PACKAGE_PIN AK2  [get_ports pcie_tx_n[9]]
set_property PACKAGE_PIN AL3  [get_ports pcie_tx_p[10]]
set_property PACKAGE_PIN AL4  [get_ports pcie_tx_n[10]]
set_property PACKAGE_PIN AM1  [get_ports pcie_tx_p[11]]
set_property PACKAGE_PIN AM2  [get_ports pcie_tx_n[11]]
set_property PACKAGE_PIN AN3  [get_ports pcie_tx_p[12]]
set_property PACKAGE_PIN AN4  [get_ports pcie_tx_n[12]]
set_property PACKAGE_PIN AP1  [get_ports pcie_tx_p[13]]
set_property PACKAGE_PIN AP2  [get_ports pcie_tx_n[13]]
set_property PACKAGE_PIN AR3  [get_ports pcie_tx_p[14]]
set_property PACKAGE_PIN AR4  [get_ports pcie_tx_n[14]]
set_property PACKAGE_PIN AT1  [get_ports pcie_tx_p[15]]
set_property PACKAGE_PIN AT2  [get_ports pcie_tx_n[15]]

set_property PACKAGE_PIN Y3   [get_ports pcie_rx_p[0]]
set_property PACKAGE_PIN Y4   [get_ports pcie_rx_n[0]]
set_property PACKAGE_PIN W1   [get_ports pcie_rx_p[1]]
set_property PACKAGE_PIN W2   [get_ports pcie_rx_n[1]]
set_property PACKAGE_PIN V3   [get_ports pcie_rx_p[2]]
set_property PACKAGE_PIN V4   [get_ports pcie_rx_n[2]]
set_property PACKAGE_PIN U1   [get_ports pcie_rx_p[3]]
set_property PACKAGE_PIN U2   [get_ports pcie_rx_n[3]]
set_property PACKAGE_PIN T3   [get_ports pcie_rx_p[4]]
set_property PACKAGE_PIN T4   [get_ports pcie_rx_n[4]]
set_property PACKAGE_PIN R1   [get_ports pcie_rx_p[5]]
set_property PACKAGE_PIN R2   [get_ports pcie_rx_n[5]]
set_property PACKAGE_PIN P3   [get_ports pcie_rx_p[6]]
set_property PACKAGE_PIN P4   [get_ports pcie_rx_n[6]]
set_property PACKAGE_PIN N1   [get_ports pcie_rx_p[7]]
set_property PACKAGE_PIN N2   [get_ports pcie_rx_n[7]]
set_property PACKAGE_PIN M3   [get_ports pcie_rx_p[8]]
set_property PACKAGE_PIN M4   [get_ports pcie_rx_n[8]]
set_property PACKAGE_PIN L1   [get_ports pcie_rx_p[9]]
set_property PACKAGE_PIN L2   [get_ports pcie_rx_n[9]]
set_property PACKAGE_PIN K3   [get_ports pcie_rx_p[10]]
set_property PACKAGE_PIN K4   [get_ports pcie_rx_n[10]]
set_property PACKAGE_PIN J1   [get_ports pcie_rx_p[11]]
set_property PACKAGE_PIN J2   [get_ports pcie_rx_n[11]]
set_property PACKAGE_PIN H3   [get_ports pcie_rx_p[12]]
set_property PACKAGE_PIN H4   [get_ports pcie_rx_n[12]]
set_property PACKAGE_PIN G1   [get_ports pcie_rx_p[13]]
set_property PACKAGE_PIN G2   [get_ports pcie_rx_n[13]]
set_property PACKAGE_PIN F3   [get_ports pcie_rx_p[14]]
set_property PACKAGE_PIN F4   [get_ports pcie_rx_n[14]]
set_property PACKAGE_PIN E1   [get_ports pcie_rx_p[15]]
set_property PACKAGE_PIN E2   [get_ports pcie_rx_n[15]]

# PCIe Reference Clock
set_property PACKAGE_PIN AW5  [get_ports pcie_refclk_p]
set_property PACKAGE_PIN AW6  [get_ports pcie_refclk_n]
set_property IOSTANDARD LVDS  [get_ports pcie_refclk_p]
set_property IOSTANDARD LVDS  [get_ports pcie_refclk_n]

## System Clock (200 MHz from PCIe refclk via MMCM)
set_property PACKAGE_PIN AU5  [get_ports sys_clk_p]
set_property PACKAGE_PIN AU6  [get_ports sys_clk_n]
set_property IOSTANDARD LVDS  [get_ports sys_clk_p]
set_property IOSTANDARD LVDS  [get_ports sys_clk_n]

## HBM Interface (HBM2 Stacks 0 and 1)
# HBM Stack 0 (Channels 0-3)
set_property PACKAGE_PIN ... [get_ports hbm0_*]
# HBM Stack 1 (Channels 4-7)  
set_property PACKAGE_PIN ... [get_ports hbm1_*]
# HBM Reference Clock
set_property PACKAGE_PIN ... [get_ports hbm_clk_p]
set_property PACKAGE_PIN ... [get_ports hbm_clk_n]
set_property IOSTANDARD LVDS  [get_ports hbm_clk_p]
set_property IOSTANDARD LVDS  [get_ports hbm_clk_n]

## Status LEDs
set_property PACKAGE_PIN AK14 [get_ports status[0]]
set_property PACKAGE_PIN AJ14 [get_ports status[1]]
set_property PACKAGE_PIN AH14 [get_ports status[2]]
set_property PACKAGE_PIN AG14 [get_ports status[3]]
set_property IOSTANDARD LVCMOS18 [get_ports status*]

## QSFP (Optional - for multi-card scaling)
# set_property PACKAGE_PIN ... [get_ports qsfp_*]

## ========================================================================
## I/O STANDARDS
## ========================================================================

# Differential clocks
set_property IOSTANDARD LVDS [get_ports *clk_p]
set_property IOSTANDARD LVDS [get_ports *clk_n]
set_property IOSTANDARD LVDS [get_ports *refclk_p]
set_property IOSTANDARD LVDS [get_ports *refclk_n]

# PCIe
set_property IOSTANDARD LVDS [get_ports pcie_tx*]
set_property IOSTANDARD LVDS [get_ports pcie_rx*]

# HBM
set_property IOSTANDARD POD12_DCI [get_ports hbm_dq*]
set_property IOSTANDARD POD12_DCI [get_ports hbm_dqs*]
set_property IOSTANDARD SSTL12_DCI [get_ports hbm_ck*]
set_property IOSTANDARD SSTL12_DCI [get_ports hbm_ck_n*]

# Status/Control
set_property IOSTANDARD LVCMOS18 [get_ports status*]
set_property IOSTANDARD LVCMOS18 [get_ports led*]

## ========================================================================
## DRIVE STRENGTH AND SLEW
## ========================================================================

# High drive for clock outputs
set_property DRIVE 16 [get_ports *clk*]
set_property SLEW FAST [get_ports *clk*]

# Standard drive for data
set_property DRIVE 12 [get_ports status*]
set_property SLEW FAST [get_ports status*]

## ========================================================================
## TERMINATION
## ========================================================================

# PCIe termination (handled by PHY IP)
# HBM termination (handled by PHY IP)

# Status outputs
set_property DIFF_TERM_ADV TERM_100 [get_ports status*]

## ========================================================================
## PACKAGE PIN CONSTRAINTS FOR DEBUG
## ========================================================================

# ILA probes
set_property MARK_DEBUG TRUE [get_nets -hierarchical *ila_probe*]

## ========================================================================
## POWER AND THERMAL CONSTRAINTS
## ========================================================================

# Power budget: 150W max (U50 TDP)
# Thermal: Junction temp < 100C at max power
# These are checked during implementation, not constrained here

## ========================================================================
## END OF CONSTRAINTS
## ========================================================================

# Note: Specific HBM pin assignments depend on the exact HBM stack configuration
# and must be obtained from the Alveo U50 board documentation and HBM IP wizard.
# The '...' placeholders above must be replaced with actual pin assignments
# from the U50 pinout table for the HBM stacks.

# For complete pin assignments, refer to:
# - UG1303: Alveo U50 Data Center Accelerator Card User Guide
# - UG1267: UltraScale+ HBM Controller Product Guide
# - UG1085: Vivado Design Suite Properties Reference Guide