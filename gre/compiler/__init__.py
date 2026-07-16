"""Public API for the GRE Compiler layer."""

from .compiler import GeometryCompiler
from .ir import (
    CompilationResult,
    ResonanceDescriptor,
    AttractorSignature,
    SymmetrySector,
    MultiscalePartition,
    WalkStrategy,
    WalkStrategyResult,
    GeometryCompilerConfig,
)
from .comparison import CorpusComparisonView
from .bridge import compare_compilation_to_corpus, CorpusComparisonView as BridgeCorpusComparisonView
