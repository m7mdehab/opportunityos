"""Closed geographic vocabulary and explicit country membership."""

REGIONS = {
    "WORLDWIDE": frozenset(),  # Special: matches every ISO country.
    # EU member states (27): all EU-27 countries as of 2024
    "EU": frozenset({
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE"
    }),
    # EEA: EU-27 + Norway, Iceland, Liechtenstein
    "EEA": frozenset({
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE", "NO", "IS", "LI"
    }),
    # EUROPE: EEA + UK, Switzerland, Albania, Bosnia, Montenegro, North Macedonia, Serbia, Ukraine
    "EUROPE": frozenset({
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE", "NO", "IS", "LI", "GB", "CH", "AL", "BA", "ME", "MK",
        "RS", "UA"
    }),
    # AFRICA: comprehensive list of African countries (54 UN-recognized states)
    "AFRICA": frozenset({
        "DZ", "AO", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD", "KM", "CG",
        "CD", "CI", "DJ", "EG", "GQ", "ER", "ET", "GA", "GM", "GH", "GN", "GW",
        "KE", "LS", "LR", "LY", "MG", "MW", "ML", "MR", "MU", "MA", "MZ", "NA",
        "NE", "NG", "RW", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "SZ",
        "TZ", "TG", "TN", "UG", "ZM", "ZW"
    }),
    # NORTH_AFRICA: Egypt, Sudan, Libya, Algeria, Morocco, Tunisia
    "NORTH_AFRICA": frozenset({"EG", "SD", "LY", "DZ", "MA", "TN"}),
    # MENA: Middle East and North Africa
    "MENA": frozenset({
        "EG", "SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "PS", "YE",
        "SY", "MA", "TN", "DZ", "LY", "SD"
    }),
    # EMEA: Europe, Middle East, Africa (for regional business)
    "EMEA": frozenset({
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE", "NO", "IS", "LI", "GB", "CH", "AL", "BA", "ME", "MK",
        "RS", "UA", "EG", "SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "IQ",
        "PS", "YE", "SY", "MA", "TN", "DZ", "LY", "SD", "DZ", "AO", "BJ", "BW",
        "BF", "BI", "CM", "CV", "CF", "TD", "KM", "CG", "CD", "CI", "DJ", "GQ",
        "ER", "ET", "GA", "GM", "GH", "GN", "GW", "KE", "LS", "LR", "MG", "MW",
        "ML", "MR", "MU", "MZ", "NA", "NE", "NG", "RW", "ST", "SN", "SC", "SL",
        "SO", "ZA", "SS", "SZ", "TZ", "TG", "UG", "ZM", "ZW"
    }),
    # GCC: Gulf Cooperation Council countries
    "GCC": frozenset({"SA", "AE", "QA", "KW", "BH", "OM"}),
    # Americas: North and South America
    "AMERICAS": frozenset({"US", "CA", "BR", "MX", "AR"}),
    # LATAM: Latin America
    "LATAM": frozenset({"BR", "MX", "AR", "CL", "CO", "PE"}),
    # APAC: Asia-Pacific
    "APAC": frozenset({"AU", "NZ", "IN", "JP", "SG", "KR"}),
}


def includes(token: str, country: str) -> bool:
    return token == country or token == "WORLDWIDE" or country in REGIONS.get(token, frozenset())
