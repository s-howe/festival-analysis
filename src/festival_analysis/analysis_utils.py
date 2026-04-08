import duckdb
import pandas as pd

from .config import DB_PATH


def query_db(query: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    return con.execute(query=query).df()
