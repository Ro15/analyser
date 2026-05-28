from collections import namedtuple

# Every gate returns this. passed: bool, score: float (0-10 unless noted),
# reasoning: human-readable string explaining the verdict.
GateResult = namedtuple("GateResult", ["passed", "score", "reasoning"])
