"""Helpers that keep ZIP and census tract ids as fixed-width text."""
import pandas as pd


def _pad(series, width):
    s = series.copy()
    if pd.api.types.is_float_dtype(s) or pd.api.types.is_integer_dtype(s):
        # floats such as 13135050532.0 must go through int64, never str() directly
        s = s.astype("int64").astype(str)
    else:
        s = s.astype(str).str.strip().str.replace(r"\.0+$", "", regex=True)
    n_fixed = int((s.str.len() != width).sum())
    return s.str.zfill(width), n_fixed


def pad_zip(series):
    """Return (5-char ZIP strings, number of values that needed padding)."""
    return _pad(series, 5)


def pad_tract(series):
    """Return (11-char TractGeoID strings, number of values that needed padding)."""
    return _pad(series, 11)
