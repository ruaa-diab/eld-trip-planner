"""US states and nearby non-US regions, to check the state a user typed ("Toronto, ON")."""

import re

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia", "PR": "Puerto Rico",
}

# Canadian provinces and territories: the non-US regions a US trucking address is mixed up with.
CANADIAN_REGIONS = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}

_US_BY_NAME = {name.lower(): code for code, name in US_STATES.items()}
_CA_BY_NAME = {name.lower(): code for code, name in CANADIAN_REGIONS.items()}
_CA_BY_NAME.update({"newfoundland": "NL", "pei": "PE", "québec": "QC"})

# Last part after a comma, with an optional ZIP: "IL", "IL 60632", "Illinois".
_LAST_PART = re.compile(r"^(?P<region>[^\d]+?)(?:\s+\d{5}(?:-\d{4})?)?$")
_COUNTRY_SUFFIX = re.compile(r",\s*(USA|US|U\.S\.A?\.?|United States(?: of America)?)\s*$", re.IGNORECASE)


def typed_region(text):
    """What region the user typed after the last comma.

    Returns ("us", "IL"), ("non_us", "ON"), ("unknown_code", "XX"), or None when the text
    doesn't end with a region (e.g. "Toronto" or "4400 S Pulaski Rd, Chicago").
    """
    text = _COUNTRY_SUFFIX.sub("", (text or "").strip())
    if "," not in text:
        return None
    last = text.rsplit(",", 1)[1].strip()
    match = _LAST_PART.match(last)
    if not match:
        return None
    region = match.group("region").strip().rstrip(".")
    key = region.lower()

    if len(region) == 2 and region.isalpha():
        code = region.upper()
        if code in US_STATES:
            return ("us", code)
        if code in CANADIAN_REGIONS:
            return ("non_us", code)
        return ("unknown_code", code)
    if key in _US_BY_NAME:
        return ("us", _US_BY_NAME[key])
    if key in _CA_BY_NAME:
        return ("non_us", _CA_BY_NAME[key])
    return None
