import duckdb
import pandas as pd

from .config import DB_PATH


def query_db(query: str, index: str | None = None) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(query=query).df()

    if index is not None:
        df.set_index(index, inplace=True)

    return df
