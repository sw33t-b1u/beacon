"""Unified ``beacon`` CLI entry point (Initiative H Phase 6).

Implements the committed CLI surface enumerated in
``docs/api-stability.md`` §3.7. Each subcommand delegates to the
underlying ``cmd/*.py`` ``main(argv)`` function so the business
logic stays in one place; this module is intentionally a thin
dispatcher.

The eight subcommands are:

* ``beacon pir-generate`` — Generate PIR + collection plan + sources
  candidate; auto-launches the web UI on success (suppress with
  ``--no-web``).
* ``beacon assets-generate`` — Generate the SAGE asset bundle.
* ``beacon identity-generate`` — Generate the identity asset bundle.
* ``beacon accounts-generate`` — Generate the user account bundle.
* ``beacon submit-review`` — Submit a PIR output for GHE review.
* ``beacon taxonomy-refresh`` — Regenerate the threat taxonomy from
  upstream MITRE ATT&CK + MISP Galaxy.
* ``beacon misp-cache-refresh`` — Refresh the local MISP cache.
* ``beacon web`` — Launch the review web UI without running PIR
  generation.

The legacy ``python -m cmd.<name>`` invocation remains for 1.x
backward compatibility; see ``docs/api-stability.md`` §3.7 for the
2.0.0 removal schedule.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

# ---------------------------------------------------------------------------
# Module loader — bypasses Python's stdlib ``cmd`` package conflict.
# ---------------------------------------------------------------------------


def _load_cmd_module(name: str) -> Any:
    """Import a ``cmd/<name>.py`` script as a uniquely-named module.

    Python's stdlib ``cmd`` (used by ``pdb``) collides with the BEACON
    ``cmd/`` directory when both end up on ``sys.path``. We resolve the
    script by absolute path and load it under a private cache key so the
    stdlib import order stays intact.
    """
    cache_key = f"_beacon_cli_cmd_{name}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    import importlib.util  # noqa: PLC0415

    repo_root = Path(__file__).resolve().parents[3]
    src_dir = repo_root / "src"
    # The cmd scripts ``sys.path.insert`` the src dir at runtime; mirror
    # that here so an import order from the CLI matches the legacy entry.
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    path = repo_root / "cmd" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(cache_key, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not load cmd module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module


def _delegate(cmd_name: str, argv: list[str]) -> int:
    """Invoke the underlying ``cmd.<cmd_name>.main(argv)`` and return its exit code.

    The ``_from_beacon_cli=True`` keyword suppresses the per-script
    deprecation banner; the user already chose the modern entry point.
    """
    module = _load_cmd_module(cmd_name)
    result = module.main(argv, _from_beacon_cli=True)
    return int(result) if result is not None else 0


# ---------------------------------------------------------------------------
# Click root group + subcommands.
# ---------------------------------------------------------------------------


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "BEACON unified CLI. Generates PIR + asset artifacts and serves the "
        "review web UI. See `docs/api-stability.md` §3.7 for the committed "
        "subcommand surface."
    ),
)
@click.version_option(package_name="beacon", prog_name="beacon")
def cli() -> None:
    """Top-level group; subcommands defined below."""


@cli.command(
    "pir-generate",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--context",
    "-c",
    required=True,
    type=click.Path(),
    help="Path to strategy document (.md) or business_context.json.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    default="output",
    show_default=True,
    help=(
        "Directory where pir_output.json, collection_plan.md and "
        "sources_candidate.yaml are written. Used both as the artifact "
        "destination and as the web UI's scan root."
    ),
)
@click.option(
    "--taxonomy",
    type=click.Path(),
    default=None,
    help="Override path to threat_taxonomy.json.",
)
@click.option(
    "--asset-tags",
    type=click.Path(),
    default=None,
    help="Override path to asset_tags.json.",
)
@click.option(
    "--save-context",
    type=click.Path(),
    default=None,
    help="If set, also write the parsed BusinessContext as JSON for review.",
)
@click.option(
    "--collection-plan",
    type=click.Path(),
    default=None,
    help="Override collection_plan.md path (default: <output-dir>/collection_plan.md).",
)
@click.option(
    "--sources-candidate",
    type=click.Path(),
    default=None,
    help="Override sources_candidate.yaml path (default: <output-dir>/sources_candidate.yaml).",
)
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="Override pir_output.json path (default: <output-dir>/pir_output.json).",
)
@click.option(
    "--use-sage",
    is_flag=True,
    default=False,
    help="Enable risk_scorer SAGE observation-count boost (requires SAGE_API_URL).",
)
@click.option(
    "--no-sage",
    is_flag=True,
    default=False,
    help="Skip the actor_triage IR-boost SAGE call (sets data_quality.ir_boost_skipped).",
)
@click.option(
    "--no-web",
    is_flag=True,
    default=False,
    help="Skip auto-launching the review web UI after PIR generation succeeds.",
)
def pir_generate(
    context: str,
    output_dir: str,
    taxonomy: str | None,
    asset_tags: str | None,
    save_context: str | None,
    collection_plan: str | None,
    sources_candidate: str | None,
    output: str | None,
    use_sage: bool,
    no_sage: bool,
    no_web: bool,
) -> None:
    """Generate SAGE-compatible PIR + collection plan + sources candidate.

    On success, auto-launches the review web UI in the background unless
    ``--no-web`` is set. The URL is printed to stdout.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pir_output_path = output or str(out_dir / "pir_output.json")
    collection_plan_path = collection_plan or str(out_dir / "collection_plan.md")
    sources_candidate_path = sources_candidate or str(out_dir / "sources_candidate.yaml")

    argv: list[str] = [
        "--context",
        context,
        "--output",
        pir_output_path,
        "--collection-plan",
        collection_plan_path,
        "--sources-candidate",
        sources_candidate_path,
    ]
    if taxonomy is not None:
        argv += ["--taxonomy", taxonomy]
    if asset_tags is not None:
        argv += ["--asset-tags", asset_tags]
    if save_context is not None:
        argv += ["--save-context", save_context]
    if use_sage:
        argv.append("--use-sage")
    if no_sage:
        argv.append("--no-sage")

    rc = _delegate("generate_pir", argv)
    if rc != 0:
        raise click.exceptions.Exit(rc)

    if not no_web:
        from beacon.web.launcher import launch_web  # noqa: PLC0415

        url = launch_web(out_dir)
        click.echo(f"BEACON web UI ready: {url}")


@cli.command(
    "assets-generate",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def assets_generate(ctx: click.Context) -> None:
    """Generate the SAGE asset bundle from a business context document."""
    rc = _delegate("generate_assets", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


@cli.command(
    "identity-generate",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def identity_generate(ctx: click.Context) -> None:
    """Generate identity_assets.json (Identity → Asset HasAccess edges)."""
    rc = _delegate("generate_identity_assets", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


@cli.command(
    "accounts-generate",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def accounts_generate(ctx: click.Context) -> None:
    """Generate user_accounts.json (User-Account SCO)."""
    rc = _delegate("generate_user_accounts", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


@cli.command(
    "submit-review",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def submit_review(ctx: click.Context) -> None:
    """Submit a PIR output for GHE Issue-driven review."""
    rc = _delegate("submit_for_review", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


@cli.command(
    "taxonomy-refresh",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def taxonomy_refresh(ctx: click.Context) -> None:
    """Regenerate threat_taxonomy.json from MITRE ATT&CK + MISP Galaxy."""
    rc = _delegate("update_taxonomy", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


@cli.command(
    "misp-cache-refresh",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def misp_cache_refresh(ctx: click.Context) -> None:
    """Refresh the MISP threat-actor cache from upstream."""
    rc = _delegate("refresh_misp_cache", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


@cli.command(
    "web",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.pass_context
def web(ctx: click.Context) -> None:
    """Launch the BEACON review web UI without triggering PIR generation."""
    rc = _delegate("web_app", list(ctx.args))
    if rc and rc != 0:
        raise click.exceptions.Exit(rc)


if __name__ == "__main__":  # pragma: no cover - manual entry path
    cli()
