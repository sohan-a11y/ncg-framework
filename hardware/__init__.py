"""NCG Hardware Package - FPGA RTL and Simulation."""

from __future__ import annotations

from .python_sim import (
    NcgHardwareSim,
    SHA256_H0,
    SHA256_K,
    Sha256TestVectors,
    sha256_compress_block,
    sha256_hash,
    sha256_pad_message,
)
from .simulation import (
    DCPMGenerator_HW,
    NCGHardwareValidator,
    ReferenceModel,
    SimulationConfig,
    SimulationResult,
    VerilatorSimulator,
    create_testbench_template,
    profile_hardware_performance,
    quick_simulation,
    run_full_simulation_suite,
    run_verilator_lint,
    run_verilator_simulation,
)

__all__ = [
    "VerilatorSimulator",
    "ReferenceModel",
    "DCPMGenerator_HW",
    "NCGHardwareValidator",
    "SimulationConfig",
    "SimulationResult",
    "run_verilator_simulation",
    "run_verilator_lint",
    "create_testbench_template",
    "quick_simulation",
    "run_full_simulation_suite",
    "profile_hardware_performance",
    "NcgHardwareSim",
    "Sha256TestVectors",
    "sha256_hash",
    "sha256_compress_block",
    "sha256_pad_message",
    "SHA256_K",
    "SHA256_H0",
]
