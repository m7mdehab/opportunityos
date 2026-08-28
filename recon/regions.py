"""Closed geographic vocabulary and explicit country membership."""

_EU = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
})

_EEA = _EU | frozenset({"NO", "IS", "LI"})

_EUROPE = _EEA | frozenset({
    "GB", "CH", "AL", "BA", "ME", "MK", "RS", "UA", "AD", "BY", "MD", "MC", "SM", "VA", "XK",
})

_AFRICA = frozenset({
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD", "KM", "CG",
    "CD", "CI", "DJ", "EG", "GQ", "ER", "ET", "GA", "GM", "GH", "GN", "GW",
    "KE", "LS", "LR", "LY", "MG", "MW", "ML", "MR", "MU", "MA", "MZ", "NA",
    "NE", "NG", "RW", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "SZ",
    "TZ", "TG", "TN", "UG", "ZM", "ZW",
})

_NORTH_AFRICA = frozenset({"EG", "SD", "LY", "DZ", "MA", "TN"})

_MENA = frozenset({
    "EG", "SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "PS", "YE",
    "SY", "MA", "TN", "DZ", "LY", "SD",
})

_GCC = frozenset({"SA", "AE", "QA", "KW", "BH", "OM"})

_LATAM = frozenset({
    "BR", "MX", "AR", "CL", "CO", "PE", "UY", "PY", "BO", "EC", "VE",
    "PA", "CR", "GT", "HN", "SV", "NI", "CU", "DO", "PR",
})

_AMERICAS = _LATAM | frozenset({"US", "CA", "JM", "TT", "BS", "BB"})

_APAC = frozenset({"AU", "NZ", "IN", "JP", "SG", "KR", "PH", "VN", "TH", "MY", "ID", "TW", "HK"})

_EMEA = _EUROPE | _MENA | _AFRICA

REGIONS = {
    "WORLDWIDE": frozenset(),
    "EU": _EU,
    "EEA": _EEA,
    "EUROPE": _EUROPE,
    "AFRICA": _AFRICA,
    "NORTH_AFRICA": _NORTH_AFRICA,
    "MENA": _MENA,
    "EMEA": _EMEA,
    "GCC": _GCC,
    "AMERICAS": _AMERICAS,
    "LATAM": _LATAM,
    "APAC": _APAC,
}


def includes(token: str, country: str) -> bool:
    return token == country or token == "WORLDWIDE" or country in REGIONS.get(token, frozenset())
