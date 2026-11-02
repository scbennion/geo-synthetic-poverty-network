"""Shared command-line options for restricting a run to one state and some counties."""
import argparse

from src.settings import state_codes, state_dict

_abbr_to_code = {abbr.lower(): code for code, abbr in state_dict.items()}


def add_geography_args(parser):
    parser.add_argument('--state', default=None,
                        help="state abbreviation or 2-digit FIPS (e.g. 'ut' or '49'); default: all states")
    parser.add_argument('--counties', default=None,
                        help="comma-separated 3-digit county FIPS within --state (e.g. '035,049'); default: all")
    return parser


def resolve_state_codes(state):
    """Return the list of 2-digit state FIPS codes to run."""
    if state is None:
        return list(state_codes)
    key = state.strip().lower()
    if key in _abbr_to_code:
        return [_abbr_to_code[key]]
    if key.isdigit() and key.zfill(2) in state_dict:
        return [key.zfill(2)]
    raise argparse.ArgumentTypeError(f"unknown state: {state!r}")


def parse_counties(counties):
    """Return a list of 3-digit county FIPS strings, or None for all counties."""
    if counties is None:
        return None
    parsed = []
    for c in counties.split(','):
        c = c.strip()
        if not c:
            continue
        if not c.isdigit() or len(c) > 3:
            raise argparse.ArgumentTypeError(f"county must be a 3-digit FIPS code: {c!r}")
        parsed.append(c.zfill(3))
    return parsed


def resolve_geography(args):
    """Validate --state/--counties together; returns (state_codes, counties)."""
    codes = resolve_state_codes(args.state)
    counties = parse_counties(args.counties)
    if counties is not None and len(codes) != 1:
        raise argparse.ArgumentTypeError("--counties requires --state")
    return codes, counties


def in_counties(ids, state_code, counties):
    """Boolean mask for tract GEOIDs or person IDs (both start with the 11-digit tract GEOID)."""
    ids = ids.astype(str)
    mask = ids.str[:2] == state_code
    if counties is not None:
        mask &= ids.str[2:5].isin(counties)
    return mask


def run_name(state_abbreviation, counties=None):
    """Output file prefix: 'ut' for a full-state run, 'ut_c035-049' for a county subset."""
    if counties is None:
        return state_abbreviation
    return f"{state_abbreviation}_c{'-'.join(sorted(counties))}"


def us_run_name(run_state_codes, counties=None):
    """Prefix for the combined outputs under 1-us/: 'us' for all states, else the single run's name."""
    if counties is None and list(run_state_codes) == list(state_codes):
        return 'us'
    return run_name(state_dict[run_state_codes[0]].lower(), counties)
