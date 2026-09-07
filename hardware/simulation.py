"""Comprehensive NCG Hardware Simulation Infrastructure

This module provides a complete simulation framework for NCG hardware designs
using Verilator, with integration against the software reference model for
cycle-accurate validation and performance profiling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from model import NCGTransformer, create_model, PasswordTokenizer, DCPMGenerator  # type: ignore[import-untyped]
from model.data import BreachContext  # type: ignore[import-untyped]
from ncg.config import ModelConfig, InferenceConfig  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """Configuration for hardware simulation."""
    top_module: str = "ncg_top"
    design_dir: Path = Path("hardware/rtl")
    build_dir: Optional[Path] = None
    trace: bool = True
    cycles: int = 100000
    timeout_ms: int = 5000
    verilator_args: list[str] = field(default_factory=list)
    

@dataclass
class SimulationResult:
    """Results from a simulation run."""
    success: bool
    cycles: int
    outputs: dict[str, list[int]]
    waveforms: Optional[Path] = None
    error: Optional[str] = None
    performance: dict[str, float] = field(default_factory=dict)
    validation: dict[str, bool] = field(default_factory=dict)


class ReferenceModel:
    """Software reference model for hardware validation."""
    
    def __init__(self, config: ModelConfig, inference_config: InferenceConfig):
        self.config = config
        self.inference_config = inference_config
        self.model = create_model(config)
        self.tokenizer = PasswordTokenizer(max_seq_len=config.max_seq_len)
        self.generator = DCPMGenerator(
            self.model, self.tokenizer, inference_config=inference_config
        )
    
    def generate_dcmp(self, context: BreachContext) -> "np.ndarray":
        """Generate DCPM matrix from context."""
        dcmp = self.generator.generate_dcmp(context)
        return dcmp.detach().cpu().numpy()  # type: ignore[no-any-return]
    
    def generate_candidates(self, context: BreachContext, num: int = 100) -> list[str]:
        """Generate password candidates."""
        return self.generator.generate_candidates(context, num_candidates=num)  # type: ignore[no-any-return]
    
    def sha256_hash(self, data: bytes) -> bytes:
        """Compute SHA-256 hash."""
        return hashlib.sha256(data).digest()
    
    def validate_candidate(self, candidate: str, target_hash: bytes) -> bool:
        """Validate candidate against target hash."""
        return self.sha256_hash(candidate.encode()) == target_hash


class DCPMGenerator_HW:
    """Hardware-compatible DCPM generator for test stimulus."""
    
    def __init__(self, vocab_size: int = 96, max_seq_len: int = 64, bram_data_width: int = 512):
        self.vocab_size = vocab_size
        self.max_seq_len = max_seq_len
        self.bram_data_width = bram_data_width
    
    def generate_dcmp_bram(self, context: BreachContext) -> list[int]:
        """Generate DCPM formatted for BRAM loading."""
        # Simplified: generate probability matrix for each position
        # In hardware, this would be the actual DCPM from the transformer
        dcmp_data = []
        for pos in range(16):  # MAX_SEQ_LEN for simulation
            # Each BRAM word contains probability distribution for one position
            # Format: 8 bytes per vocab entry (simplified)
            word = 0
            for v in range(8):  # Reduced vocab for simulation
                prob = np.random.randint(0, 256)
                word |= (prob << (v * 8))
            dcmp_data.append(word)
        return dcmp_data
    
    def generate_test_dcmp(self, seed: int = 42) -> list[int]:
        """Generate deterministic test DCPM."""
        np.random.seed(seed)
        return self.generate_dcmp_bram(BreachContext())


class VerilatorSimulator:
    """Enhanced Verilator simulator with automated testbench generation."""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.build_dir = config.build_dir or Path(tempfile.mkdtemp()) / "verilator_build"
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.compiled = False
        self.design_path = config.design_dir / f"{config.top_module}.sv"
    
    def compile(self) -> bool:
        """Compile the SystemVerilog design with Verilator."""
        logger.info(f"Compiling {self.config.top_module} with Verilator...")
        
        # Find all SystemVerilog files
        sv_files = list(self.config.design_dir.glob("*.sv"))
        if not sv_files:
            logger.error(f"No SystemVerilog files found in {self.config.design_dir}")
            return False
        
        cmd = [
            "verilator",
            "--cc",
            "--exe",
            "--trace" if self.config.trace else "",
            "--trace-structs" if self.config.trace else "",
            "-O3",
            "-x-initial",
            "-x-assign",
            "--top-module", self.config.top_module,
            "-Mdir", str(self.build_dir),
            *[str(f) for f in sv_files],
            *self.config.verilator_args,
        ]
        cmd = [c for c in cmd if c]  # Remove empty strings
        
        logger.debug(f"Verilator command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"Verilator compilation failed:\n{result.stderr}")
            return False
        
        # Build the C++ simulation
        make_cmd = ["make", "-C", str(self.build_dir), "-f", f"V{self.config.top_module}.mk", f"V{self.config.top_module}"]
        result = subprocess.run(make_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"Make failed:\n{result.stderr}")
            return False
        
        self.compiled = True
        logger.info("Compilation successful")
        return True
    
    def run_testbench(self, testbench_name: str) -> SimulationResult:
        """Run a specific SystemVerilog testbench."""
        if not self.compiled:
            if not self.compile():
                return SimulationResult(success=False, cycles=0, outputs={}, error="Compilation failed")
        
        # Find testbench file
        tb_path = self.config.design_dir / f"{testbench_name}_tb.sv"
        if not tb_path.exists():
            return SimulationResult(success=False, cycles=0, outputs={}, error=f"Testbench not found: {tb_path}")
        
        # Run the testbench using Verilator's sim
        sim_exe = self.build_dir / f"V{self.config.top_module}"
        if not sim_exe.exists():
            # Try to find the compiled testbench
            sim_exe = self.build_dir / "sim"
        
        if not sim_exe.exists():
            return SimulationResult(success=False, cycles=0, outputs={}, error="Simulation executable not found")
        
        # Run simulation
        start_time = time.time()
        try:
            result = subprocess.run(
                [str(sim_exe)],
                capture_output=True,
                text=True,
                cwd=str(self.build_dir),
                timeout=self.config.timeout_ms / 1000,
            )
            elapsed = time.time() - start_time
            
            if result.returncode != 0:
                return SimulationResult(
                    success=False,
                    cycles=0,
                    outputs={},
                    error=f"Simulation failed:\n{result.stderr}",
                    performance={"simulation_time_s": elapsed}
                )
            
            # Parse outputs
            outputs = self._parse_simulation_output(result.stdout)
            
            # Check for validation results
            validation = self._parse_validation_output(result.stdout)
            
            return SimulationResult(
                success=True,
                cycles=self._extract_cycles(result.stdout),
                outputs=outputs,
                performance={
                    "simulation_time_s": elapsed,
                    "cycles_per_second": self._extract_cycles(result.stdout) / elapsed if elapsed > 0 else 0
                },
                validation=validation
            )
            
        except subprocess.TimeoutExpired:
            return SimulationResult(
                success=False,
                cycles=0,
                outputs={},
                error=f"Simulation timeout after {self.config.timeout_ms}ms",
                performance={"simulation_time_s": self.config.timeout_ms / 1000}
            )
        except Exception as e:
            return SimulationResult(
                success=False,
                cycles=0,
                outputs={},
                error=str(e)
            )
    
    def _parse_simulation_output(self, stdout: str) -> dict[str, list[int]]:
        """Parse simulation output for signal values."""
        outputs: dict[str, list[int]] = {}
        for line in stdout.strip().split("\n"):
            if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                parts = line.split(":")
                if len(parts) >= 2:
                    key = parts[0].strip()
                    try:
                        val = int(parts[1].strip().split()[0], 0)
                        if key not in outputs:
                            outputs[key] = []
                        outputs[key].append(val)
                    except ValueError:
                        pass
        return outputs
    
    def _parse_validation_output(self, stdout: str) -> dict[str, bool]:
        """Parse validation results from simulation output."""
        validation = {}
        for line in stdout.strip().split("\n"):
            line_lower = line.lower()
            if "validation passed" in line_lower:
                validation["output_validation"] = True
            elif "validation failed" in line_lower:
                validation["output_validation"] = False
            elif "validation passed!" in line_lower:
                validation["hash_validation"] = True
            elif "validation failed!" in line_lower:
                validation["hash_validation"] = False
        return validation
    
    def _extract_cycles(self, stdout: str) -> int:
        """Extract cycle count from simulation output."""
        for line in stdout.strip().split("\n"):
            if "cycle" in line.lower() and "total" in line.lower():
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        return int(p)
        return 0


class NCGHardwareValidator:
    """Validates hardware simulation against software reference model."""
    
    def __init__(self, reference_model: ReferenceModel):
        self.ref_model = reference_model
    
    def validate_dcmp_generation(self, context: BreachContext, hw_dcmp: list[int]) -> dict[str, Any]:
        """Validate hardware DCPM against software reference."""
        sw_dcmp = self.ref_model.generate_dcmp(context)
        
        # Compare shapes
        hw_array = np.array(hw_dcmp, dtype=np.float32)
        sw_array = sw_dcmp.astype(np.float32)
        
        # Normalize and compare
        if hw_array.shape != sw_array.shape:
            return {
                "passed": False,
                "error": f"Shape mismatch: HW={hw_array.shape}, SW={sw_array.shape}",
                "hw_shape": hw_array.shape,
                "sw_shape": sw_array.shape
            }
        
        # Compute correlation
        correlation = np.corrcoef(hw_array.flatten(), sw_array.flatten())[0, 1]
        mse = np.mean((hw_array - sw_array) ** 2)
        
        return {
            "passed": correlation > 0.95 and mse < 0.01,
            "correlation": float(correlation),
            "mse": float(mse),
            "hw_shape": hw_array.shape,
            "sw_shape": sw_array.shape
        }
    
    def validate_candidate_generation(
        self, 
        context: BreachContext, 
        hw_candidates: list[str],
        num_expected: int
    ) -> dict[str, Any]:
        """Validate hardware-generated candidates against software."""
        sw_candidates = self.ref_model.generate_candidates(context, num_expected)
        
        # Check overlap
        hw_set = set(hw_candidates)
        sw_set = set(sw_candidates)
        overlap = hw_set & sw_set
        
        return {
            "passed": len(overlap) > 0,
            "hw_count": len(hw_candidates),
            "sw_count": len(sw_candidates),
            "overlap_count": len(overlap),
            "overlap_ratio": len(overlap) / len(hw_set) if hw_set else 0,
            "unique_hw": len(hw_set - sw_set),
            "unique_sw": len(sw_set - hw_set)
        }
    
    def validate_hash_match(self, candidate: str, target_hash: bytes, hw_match: bool) -> dict[str, Any]:
        """Validate hash match detection."""
        sw_match = self.ref_model.validate_candidate(candidate, target_hash)
        
        return {
            "passed": hw_match == sw_match,
            "hw_match": hw_match,
            "sw_match": sw_match,
            "candidate": candidate
        }


def run_full_simulation_suite(
    config: Optional[SimulationConfig] = None,
    reference_config: Optional[ModelConfig] = None
) -> dict[str, SimulationResult]:
    """Run complete simulation suite for all testbenches."""
    if config is None:
        config = SimulationConfig()
    
    if reference_config is None:
        reference_config = ModelConfig(
            vocab_size=32,
            max_seq_len=16,
            d_model=64,
            n_heads=4,
            n_layers=2
        )
    
    logger.info("Starting NCG Hardware Simulation Suite")
    
    # Initialize reference model
    inference_config = InferenceConfig(top_k=10, top_p=0.9, temperature=0.8)
    ref_model = ReferenceModel(reference_config, inference_config)
    validator = NCGHardwareValidator(ref_model)
    
    # Initialize simulator
    simulator = VerilatorSimulator(config)
    
    # Testbenches to run
    testbenches = [
        "ncg_top",
        "inference_core",
        "sha256_core",
        "sha256_array",
    ]
    
    results = {}
    
    for tb in testbenches:
        logger.info(f"Running testbench: {tb}")
        result = simulator.run_testbench(tb)
        results[tb] = result
        
        if result.success:
            logger.info(f"  {tb}: PASSED ({result.cycles} cycles)")
        else:
            logger.error(f"  {tb}: FAILED - {result.error}")
    
    # Summary
    passed = sum(1 for r in results.values() if r.success)
    total = len(results)
    logger.info(f"Simulation suite complete: {passed}/{total} passed")
    
    return results


def profile_hardware_performance(
    simulator: VerilatorSimulator,
    testbench: str = "ncg_top",
    num_runs: int = 10
) -> dict[str, float | str]:
    """Profile hardware performance across multiple runs."""
    logger.info(f"Profiling {testbench} performance over {num_runs} runs...")
    
    cycles = []
    times = []
    
    for i in range(num_runs):
        result = simulator.run_testbench(testbench)
        if result.success:
            cycles.append(result.cycles)
            times.append(result.performance.get("simulation_time_s", 0))
    
    if not cycles:
        return {"error": "All runs failed"}
    
    stats: dict[str, float | str] = {
        "mean_cycles": float(np.mean(cycles)),
        "std_cycles": float(np.std(cycles)),
        "min_cycles": int(np.min(cycles)),
        "max_cycles": int(np.max(cycles)),
        "mean_time_s": float(np.mean(times)),
        "std_time_s": float(np.std(times)),
        "throughput_cycles_per_sec": float(np.mean(cycles) / np.mean(times)) if np.mean(times) > 0 else 0,
    }
    
    return stats


def generate_test_report(results: dict[str, SimulationResult], output_path: Path) -> None:
    """Generate comprehensive test report."""
    report: dict[str, Any] = {
        "summary": {
            "total_tests": len(results),
            "passed": sum(1 for r in results.values() if r.success),
            "failed": sum(1 for r in results.values() if not r.success),
            "total_cycles": sum(r.cycles for r in results.values() if r.success),
        },
        "tests": {}
    }
    
    for name, result in results.items():
        report["tests"][name] = {
            "success": result.success,
            "cycles": result.cycles,
            "error": result.error,
            "performance": result.performance,
            "validation": result.validation,
        }
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Test report saved to {output_path}")


# Convenience functions
def quick_simulation(top_module: str = "ncg_top", cycles: int = 10000) -> SimulationResult:
    """Quick simulation run with default config."""
    config = SimulationConfig(top_module=top_module, cycles=cycles)
    simulator = VerilatorSimulator(config)
    if simulator.compile():
        return simulator.run_testbench(top_module)
    return SimulationResult(success=False, cycles=0, outputs={}, error="Compilation failed")


def run_verilator_lint(design_dir: Path) -> tuple[bool, str]:
    """Run Verilator lint check on design."""
    sv_files = list(design_dir.glob("*.sv"))
    cmd = ["verilator", "--lint-only", *[str(f) for f in sv_files]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout + result.stderr


def run_verilator_simulation(
    design_path: str | Path,
    top_module: str = "top",
    cycles: int = 10000,
    trace: bool = True,
) -> SimulationResult:
    """Convenience function to run Verilator simulation."""
    config = SimulationConfig(
        top_module=top_module,
        design_dir=Path(design_path).parent if Path(design_path).is_file() else Path(design_path),
        cycles=cycles,
        trace=trace,
    )
    sim = VerilatorSimulator(config)
    if sim.compile():
        return sim.run_testbench(top_module)
    return SimulationResult(success=False, cycles=0, outputs={}, error="Compilation failed")


def create_testbench_template(module_name: str, ports: dict[str, str]) -> str:
    """Create a SystemVerilog testbench template."""
    _ = [name for name, dir in ports.items() if dir == "input"]
    _ = [name for name, dir in ports.items() if dir == "output"]
    _ = [name for name, dir in ports.items() if dir == "inout"]

    tb = f"""module {module_name}_tb;

"""
    # Clock and reset
    tb += "    logic clk;\n"
    tb += "    logic rst_n;\n\n"

    # DUT signals
    for name, direction in ports.items():
        if direction == "input":
            tb += f"    logic {name};\n"
        elif direction == "output":
            tb += f"    logic {name};\n"
        else:
            tb += f"    logic {name};\n"

    tb += f"""
    // Clock generation
    initial clk = 0;
    always #5 clk = ~clk;

    // Reset generation
    initial begin
        rst_n = 0;
        repeat (10) @(posedge clk);
        rst_n = 1;
    end

    // DUT instantiation
    {module_name} dut (
"""
    for name in ports.keys():
        tb += f"        .{name}({name}),\n"
    tb += "    );\n\n"

    # Stimulus
    tb += """    // Stimulus
    initial begin
        // Add stimulus here
        repeat (1000) @(posedge clk);
        $finish;
    end

endmodule
"""
    return tb


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example usage
    config = SimulationConfig(
        top_module="ncg_top",
        design_dir=Path("hardware/rtl"),
        cycles=50000,
        trace=True,
    )
    
    results = run_full_simulation_suite(config)
    generate_test_report(results, Path("simulation_report.json"))
    
    # Print summary
    print("\n=== Simulation Summary ===")
    for name, result in results.items():
        status = "PASS" if result.success else "FAIL"
        print(f"  {name}: {status} ({result.cycles} cycles)")