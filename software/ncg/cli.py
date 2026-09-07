"""CLI entry point for NCG Framework."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows (rich spinners/unicode need it)
if sys.platform == "win32":
    os.system("")  # Enable ANSI escape sequences on modern Windows terminals
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass

import click
import torch
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import load_config
from .logging import get_logger, setup_logging

console = Console(force_terminal=True if sys.platform == "win32" else None)
logger = get_logger(__name__)


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config YAML file")
@click.option("--log-level", "-l", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
@click.option(
    "--log-format", type=click.Choice(["json", "text", "rich"]), default="rich", help="Log format"
)
@click.pass_context
def cli(ctx: click.Context, config: str | None, log_level: str, log_format: str) -> None:
    """Neuromorphic Cryptanalytic Generator (NCG) - Next-gen cryptanalytic system."""
    ctx.ensure_object(dict)

    cfg = load_config(config)
    cfg.logging.level = log_level
    cfg.logging.format = log_format

    setup_logging(cfg.logging)
    ctx.obj["config"] = cfg

    logger.info("NCG Framework initialized", extra={"extra_fields": {"version": "0.1.0"}})


@cli.command()
@click.pass_context
def version(ctx: click.Context) -> None:
    """Show version information."""
    from . import __author__, __license__, __version__

    table = Table(title="NCG Framework")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version", __version__)
    table.add_row("Author", __author__)
    table.add_row("License", __license__)

    console.print(table)


@cli.command()
@click.option("--num", "-n", type=int, default=10000, help="Number of passwords to generate (per org, if --orgs given)")
@click.option("--org", default="TechCorp", help="Organization for contextual patterns (ignored if --orgs given)")
@click.option(
    "--orgs",
    default=None,
    help=(
        "Comma-separated organizations to generate a CONTEXTUAL dataset "
        "(JSONL, one {password, metadata} per line). Multiple orgs are what "
        "gives 'ncg model train' a real signal to learn context-conditioning "
        "from -- a single org (the default) has no context to distinguish."
    ),
)
@click.option("--output", "-o", type=click.Path(), default="data/passwords.txt", help="Output file")
@click.option("--seed", type=int, default=42, help="Random seed")
def dataset(num: int, org: str, orgs: str | None, output: str, seed: int) -> None:
    """Generate a synthetic training dataset with realistic password patterns."""
    from model.dataset import (
        generate_dataset,
        generate_multi_org_dataset,
        save_dataset,
        save_dataset_jsonl,
    )

    if orgs:
        org_list = [o.strip() for o in orgs.split(",") if o.strip()]
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task(f"Generating {num} passwords x {len(org_list)} orgs...", total=None)
            passwords, metadata = generate_multi_org_dataset(num, org_list, seed)

        out_path = Path(output)
        if out_path.suffix != ".jsonl":
            out_path = out_path.with_suffix(".jsonl")
        save_dataset_jsonl(passwords, metadata, out_path)
        console.print(f"[green]Generated {len(passwords)} contextual passwords ({len(org_list)} orgs) -> {out_path}[/green]")
        console.print("\n[bold]Sample:[/bold]")
        for pwd, meta in list(zip(passwords, metadata, strict=True))[:10]:
            console.print(f"  {pwd}  [dim]({meta['organization']})[/dim]")
        return

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(f"Generating {num} passwords...", total=None)
        passwords = generate_dataset(num, org, seed)

    save_dataset(passwords, output)
    console.print(f"[green]Generated {len(passwords)} passwords -> {output}[/green]")
    console.print("\n[bold]Sample:[/bold]")
    for pwd in passwords[:10]:
        console.print(f"  {pwd}")


@cli.group()
def model() -> None:
    """Model management commands."""
    pass


@model.command("train")
@click.option(
    "--data", "-d", type=click.Path(exists=True), required=True, help="Training data path (text file, one password per line)"
)
@click.option("--output", "-o", type=click.Path(), required=True, help="Output model directory")
@click.option("--epochs", "-e", type=int, default=None, help="Number of epochs (overrides config)")
@click.option("--batch-size", "-b", type=int, default=None, help="Batch size (overrides config)")
@click.option("--device", type=click.Choice(["auto", "cpu", "cuda"]), default="auto", help="Device")
@click.option("--d-model", type=int, default=None, help="Model dimension (overrides config)")
@click.option("--n-layers", type=int, default=None, help="Number of layers (overrides config)")
@click.pass_context
def train_model(
    ctx: click.Context,
    data: str,
    output: str,
    epochs: int | None,
    batch_size: int | None,
    device: str,
    d_model: int | None,
    n_layers: int | None,
) -> None:
    """Train the transformer model on a password dataset.

    Accepts either a plain text file (one password per line, no context) or a
    JSONL file produced by `ncg dataset --orgs ...` (one {password, metadata}
    per line) for training with real breach-context conditioning.
    """
    from model import PasswordTokenizer, create_data_loaders, create_model, load_password_list
    from model.dataset import is_jsonl_dataset, load_dataset_jsonl
    from model.tokenizer import MetadataTokenizer
    from model.train import train as run_training

    cfg = ctx.obj["config"]

    # Apply CLI overrides
    if epochs is not None:
        cfg.training.max_epochs = epochs
    if batch_size is not None:
        cfg.training.batch_size = batch_size
    if d_model is not None:
        cfg.model.d_model = d_model
    if n_layers is not None:
        cfg.model.n_layers = n_layers

    # Resolve device
    if device == "auto":
        dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        dev = torch.device(device)

    console.print(f"[bold]Loading dataset:[/bold] {data}")
    contextual = is_jsonl_dataset(data)
    metadata_tokenizer: MetadataTokenizer | None = None
    metadata: list[dict] | None = None
    if contextual:
        passwords, metadata = load_dataset_jsonl(data)
        metadata_tokenizer = MetadataTokenizer(max_metadata_tokens=cfg.model.max_metadata_tokens)
        metadata_tokenizer.build_vocab(metadata)
        console.print(
            f"  {len(passwords)} passwords loaded [bold]with breach-context metadata[/bold] "
            f"(vocab: {metadata_tokenizer.get_vocab_size()} words)"
        )
    else:
        passwords = load_password_list(data)
        console.print(f"  {len(passwords)} passwords loaded (no context metadata)")
    if not passwords:
        console.print("[red]No passwords found in dataset[/red]")
        raise SystemExit(1)

    # Build tokenizer and model from config
    tokenizer = PasswordTokenizer(max_seq_len=cfg.model.max_seq_len)
    net = create_model(cfg.model)
    param_count = sum(p.numel() for p in net.parameters())
    console.print(f"[bold]Model:[/bold] {param_count:,} parameters, d_model={cfg.model.d_model}, layers={cfg.model.n_layers}")
    console.print(f"[bold]Device:[/bold] {dev}")
    console.print(
        f"[bold]Training:[/bold] epochs={cfg.training.max_epochs}, batch_size={cfg.training.batch_size}, "
        f"lr={cfg.training.learning_rate}, quantization_aware={cfg.training.quantization_aware}"
    )

    # Create data loaders (90/10 train/val split); metadata (if any) is split
    # and shuffled in lockstep with its password so pairs never desync.
    train_loader, val_loader = create_data_loaders(
        passwords,
        tokenizer=tokenizer,
        batch_size=cfg.training.batch_size,
        max_seq_len=cfg.model.max_seq_len,
        num_workers=0,  # Windows-safe
        val_split=0.1,
        train_metadata=metadata,
        metadata_tokenizer=metadata_tokenizer,
    )
    console.print(f"  Train batches: {len(train_loader)}, Val batches: {len(val_loader) if val_loader else 0}")

    # Adjust warmup if dataset is small
    total_steps = len(train_loader) * cfg.training.max_epochs
    if cfg.training.warmup_steps > total_steps // 10:
        cfg.training.warmup_steps = max(10, total_steps // 10)
        console.print(f"  Adjusted warmup steps: {cfg.training.warmup_steps}")

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the config used alongside the model for reproducibility
    cfg.to_yaml(output_dir / "training_config.yaml")

    run_training(
        train_loader=train_loader,
        val_loader=val_loader,
        model=net,
        config=cfg.training,
        tokenizer=tokenizer,
        metadata_tokenizer=metadata_tokenizer,
        device=dev,
        output_dir=output_dir,
        log_interval=max(1, len(train_loader) // 10),
        eval_interval=max(1, len(train_loader)),
        save_interval=max(1, len(train_loader) * cfg.training.max_epochs),
    )

    console.print(f"\n[green]Training complete. Model saved to {output_dir}[/green]")
    console.print(f"  Best model: {output_dir / 'best_model.pt'}")
    console.print(f"  Final model: {output_dir / 'final_model.pt'}")


@model.command("generate")
@click.option("--model", "-m", type=click.Path(exists=True), required=True, help="Model checkpoint path (.pt)")
@click.option("--context", "-c", required=True, help="Target context (JSON, e.g. '{\"organization\": \"TechCorp\"}')")
@click.option(
    "--num-candidates", "-n", type=int, default=100, help="Number of candidates to generate"
)
@click.option("--output", "-o", type=click.Path(), help="Output file for candidates (one per line)")
@click.option("--max-length", type=int, default=None, help="Max candidate length (overrides config)")
@click.option("--temperature", "-t", type=float, default=None, help="Sampling temperature (overrides config)")
@click.option("--top-k", type=int, default=None, help="Top-k sampling (overrides config)")
@click.option("--top-p", type=float, default=None, help="Top-p sampling (overrides config)")
@click.pass_context
def generate_candidates(
    ctx: click.Context,
    model: str,
    context: str,
    num_candidates: int,
    output: str | None,
    max_length: int | None,
    temperature: float | None,
    top_k: int | None,
    top_p: float | None,
) -> None:
    """Generate password candidates from a trained model + breach context."""
    from model import load_generator

    cfg = ctx.obj["config"]

    # Apply overrides
    if max_length is not None:
        cfg.inference.max_new_tokens = max_length
    if temperature is not None:
        cfg.inference.temperature = temperature
    if top_k is not None:
        cfg.inference.top_k = top_k
    if top_p is not None:
        cfg.inference.top_p = top_p

    # Parse context JSON
    try:
        context_dict = json.loads(context)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid context JSON: {e}[/red]")
        console.print("Example: --context '{\"organization\": \"TechCorp\", \"year\": 2026}'")
        raise SystemExit(1) from e

    console.print(f"[bold]Loading model:[/bold] {model}")
    generator = load_generator(model, device="auto", inference_config=cfg.inference)
    console.print(f"[bold]Context:[/bold] {context_dict}")
    console.print(
        f"[bold]Sampling:[/bold] temp={cfg.inference.temperature}, top_k={cfg.inference.top_k}, top_p={cfg.inference.top_p}"
    )

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(f"Generating {num_candidates} candidates...", total=None)
        candidates = generator.generate_candidates(
            context_dict,
            num_candidates=num_candidates,
            max_length=cfg.inference.max_new_tokens,
            temperature=cfg.inference.temperature,
            top_k=cfg.inference.top_k,
            top_p=cfg.inference.top_p,
        )

    # Deduplicate while preserving order (real passwords repeat, but unique is more useful)
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    console.print(f"\n[green]Generated {len(candidates)} candidates ({len(unique_candidates)} unique)[/green]")
    console.print("\n[bold]Top candidates:[/bold]")
    for i, cand in enumerate(unique_candidates[:20]):
        console.print(f"  {i + 1:3d}. {cand}")

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(unique_candidates))
        console.print(f"\n[green]Saved {len(unique_candidates)} unique candidates -> {output}[/green]")


@model.command("evaluate")
@click.option("--model", "-m", type=click.Path(exists=True), required=True, help="Model checkpoint path")
@click.option("--test-data", "-d", type=click.Path(exists=True), required=True, help="Holdout passwords (one per line)")
@click.option("--num-candidates", "-n", type=int, default=1000, help="Candidates per evaluation")
@click.pass_context
def evaluate_model(ctx: click.Context, model: str, test_data: str, num_candidates: int) -> None:
    """Evaluate model: top-k accuracy against a holdout set."""
    from model import load_generator, load_password_list

    generator = load_generator(model, device="auto")
    test_passwords = load_password_list(test_data)

    console.print(f"Evaluating against {len(test_passwords)} holdout passwords...")
    candidates = generator.generate_candidates(
        {"organization": "TechCorp"}, num_candidates=num_candidates, max_length=20
    )
    candidate_set = set(candidates)

    hits = sum(1 for pwd in test_passwords if pwd in candidate_set)

    table = Table(title="Evaluation Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Holdout size", str(len(test_passwords)))
    table.add_row("Candidates generated", str(num_candidates))
    table.add_row("Hits (exact match)", str(hits))
    table.add_row("Top-N accuracy", f"{hits / len(test_passwords) * 100:.1f}%")
    console.print(table)


@model.command("export")
@click.option("--model", "-m", type=click.Path(exists=True), required=True, help="Model checkpoint path")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["onnx", "torchscript"]),
    default="torchscript",
    help="Export format",
)
@click.option("--output", "-o", type=click.Path(), required=True, help="Output path")
@click.pass_context
def export_model(ctx: click.Context, model: str, format: str, output: str) -> None:
    """Export model for deployment."""
    from model import load_generator
    from model.export import export_to_torchscript

    console.print(f"[bold]Loading model:[/bold] {model}")
    generator = load_generator(model, device="cpu")
    gen_model = generator.model

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if format == "torchscript":
        export_to_torchscript(gen_model, out_path)
        console.print(f"[green]TorchScript export complete: {out_path}[/green]")
    elif format == "onnx":
        try:
            from model.export import export_to_onnx

            export_to_onnx(gen_model, generator.tokenizer, out_path)
            console.print(f"[green]ONNX export complete: {out_path}[/green]")
        except Exception as e:
            console.print(f"[red]ONNX export failed: {e}[/red]")
            console.print("[yellow]Hint: ONNX export requires fixed shapes; use torchscript for now.[/yellow]")
            raise SystemExit(1) from e


@cli.group()
def hardware() -> None:
    """Hardware/FPGA commands."""
    pass


@hardware.command("simulate")
@click.option("--design", "-d", type=click.Path(exists=True), required=True, help="RTL design path")
@click.option("--testbench", "-t", type=click.Path(exists=True), help="Testbench path")
@click.option("--cycles", "-c", type=int, default=10000, help="Simulation cycles")
@click.pass_context
def simulate(ctx: click.Context, design: str, testbench: str | None, cycles: int) -> None:
    """Run Verilator simulation."""
    import shutil

    # Check the toolchain first so the friendly install message is what
    # users see when verilator is missing, rather than an import traceback.
    if shutil.which("verilator") is None:
        console.print("[red]Verilator not found. Install it first:[/red]")
        console.print("  Windows: choco install verilator")
        console.print("  Linux: apt install verilator")
        raise SystemExit(1)

    # `hardware` lives at the repo root, not under `software/`, so it is not
    # on sys.path via the editable install (see pyproject.toml packages.find,
    # where=["software"]). Add the repo root so the import below succeeds
    # when `ncg` is run from within a checkout (the supported dev workflow).
    _repo_root = Path(__file__).resolve().parent.parent.parent
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))

    try:
        from hardware import SimulationConfig, VerilatorSimulator
    except ModuleNotFoundError as e:
        console.print(f"[red]Could not import hardware package: {e}[/red]")
        console.print(f"  Expected to find it at: {_repo_root / 'hardware'}")
        console.print("  Run `ncg` from within the ncg-framework checkout.")
        raise SystemExit(1) from e

    design_path = Path(design)
    design_dir = design_path.parent if design_path.is_file() else design_path
    top_module = design_path.stem if design_path.is_file() else "ncg_top"

    config = SimulationConfig(
        top_module=top_module,
        design_dir=design_dir,
        cycles=cycles,
    )
    sim = VerilatorSimulator(config)
    if not sim.compile():
        console.print("[red]Verilator compilation failed[/red]")
        raise SystemExit(1)

    result = sim.run_testbench(top_module)
    if result.success:
        console.print(f"[green]Simulation passed[/green] ({result.cycles} cycles)")
    else:
        console.print(f"[red]Simulation failed:[/red] {result.error}")
        raise SystemExit(1)


@hardware.command("synthesize")
@click.option("--design", "-d", type=click.Path(exists=True), required=True, help="RTL design path")
@click.option(
    "--device",
    type=click.Choice(["alveo_u50", "alveo_u280", "zcu102"]),
    default="alveo_u50",
    help="Target device",
)
@click.option("--output", "-o", type=click.Path(), required=True, help="Output bitstream path")
@click.pass_context
def synthesize(ctx: click.Context, design: str, device: str, output: str) -> None:
    """Synthesize RTL to bitstream (requires Vivado)."""
    import shutil

    if shutil.which("vivado") is None:
        console.print("[red]Vivado not found in PATH.[/red]")
        console.print("Synthesis requires Vivado 2022.2+ and a licensed installation.")
        console.print("\nTo run synthesis manually:")
        console.print(f"  vivado -mode batch -source hardware/synth/tcl/create_project.tcl -tclargs {device.split('_')[1]}")
        console.print("  # then: launch_runs impl_1 -to_step write_bitstream")
        raise SystemExit(1)

    console.print(f"Synthesis for {device} would run here (Vivado detected).")
    console.print(f"  Design: {design}")
    console.print(f"  Output: {output}")


@cli.command()
@click.option("--generate-dataset", is_flag=True, help="Also generate a sample dataset")
@click.pass_context
def doctor(ctx: click.Context, generate_dataset: bool) -> None:
    """Check system dependencies and configuration."""
    console.print("[bold]NCG Framework System Check[/bold]\n")

    table = Table(title="Environment")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    import shutil
    import sys

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    table.add_row("Python", py_version)
    table.add_row("PyTorch", torch.__version__)
    table.add_row("CUDA", "Available" if torch.cuda.is_available() else "Not available (CPU mode)")

    for tool, desc in [("verilator", "RTL simulation"), ("vivado", "FPGA synthesis"), ("xbutil", "XRT deployment")]:
        found = shutil.which(tool) is not None
        table.add_row(tool, f"{desc} - {'Found' if found else 'Not installed'}")

    console.print(table)

    # Check for trained model
    model_paths = list(Path(".").glob("**/best_model.pt")) + list(Path(".").glob("**/final_model.pt"))
    if model_paths:
        console.print(f"\n[green]Trained model found:[/green] {model_paths[0]}")
    else:
        console.print("\n[yellow]No trained model found. Next steps:[/yellow]")
        console.print("  1. ncg dataset -n 10000 -o data/passwords.txt")
        console.print("  2. ncg model train -d data/passwords.txt -o models/ncg -e 5")
        console.print("  3. ncg model generate -m models/ncg/best_model.pt -c '{\"organization\": \"TechCorp\"}'")


if __name__ == "__main__":
    cli()
