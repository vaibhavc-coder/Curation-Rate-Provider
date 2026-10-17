"""PTD Pipeline Main Execution CLI.

Executes pipeline phases cleanly with logging, resource tracking, and modular phase selection.
Supports:
    python run_pipeline.py --phase 1
    python run_pipeline.py --phase 2
    python run_pipeline.py --all
    python run_pipeline.py --sample 500
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure src is on sys.path
_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import time
from typing import Optional
import polars as pl

from ptd.config import load_config
from ptd.io_utils import get_ijson_backend_info, get_process_memory_mb, setup_logging
from ptd.index_parser import IndexParser
from ptd.ppo_classifier import PPOClassifier

from ptd.rate_stream import RateStreamProfiler
from ptd.rate_extract import RateExtractor
from ptd.file_grading import FileGrader

logger = logging.getLogger("ptd.main")


def run_phase_1(config) -> dict:
    logger.info("=== Starting Phase 1: TiC Index File Parsing & Scoping ===")
    start_t = time.time()
    start_mem = get_process_memory_mb()

    parser = IndexParser(config)
    result = parser.run()

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 1 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def run_phase_2(config, df_plans=None) -> dict:
    logger.info("=== Starting Phase 2: Explainable PPO Network Classification ===")
    start_t = time.time()
    start_mem = get_process_memory_mb()

    classifier = PPOClassifier(config)
    result = classifier.run(df_plans)

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 2 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def run_phase_3(config, sample_n: Optional[int] = None) -> dict:
    logger.info("=== Starting Phase 3: Rate File Streaming Profile ===")
    start_t = time.time()
    start_mem = get_process_memory_mb()

    profiler = RateStreamProfiler(config)
    result = profiler.run(sample_n=sample_n)

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 3 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def run_phase_4(config, sample_n: Optional[int] = None) -> dict:
    logger.info("=== Starting Phase 4: File Quality Grading (C3) & Rate Extraction (C4) ===")
    start_t = time.time()
    start_mem = get_process_memory_mb()

    # Step 1: Extract and aggregate rates
    extractor = RateExtractor(config)
    extract_res = extractor.run(sample_n=sample_n)

    # Step 2: Grade the RAW stream (before tie-breaks and filters)
    raw_audit_path = config.interim_dir / "raw_price_audit.parquet"
    df_raw = pl.read_parquet(raw_audit_path)

    grader = FileGrader(config)
    grade_res = grader.grade_raw_stream(df_raw)

    # Step 3: Run mutation test
    mutation_res = grader.run_mutation_test(df_raw)

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 4 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return {
        "extract": extract_res,
        "grade": grade_res,
        "mutation": mutation_res,
    }


def run_phase_5(config) -> dict:
    logger.info("=== Starting Phase 5: TIN -> NPI -> Practicing Address Linkage (C5) ===")
    from ptd.address_link import AddressLinkEngine
    start_t = time.time()
    start_mem = get_process_memory_mb()

    engine = AddressLinkEngine(config)
    result = engine.run()

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 5 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def run_phase_6(config) -> dict:
    logger.info("=== Starting Phase 6: Final Curated Rate File Generation (C6) ===")
    from ptd.final_output import FinalOutputGenerator
    start_t = time.time()
    start_mem = get_process_memory_mb()

    generator = FinalOutputGenerator(config)
    result = generator.run()

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 6 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def run_cost_effectiveness(config, df_final=None) -> dict:
    logger.info("=== Starting Cost-Effectiveness Provider Frontier (C7) ===")
    from ptd.cost_effectiveness import CostEffectivenessAnalyzer
    start_t = time.time()
    start_mem = get_process_memory_mb()

    if df_final is None:
        final_parquet = config.output_dir / "final_curated_rates.parquet"
        df_final = pl.read_parquet(final_parquet)

    analyzer = CostEffectivenessAnalyzer(config)
    result = analyzer.run_analysis(df_final)

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Cost-Effectiveness Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def run_phase_7(config) -> dict:
    logger.info("=== Starting Phase 7: Production Governance Summary Export (Phase 7) ===")
    from ptd.summary import PipelineSummarizer
    start_t = time.time()
    start_mem = get_process_memory_mb()

    summarizer = PipelineSummarizer(config)
    result = summarizer.run()

    dur = time.time() - start_t
    peak_mem = get_process_memory_mb() - start_mem
    logger.info(f"=== Phase 7 Complete in {dur:.2f}s | Delta Mem: {peak_mem:.1f} MB ===")
    return result


def stage_input_files_if_needed(config):
    """Ensure data/index and data/raw contain required input files from config."""
    import shutil
    from pathlib import Path
    config.index_dir.mkdir(parents=True, exist_ok=True)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    orig = getattr(config, "raw_config", {}) or {}
    sources = orig.get("original_input_sources", {})

    downloads_dir = Path.home() / "Downloads"
    if downloads_dir.exists():
        for p in downloads_dir.glob("*_index*.json"):
            if "(1)" not in p.name:
                target = config.index_dir / p.name
                if not target.exists():
                    try:
                        target.symlink_to(p)
                    except OSError:
                        shutil.copy(p, target)

    if not list(config.raw_dir.glob("*.json")):
        p = sources.get("healthnet_ca_rate_file")
        if p and Path(p).exists():
            target = config.raw_dir / Path(p).name
            if not target.exists():
                try:
                    target.symlink_to(p)
                except OSError:
                    shutil.copy(p, target)


def main():
    setup_logging()
    cli_parser = argparse.ArgumentParser(description="Centene Commercial-Group CA PPO Data Pipeline")
    cli_parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4, 5, 6, 7], help="Run a specific phase")
    cli_parser.add_argument("--all", action="store_true", help="Run all phases end-to-end")
    cli_parser.add_argument("--cost-effectiveness", action="store_true", help="Run C7 cost-effectiveness analysis")
    cli_parser.add_argument("--sample", type=int, default=None, help="Process first N records in rate extraction")
    cli_parser.add_argument("--config", type=str, default=None, help="Path to custom config.yaml")

    args = cli_parser.parse_args()
    config = load_config(args.config)
    stage_input_files_if_needed(config)

    backend_info = get_ijson_backend_info()
    logger.info(f"Active ijson backend: {backend_info['active_backend']}")
    logger.info(f"Project root: {config.project_root}")
    logger.info(f"Data directory: {config.data_dir}")

    # If --sample is passed without --phase, execute all phases in sample mode
    run_all = args.all or (not args.phase and not args.cost_effectiveness and args.sample is not None)

    if args.phase == 1 or run_all:
        p1_res = run_phase_1(config)
        if args.phase == 1:
            return

    if args.phase == 2 or run_all:
        df_plans = p1_res["df_plans"] if (run_all and "p1_res" in locals()) else None
        p2_res = run_phase_2(config, df_plans)
        if args.phase == 2:
            return

    if args.phase == 3 or run_all:
        p3_res = run_phase_3(config, sample_n=args.sample)
        if args.phase == 3:
            return

    if args.phase == 4 or run_all:
        p4_res = run_phase_4(config, sample_n=args.sample)
        if args.phase == 4:
            return

    if args.phase == 5 or run_all:
        p5_res = run_phase_5(config)
        if args.phase == 5:
            return

    if args.phase == 6 or run_all:
        p6_res = run_phase_6(config)
        if args.phase == 6:
            return

    if args.cost_effectiveness or run_all:
        p_ce = run_cost_effectiveness(config)
        if args.cost_effectiveness:
            return

    if args.phase == 7 or run_all:
        p7_res = run_phase_7(config)
        if args.phase == 7:
            return

    if not args.phase and not run_all and not args.cost_effectiveness:
        logger.info("No phase specified. Defaulting to Phase 1, Phase 2, and Phase 3.")
        p1_res = run_phase_1(config)
        p2_res = run_phase_2(config, p1_res["df_plans"])
        p3_res = run_phase_3(config, sample_n=args.sample)


if __name__ == "__main__":
    main()
