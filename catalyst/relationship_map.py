"""Stock relationship graph: suppliers, customers, competitors, sympathy names.

Used by the Phase-5 propagation engine to surface second-order read-through
plays when a primary catalyst is detected (e.g. an NVDA event -> AMD/MU/AVGO).
Seeded with major tech/semi/AI names; extend via add_edge / the RELATIONSHIPS dict.
"""
from collections import defaultdict

# relation in: supplier | customer | competitor | sympathy
RELATIONSHIPS = {
    "NVDA": [("AMD", "competitor"), ("AVGO", "competitor"), ("MU", "supplier"),
             ("TSM", "supplier"), ("ARM", "supplier"), ("SMCI", "customer"),
             ("DELL", "customer"), ("MSFT", "customer"), ("META", "customer")],
    "AMD": [("NVDA", "competitor"), ("INTC", "competitor"), ("TSM", "supplier"),
            ("MU", "supplier")],
    "AVGO": [("NVDA", "competitor"), ("MRVL", "competitor"), ("TSM", "supplier"),
             ("AAPL", "customer")],
    "TSM": [("NVDA", "customer"), ("AMD", "customer"), ("AAPL", "customer"),
            ("AVGO", "customer"), ("ASML", "supplier")],
    "MU": [("NVDA", "customer"), ("AMD", "customer"), ("WDC", "competitor")],
    "ARM": [("NVDA", "customer"), ("AAPL", "customer"), ("QCOM", "customer")],
    "AAPL": [("TSM", "supplier"), ("AVGO", "supplier"), ("QCOM", "supplier"),
             ("ARM", "supplier"), ("SWKS", "supplier")],
    "MSFT": [("NVDA", "supplier"), ("AMD", "supplier"), ("OPENAI", "partner")],
    "META": [("NVDA", "supplier"), ("AMD", "supplier")],
    "QCOM": [("ARM", "supplier"), ("AAPL", "customer"), ("AVGO", "competitor")],
    "TSLA": [("PANW", "sympathy"), ("RIVN", "competitor"), ("GM", "competitor"),
             ("F", "competitor"), ("PANT", "supplier")],
}


def _build_undirected():
    g = defaultdict(set)
    for src, edges in RELATIONSHIPS.items():
        for dst, rel in edges:
            g[src].add((dst, rel))
            inv = {"supplier": "customer", "customer": "supplier"}.get(rel, rel)
            g[dst].add((src, inv))
    return g


_GRAPH = _build_undirected()


def related(ticker, relations=None):
    """Neighbors of a ticker, optionally filtered to specific relation types."""
    out = _GRAPH.get(ticker.upper(), set())
    if relations:
        out = {(t, r) for t, r in out if r in relations}
    return sorted(out)


def read_through(ticker):
    """Tickers likely to move in sympathy with a catalyst on `ticker`."""
    return [t for t, _ in related(ticker)]


def add_edge(src, dst, relation):
    _GRAPH[src.upper()].add((dst.upper(), relation))
    inv = {"supplier": "customer", "customer": "supplier"}.get(relation, relation)
    _GRAPH[dst.upper()].add((src.upper(), inv))
