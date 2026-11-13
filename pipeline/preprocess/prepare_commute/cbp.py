"""Read raw and prepared County Business Patterns establishment counts."""
import os
import zipfile

import pandas as pd

from src.settings import INTERIM_DATA_DIR

CBP_URL = "https://www2.census.gov/programs-surveys/cbp/data/2020/CB2000CBP.zip"


def read_cbp_counties(path):
    """
    One row per county from 2020 County Business Patterns: `county` (5-digit FIPS),
    `NAME`, `ESTAB`, for all industries (NAICS2017 00), all legal forms (LFO 001) and
    all establishment sizes (EMPSZES 001).

    Accepts the paper's pipe-delimited CB2000CBP.zip / CB2000CBP.dat (streamed, not
    extracted) or a data.census.gov table CSV (CBP2020.CB2000CBP-Data.csv). Only
    county geographies (GEO_ID 0500000US...) are kept; the national file also holds
    ZIP-code, metro and state rows whose last five characters can look like a county.
    """
    if path.endswith((".zip", ".dat")):
        cols = ["GEO_ID", "GEO_LABEL", "NAICS2017", "LFO", "EMPSZES", "ESTAB"]
        if path.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                with z.open(z.namelist()[0]) as f:
                    cbp = _filter_cbp_chunks(pd.read_csv(f, sep="|", usecols=cols, dtype=str, chunksize=2_000_000))
        else:
            cbp = _filter_cbp_chunks(pd.read_csv(path, sep="|", usecols=cols, dtype=str, chunksize=2_000_000))
        cbp = cbp[(cbp["LFO"] == "001") & (cbp["EMPSZES"] == "001")].rename(columns={"GEO_LABEL": "NAME"})
    else:
        cbp = pd.read_csv(path, dtype=str)
        cbp = cbp[cbp["GEO_ID"].str.startswith("0500000US", na=False)
                  & (cbp["NAICS2017"] == "00")
                  & (cbp["EMPSZES_LABEL"] == "All establishments")]
        if "LFO" in cbp.columns:
            cbp = cbp[cbp["LFO"] == "001"]
    cbp = cbp.assign(county=cbp["GEO_ID"].str[-5:], ESTAB=cbp["ESTAB"].astype(int))
    cbp = cbp[["county", "NAME", "ESTAB"]].sort_values("county").reset_index(drop=True)
    if cbp["county"].duplicated().any():
        raise ValueError(f"CBP has more than one all-establishments row for counties "
                         f"{sorted(cbp.loc[cbp['county'].duplicated(), 'county'])[:5]}")
    return cbp


def _filter_cbp_chunks(chunks):
    return pd.concat(ch[ch["GEO_ID"].str.startswith("0500000US") & (ch["NAICS2017"] == "00")] for ch in chunks)


def cbp_path(interim_data_path=None):
    return os.path.join(interim_data_path or INTERIM_DATA_DIR, 'cbp', 'workplace_cbp.csv')


def read_cbp(path):
    cbp = pd.read_csv(path).iloc[:, 1:]
    cbp['county'] = cbp['county'].astype(str)
    return cbp
