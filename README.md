<div align="center">

<h1>🧬 NCG Framework</h1>

<p><strong>A research prototype for AI-guided, breach-context-aware password candidate generation, with an FPGA hardware-acceleration sketch alongside it.</strong></p>

<p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/sohan-a11y/ncg-framework/actions"><img src="https://img.shields.io/github/actions/workflow/status/sohan-a11y/ncg-framework/ci.yml?label=CI" alt="CI"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/status-research%20prototype-orange" alt="Status: research prototype"></a>
</p>

</div>

---

## What is this?

NCG explores an alternative to wordlist-based password guessing: instead of loading gigabytes of dictionaries from disk, a small **Transformer language model** learns realistic password patterns and generates candidates conditioned on **breach context** (organization name, year, known prior leaks). A separate **SystemVerilog RTL sketch** explores what a hardware-accelerated hashing/generation pipeline for this could look like on an FPGA.

```
[Breach Context: org, year, leaks] → [Transformer: DCPM] → [Candidates] → [SHA-256 verify] → [Match?]
```

**Honest status:** the software model (training, context-conditioning, INT4 quantization-aware training, ONNX/TorchScript export) is real and working — see [Verified Results](#verified-results) below. The hardware layer is a **design sketch**, not a working accelerator: the RTL lints cleanly and is validated *algorithmically* against an independent Python reference model, but it has never been run through Verilator simulation or synthesized (see [Hardware Status](#hardware-status)). This is not a competitive replacement for Hashcat/John the Ripper — treat it as a research/education artifact, not a production tool.

## Use cases

- **Security research & education** — a complete, working example of context-conditioned password generation, INT4 quantization-aware training, and ONNX/TorchScript export, small enough to read end-to-end.
- **Authorized password-policy testing** — generate org-contextual candidate lists to test an organization's own password policy (with explicit authorization only).
- **Hardware/software co-design reference** — the RTL sketch + Python cycle-accurate reference model is a worked example of validating a hardware design's algorithm before committing to synthesis.

> **Disclaimer:** for educational and defensive security research only. Do not use against systems you do not own or lack explicit authorization to test.

## Verified Results

These numbers are from actually running the pipeline, not aspirational targets:

| Check | Result |
|---|---|
| Test suite | 73/73 passing (`pytest tests/`) |
| Context-conditioning | Verified live: same seed, different `organization` in context → measurably different, org-flavored candidates |
| Top-1000 holdout accuracy | **38.0%** (`ncg model evaluate`, 12-epoch model, 16K contextual synthetic passwords) |
| INT4 quantization-aware training | Verified: fake-quantization measurably changes the forward pass during training; gradients still flow via straight-through estimator |
| ONNX export | Numerically verified against PyTorch (max diff ~3e-6) |
| SHA-256 (hardware reference) | Matches NIST FIPS 180-4 test vectors and `hashlib` byte-for-byte |

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Check your environment
ncg doctor

# Generate a contextual training set spanning multiple organizations
# (multiple orgs is what gives the model a real signal to condition on)
ncg dataset -n 4000 --orgs "TechCorp,FinanceInc,HealthNet,EduSystems" -o data/passwords_ctx.jsonl

# Train (a released demo checkpoint is also available -- see Releases)
ncg model train -d data/passwords_ctx.jsonl -o models/ncg_ctx -e 12 -b 64 --d-model 128 --n-layers 4

# Generate candidates conditioned on breach context
ncg model generate -m models/ncg_ctx/best_model.pt -c '{"organization": "TechCorp", "year": 2026}' -n 20

# Evaluate top-N accuracy against a holdout set
ncg model evaluate -m models/ncg_ctx/best_model.pt -d data/holdout.txt -n 1000

# Export for deployment
ncg model export -m models/ncg_ctx/best_model.pt -f onnx -o model.onnx
```

A pretrained demo checkpoint (`best_model.pt`, ~19MB) is attached to the [latest Release](https://github.com/sohan-a11y/ncg-framework/releases) so you can run `generate`/`evaluate` immediately without training first.

## Architecture

```
                    Software (Phase 1 -- working)
┌───────────────────────────────────────────────────────────────┐
│  BreachContext {org, year, known_leaks}                       │
│         │                                                     │
│         ▼                                                     │
│  MetadataTokenizer ──▶ MetadataEncoder (learned embedding)    │
│         │                                                     │
│         ▼                                                     │
│  NCGTransformer (INT4 QAT, char-level, causal)                │
│         │  logits over 99-token vocab                         │
│         ▼                                                     │
│  top-k / top-p sampling ──▶ password candidates               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼ (design sketch only, see below)
                    Hardware (Phase 2/3 -- RTL sketch)
┌───────────────────────────────────────────────────────────────┐
│  inference_core.sv   -- BRAM-backed candidate-matrix walker    │
│  sha256_core.sv       -- SHA-256 compression, NIST-verified    │
│  ncg_top.sv            -- PCIe/HBM integration sketch          │
│                                                                 │
│  Validated via: RTL lint (Verilator) + independent Python      │
│  reference model (hardware/python_sim.py), NOT via RTL          │
│  co-simulation or synthesis.                                   │
└───────────────────────────────────────────────────────────────┘
```

**Stack:** Python 3.10+ · PyTorch · Click · Pydantic · ONNX/TorchScript · SystemVerilog (Verilator-lintable) · pytest

## Repository Structure

```
ncg-framework/
├── .github/workflows/      # CI (lint, typecheck, tests, build)
├── hardware/
│   ├── rtl/                # SystemVerilog top-level + testbenches
│   ├── inference_core/     # Candidate-matrix walker (RTL sketch)
│   ├── hashing_cores/      # SHA-256 core + parallel array
│   ├── python_sim.py       # Cycle-accurate Python reference model
│   └── SIMULATION_METHODOLOGY.md
├── software/
│   ├── model/               # Transformer, tokenizer, training, inference, export
│   └── ncg/                 # CLI, config, logging
├── tests/                   # 73 tests: unit, integration, hardware-reference, context-conditioning
├── config.yaml               # Default configuration
└── COMPLETION_SUMMARY.md     # Detailed component-by-component status
```

## Hardware Status

The RTL (`hardware/inference_core/`, `hardware/hashing_cores/`, `hardware/rtl/ncg_top.sv`) lints cleanly under Verilator but has **not** been run through Verilator simulation or synthesized to a bitstream. `hardware/python_sim.py` is an independent Python re-implementation of the same algorithm, validated against NIST test vectors — it proves the *algorithm* is correct, not that the RTL matches it bit-for-bit (no co-simulation exists yet). The `inference_core` itself is a fixed byte-permutation matrix walker, not an actual Transformer running on hardware. See [hardware/SIMULATION_METHODOLOGY.md](hardware/SIMULATION_METHODOLOGY.md) for the full validation methodology and its limitations.

## Configuration

Copy `config.yaml` to `config.local.yaml` and override what you need:

```yaml
model:
  d_model: 256
  n_layers: 6
training:
  batch_size: 64
  learning_rate: 3.0e-4
  quantization_aware: true
```

## Development

```bash
# Run tests
pytest tests/ -v

# Lint & format
ruff check software/
ruff format software/

# Typecheck
mypy software/
```

## Roadmap

- [x] **Phase 1**: Software Transformer + context-conditioned DCPM generation, INT4 QAT, ONNX/TorchScript export
- [ ] **Phase 2**: RTL co-simulation against the Python reference model (Verilator); currently lint-only
- [ ] **Phase 3**: FPGA synthesis + bitstream deployment (requires Vivado + Alveo board files)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

Apache 2.0 — see [LICENSE](LICENSE).
