"""Main GeometryCompiler entry point for the GRC pipeline."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union

from .attractor import AttractorSignatureClassifier
from .ir import (
    CompilationResult,
    GeometryCompilerConfig,
    MultiscalePartition,
    ResonanceDescriptor,
    SymmetrySector,
    WalkStrategy,
    WalkStrategyResult,
)
from .partitions import MultiscalePartitionComputer
from .resonance import ResonanceDescriptorComputer
from .symmetry import SymmetrySectorComputer
from ..core.geometry import GeometryModel
from ..core.graph import GraphModel
from ..fractals.registry import FractalRegistry
from ..simulation.quantum_walk import QuantumWalkSimulator


class GeometryCompiler:
    """Main GRC entry point."""

    def __init__(self, config: Optional[GeometryCompilerConfig] = None):
        self.config = config or GeometryCompilerConfig()
        self._registry = FractalRegistry()
        self._symmetry_computer = SymmetrySectorComputer()
        self._partition_computer = MultiscalePartitionComputer()
        self._resonance_computer = ResonanceDescriptorComputer()
        self._attractor_classifier = AttractorSignatureClassifier()

    def compile(
        self,
        geometry: Union[GeometryModel, str],
        *,
        level: Optional[int] = None,
        route: str = "ifs",
        strategies: Optional[List[str]] = None,
        emit_circuits: Optional[bool] = None,
        walk_steps: Optional[int] = None,
        initial_node: Optional[int] = None,
    ) -> CompilationResult:
        """Compile a geometry into a full CompilationResult."""
        # Resolve emit_circuits from config if not passed
        emit = emit_circuits if emit_circuits is not None else self.config.emit_circuits
        steps = walk_steps if walk_steps is not None else self.config.walk_steps
        init_node = initial_node if initial_node is not None else self.config.initial_node
        strat_list = strategies or self.config.strategies or ["staggered", "coined"]

        t0 = time.perf_counter()

        # Default level: use config default (3) if not specified
        resolved_level = level if level is not None else 3

        # 1. Resolve geometry (from str name or direct GeometryModel)
        if isinstance(geometry, str):
            geometry = self._registry.create(geometry, level=resolved_level, route=route)

        # 2. Derive graph
        graph = GraphModel.from_geometry(geometry)

        # 3. Structural decompositions
        symmetry: Optional[SymmetrySector] = None
        if self.config.compute_symmetry:
            symmetry = self._symmetry_computer.compute(graph)

        partition: Optional[MultiscalePartition] = None
        if self.config.compute_multiscale:
            partition = self._partition_computer.compute(graph, geometry)

        # 4. Per-strategy walk
        walk_results: Dict[str, WalkStrategyResult] = {}
        simulator = QuantumWalkSimulator(graph)

        for strat_name in strat_list:
            strategy = WalkStrategy(strat_name)
            wr = self._run_walk(simulator, strategy, graph, steps, init_node)

            res_desc = self._resonance_computer.compute(graph, wr)
            attr_sig = self._attractor_classifier.classify(wr, graph)

            circuit = None
            if emit:
                circuit = self._build_circuit(strategy, graph, steps, init_node)

            walk_results[strat_name] = WalkStrategyResult(
                strategy=strategy,
                walk_result=wr,
                circuit=circuit,
                attractor_signature=attr_sig,
                resonance_descriptor=res_desc,
            )

        primary = walk_results[strat_list[0]]
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return CompilationResult(
            source_type="fractal_generator" if isinstance(geometry, str) else "geometry_model",
            source_id=self._geometry_id(geometry, level, route),
            geometry=geometry,
            graph=graph,
            symmetry_sector=symmetry,
            multiscale_partition=partition,
            walk_results=walk_results,
            resonance_descriptor=primary.resonance_descriptor,
            attractor_signature=primary.attractor_signature,
            compile_time_ms=elapsed_ms,
            emit_circuits=emit,
            walk_strategies_computed=strat_list,
        )

    def _run_walk(self, simulator, strategy, graph, steps, init_node):
        """Route to the correct walk type based on strategy."""
        if strategy == WalkStrategy.COINED:
            return simulator.coined_walk(steps, init_node, coin="hadamard")
        elif strategy == WalkStrategy.STAGGERED:
            return simulator.staggered_walk(steps, init_node)
        elif strategy == WalkStrategy.QUTRIT:
            # Fall back to staggered for qutrit — actual qutrit sim deferred
            return simulator.staggered_walk(steps, init_node)
        elif strategy == WalkStrategy.STAGGERED_CONTINUOUS:
            return simulator.staggered_walk(steps, init_node)
        else:
            return simulator.staggered_walk(steps, init_node)

    def _build_circuit(self, strategy, graph, steps, init_node):
        """Deferred — emitters handle circuit building."""
        return None

    def _geometry_id(self, geometry, level, route):
        if isinstance(geometry, str):
            return f"{geometry}:level={level},route={route}"
        return f"geometry:{geometry.meta.fractal_type}:level={geometry.meta.level}"
