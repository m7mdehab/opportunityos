"""Closed geographic vocabulary and explicit country membership."""

REGIONS = {
    "WORLDWIDE": frozenset(),  # Special: matches every ISO country.
    "AFRICA": frozenset({"EG", "ZA", "NG", "KE", "MA", "TN"}),
    "NORTH_AFRICA": frozenset({"EG", "MA", "TN", "DZ", "LY", "SD"}),
    "MENA": frozenset({"EG", "SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "MA", "TN", "DZ", "LY"}),
    "EMEA": frozenset({"EG", "SA", "AE", "QA", "KW", "BH", "OM", "GB", "DE", "FR", "ES", "IT", "NL", "SE", "PL"}),
    "GCC": frozenset({"SA", "AE", "QA", "KW", "BH", "OM"}),
    "EU": frozenset({"DE", "FR", "ES", "IT", "NL", "SE", "PL", "IE", "PT"}),
    "EEA": frozenset({"DE", "FR", "ES", "IT", "NL", "SE", "PL", "IE", "PT", "NO", "IS", "LI"}),
    "EUROPE": frozenset({"GB", "DE", "FR", "ES", "IT", "NL", "SE", "PL", "IE", "PT", "NO", "CH"}),
    "AMERICAS": frozenset({"US", "CA", "BR", "MX", "AR"}), "LATAM": frozenset({"BR", "MX", "AR", "CL", "CO", "PE"}),
    "APAC": frozenset({"AU", "NZ", "IN", "JP", "SG", "KR"}),
}


def includes(token: str, country: str) -> bool:
    return token == country or token == "WORLDWIDE" or country in REGIONS.get(token, frozenset())
