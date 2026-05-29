"""Sector classification, sector ETFs, and macro sensitivity mappings.

Used by the sector-rotation, relative-strength, and macro gates. Sector for a
ticker comes from yfinance .info; everything degrades to neutral when unknown.
"""

# The 11 GICS sectors -> their SPDR sector ETF.
SECTOR_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

ALL_SECTOR_ETFS = list(SECTOR_ETF.values())

# Macro factor sensitivity per sector: +1 = the factor RISING is a tailwind,
# -1 = rising is a headwind, 0 = neutral. Factors keyed by macro ticker.
#   ^TNX = 10Y yield, DX-Y.NYB = dollar, CL=F = oil, GC=F = gold, ^SOX = semis
MACRO_SENSITIVITY = {
    "Technology":            {"^TNX": -1, "DX-Y.NYB": -1, "^SOX": +1},
    "Communication Services":{"^TNX": -1, "DX-Y.NYB": -1},
    "Financial Services":    {"^TNX": +1, "DX-Y.NYB":  0},
    "Energy":                {"CL=F": +1, "DX-Y.NYB": -1},
    "Basic Materials":       {"GC=F": +1, "DX-Y.NYB": -1, "CL=F": +1},
    "Utilities":             {"^TNX": -1},
    "Real Estate":           {"^TNX": -1},
    "Consumer Cyclical":     {"^TNX": -1, "DX-Y.NYB": -1},
    "Consumer Defensive":    {"^TNX":  0},
    "Healthcare":            {"^TNX": -1},
    "Industrials":           {"DX-Y.NYB": -1, "CL=F": -1},
}

MACRO_TICKERS = ["^TNX", "DX-Y.NYB", "CL=F", "GC=F", "^SOX"]

# The NASDAQ screener (our universe source) names sectors differently from the
# GICS names used above. Map screener -> GICS so the sector gates line up.
# "Miscellaneous" has no clean GICS sector -> left unmapped (gate goes neutral).
NASDAQ_SECTOR_TO_GICS = {
    "Technology": "Technology",
    "Finance": "Financial Services",
    "Health Care": "Healthcare",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Energy": "Energy",
    "Industrials": "Industrials",
    "Basic Materials": "Basic Materials",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Telecommunications": "Communication Services",
}


def to_gics(sector):
    """Normalize a sector name to the GICS vocabulary used here.

    Returns the input unchanged if it's already GICS, the mapped name for a
    NASDAQ-screener label, or None if it can't be mapped.
    """
    if not sector:
        return None
    if sector in SECTOR_ETF:
        return sector
    return NASDAQ_SECTOR_TO_GICS.get(sector)


def etf_for_sector(sector):
    return SECTOR_ETF.get(sector)
