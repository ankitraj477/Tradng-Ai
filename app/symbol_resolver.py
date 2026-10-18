import re


class SymbolResolver:
    """
    Symbol linking engine using company aliases and ISIN mappings.
    Eliminates false-positive substring and ticker collisions on common dictionary words.
    """
    def __init__(self, alias_map=None, isin_map=None):
        self.aliases = {}
        self.isins = {}

        # Default standard NIFTY heavyweights mapping
        default_isins = {
            "INE002A01018": "RELIANCE.NS",
            "INE467B01029": "TCS.NS",
            "INE040A01034": "HDFCBANK.NS",
            "INE009A01021": "INFY.NS",
            "INE090A01021": "ICICIBANK.NS",
            "INE062A01020": "SBIN.NS",
            "INE397D01024": "BHARTIARTL.NS",
            "INE154A01025": "ITC.NS",
            "INE075A01022": "WIPRO.NS",
            "INE018A01030": "LT.NS"
        }
        default_aliases = {
            "reliance industries": "RELIANCE.NS",
            "reliance ind": "RELIANCE.NS",
            "tata consultancy services": "TCS.NS",
            "tcs": "TCS.NS",
            "hdfc bank": "HDFCBANK.NS",
            "infosys": "INFY.NS",
            "icici bank": "ICICIBANK.NS",
            "state bank of india": "SBIN.NS",
            "sbi": "SBIN.NS",
            "bharti airtel": "BHARTIARTL.NS",
            "airtel": "BHARTIARTL.NS",
            "itc limited": "ITC.NS",
            "wipro": "WIPRO.NS",
            "larsen & toubro": "LT.NS",
            "l&t": "LT.NS"
        }

        self.isins.update(default_isins)
        if isin_map: self.isins.update(isin_map)

        self.aliases.update(default_aliases)
        if alias_map:
            for k, v in alias_map.items():
                self.aliases[k.lower().strip()] = v

        # Compile regexes sorted by alias length (longer alias match first)
        self._sorted_aliases = sorted(self.aliases.keys(), key=len, reverse=True)

    def add_alias(self, alias, symbol):
        self.aliases[alias.lower().strip()] = symbol
        self._sorted_aliases = sorted(self.aliases.keys(), key=len, reverse=True)

    def add_isin(self, isin, symbol):
        self.isins[isin.upper().strip()] = symbol

    def resolve(self, text):
        """Resolves symbols from headline or body text using ISINs and verified aliases."""
        if not text: return []
        t_lower = text.lower()
        matched = set()

        # 1. Match ISIN (e.g. INE002A01018)
        isin_matches = re.findall(r"\b(INE[0-9A-Z]{9})\b", text.upper())
        for isin in isin_matches:
            if isin in self.isins:
                matched.add(self.isins[isin])

        # 2. Match verified aliases with word boundaries
        for alias in self._sorted_aliases:
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, t_lower):
                matched.add(self.aliases[alias])

        return sorted(list(matched))
