"""Standalone GRC benchmark: compile all routes and compute pairwise metric differences."""

import csv
import sys
import os
from itertools import combinations

# Ensure gre package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gre.compiler.compiler import GeometryCompiler
from gre.compiler.ir import CompilationResult


ROUTES = ["ifs", "pascal_mod2", "rule90", "hanoi"]
METRIC_NAMES = [
    "spectral_gap",
    "eigenvalue_spacing_ratio",
    "resonance_frequency",
    "resonance_coupling",
    "average_degree",
    "golden_ratio_ratio",
]
STRING_METRICS = ["attractor_label"]
SEPARABLE_THRESHOLD = 0.05
SEPARABLE_COUNT = 3


def compile_all_routes(level: int = 4) -> dict:
    """Compile all routes at the given level and return a dict of route -> CompilationResult."""
    compiler = GeometryCompiler()
    results = {}
    for route in ROUTES:
        try:
            result = compiler.compile(
                "sierpinski",
                level=level,
                route=route,
                strategies=["staggered"],
                emit_circuits=False,
            )
            results[route] = result
        except Exception as e:
            print(f"Warning: failed to compile route={route} level={level}: {e}", file=sys.stderr)
    return results


def get_numeric_metrics(result: CompilationResult) -> dict:
    """Extract numeric metrics from a CompilationResult."""
    rd = result.resonance_descriptor
    return {
        "spectral_gap": rd.spectral_gap,
        "eigenvalue_spacing_ratio": rd.eigenvalue_spacing_ratio,
        "resonance_frequency": rd.resonance_frequency,
        "resonance_coupling": rd.resonance_coupling,
        "average_degree": rd.average_degree,
        "golden_ratio_ratio": rd.golden_ratio_ratio,
    }


def get_string_metrics(result: CompilationResult) -> dict:
    """Extract string metrics from a CompilationResult."""
    return {
        "attractor_label": result.attractor_signature.attractor_label,
    }


def pairwise_differences(results: dict) -> list:
    """Compute pairwise differences for all routes."""
    rows = []
    route_names = list(results.keys())
    for a, b in combinations(route_names, 2):
        res_a = results[a]
        res_b = results[b]
        metrics_a = get_numeric_metrics(res_a)
        metrics_b = get_numeric_metrics(res_b)
        str_a = get_string_metrics(res_a)
        str_b = get_string_metrics(res_b)

        all_diff = {}
        for metric in METRIC_NAMES:
            diff = abs(metrics_a[metric] - metrics_b[metric])
            all_diff[metric] = diff
            separable = 1 if diff >= SEPARABLE_THRESHOLD else 0
            rows.append({
                "route_a": a,
                "route_b": b,
                "metric": metric,
                "value_a": metrics_a[metric],
                "value_b": metrics_b[metric],
                "difference": diff,
                "separable": separable,
            })

        # String metric — 0 difference if match, 1 if mismatch
        for metric in STRING_METRICS:
            diff = 0.0 if str_a[metric] == str_b[metric] else 1.0
            all_diff[metric] = diff
            separable = 1 if diff > 0 else 0
            rows.append({
                "route_a": a,
                "route_b": b,
                "metric": metric,
                "value_a": str_a[metric],
                "value_b": str_b[metric],
                "difference": diff,
                "separable": separable,
            })

        # Summary row
        sep_count = sum(1 for d in all_diff.values() if d >= SEPARABLE_THRESHOLD)
        summary = "separable" if sep_count >= SEPARABLE_COUNT else "similar"
        rows.append({
            "route_a": a,
            "route_b": b,
            "metric": "summary",
            "value_a": sep_count,
            "route_b": b,
            "metric": "summary",
            "value_a": sep_count,
            "value_b": SEPARABLE_COUNT,
            "difference": sep_count,
            "separable": 1 if summary == "separable" else 0,
            "summary": summary,
        })

    return rows


def build_markdown_table(results: dict, rows: list) -> str:
    """Build a readable markdown comparison table."""
    lines = []
    lines.append("# GRC Benchmark: Route Comparison\n")
    lines.append(f"**Routes:** {', '.join(ROUTES)}")
    lines.append(f"**Separable threshold:** {SEPARABLE_THRESHOLD} | **Min separable metrics:** {SEPARABLE_COUNT}\n")

    # Per-route metric summary table
    lines.append("## Route Metric Summary\n")
    lines.append("| Route | spectral_gap | eigenvalue_spacing_ratio | resonance_frequency | resonance_coupling | average_degree | golden_ratio_ratio | attractor_label |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for route, result in results.items():
        m = get_numeric_metrics(result)
        s = get_string_metrics(result)
        lines.append(
            f"| {route} | {m['spectral_gap']:.6f} | {m['eigenvalue_spacing_ratio']:.6f} | "
            f"{m['resonance_frequency']:.6f} | {m['resonance_coupling']:.6f} | "
            f"{m['average_degree']:.6f} | {m['golden_ratio_ratio']:.6f} | {s['attractor_label']} |"
        )

    lines.append("\n## Pairwise Differences\n")
    lines.append("| Route A | Route B | Metric | Value A | Value B | Difference | Separable |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in rows:
        if row["metric"] == "summary":
            lines.append(
                f"| **{row['route_a']}** | **{row['route_b']}** | "
                f"__summary__ | {row['value_a']}/{SEPARABLE_COUNT} metrics differ | "
                f"_{row.get('summary', 'similar')}_ | {row['difference']} | "
                f"{'yes' if row['separable'] else 'no'} |"
            )
        elif row["metric"] in STRING_METRICS:
            lines.append(
                f"| {row['route_a']} | {row['route_b']} | {row['metric']} | "
                f"{row['value_a']} | {row['value_b']} | {row['difference']:.1f} | "
                f"{'yes' if row['separable'] else 'no'} |"
            )
        else:
            lines.append(
                f"| {row['route_a']} | {row['route_b']} | {row['metric']} | "
                f"{row['value_a']:.6f} | {row['value_b']:.6f} | {row['difference']:.6f} | "
                f"{'yes' if row['separable'] else 'no'} |"
            )

    return "\n".join(lines)


def write_csv(rows: list, path: str) -> None:
    """Write benchmark results to CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["route_a", "route_b", "metric", "value_a", "value_b", "difference", "separable"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "route_a": row["route_a"],
                "route_b": row["route_b"],
                "metric": row["metric"],
                "value_a": row["value_a"],
                "value_b": row["value_b"],
                "difference": row["difference"],
                "separable": row["separable"],
            })


def main() -> None:
    level = 4
    level5 = False
    if len(sys.argv) > 1 and sys.argv[1] == "--level5":
        level = 5
        level5 = True

    print(f"Compiling all routes at level={level}...", file=sys.stderr)
    results = compile_all_routes(level)
    if not results:
        print("Error: no routes compiled successfully.", file=sys.stderr)
        sys.exit(1)

    print(f"Compiled {len(results)} routes: {list(results.keys())}", file=sys.stderr)

    if level5:
        print("Compiling at level=5 for optional comparison...", file=sys.stderr)
        results_l5 = compile_all_routes(5)
        # Inject cross-level comparison rows
        for route in ROUTES:
            if route in results and route in results_l5:
                m4 = get_numeric_metrics(results[route])
                m5l = get_numeric_metrics(results_l5[route])
                print(
                    f"  {route} level=4 spectral_gap={m4['spectral_gap']:.6f} -> "
                    f"level=5 spectral_gap={m5l['spectral_gap']:.6f}",
                    file=sys.stderr,
                )

    rows = pairwise_differences(results)

    # Write CSV
    csv_path = os.path.join(os.path.dirname(__file__), "benchmark_results.csv")
    write_csv(rows, csv_path)
    print(f"CSV written to: {csv_path}", file=sys.stderr)

    # Print markdown to stdout
    md = build_markdown_table(results, rows)
    print(md)


if __name__ == "__main__":
    main()
