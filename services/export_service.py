"""Exportación de datos del dashboard."""

import pandas as pd


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    # utf-8-sig para que Excel abra bien acentos.
    return df.to_csv(index=False).encode("utf-8-sig")
