import duckdb
import pandas as pd


def query_db(query: str) -> pd.DataFrame:
    con = duckdb.connect("./data/festival.duckdb", read_only=True)
    return con.execute(query=query).df()
