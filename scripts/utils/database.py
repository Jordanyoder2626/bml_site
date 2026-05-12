import os
from scripts.utils import constants
import mysql.connector
import pandas as pd
from sshtunnel import SSHTunnelForwarder


class Database:
    def __init__(self,
                 data: dict | list | pd.DataFrame = None,
                 table: str = None,
                 columns: str | list = None,
                 values: tuple = None,
                 season: int = None,
                 week: int = None,
                 use_ssh: bool = False):

        self.connection = None
        self.data = data
        self.table = table
        self.columns = columns
        self.values = values
        self.season = season
        self.week = week
        self.use_ssh = use_ssh
        self.tunnel = None

    # =========================================================
    # CONNECTION HANDLING
    # =========================================================

    def __enter__(self):
        if self.use_ssh:
            self.tunnel = SSHTunnelForwarder(
                (constants.DB_HOST_SSH, 22),
                ssh_username=constants.DB_USER_SSH,
                ssh_password=os.getenv('PA_PASS'),
                remote_bind_address=(constants.DB_MYSQL_HOST_SSH, 3306)
            )
            self.tunnel.start()

            self.connection = mysql.connector.connect(
                host='127.0.0.1',
                port=self.tunnel.local_bind_port,
                user=constants.DB_USER_SSH,
                password=constants.DB_PASS_SSH,
                database=constants.DB_NAME_SSH
            )

        else:
            self.connection = mysql.connector.connect(
                host=constants.DB_HOST,
                user=constants.DB_USER,
                password=constants.DB_PASS,
                database=constants.DB_NAME
            )

        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        if self.connection:
            self.connection.close()
        if self.tunnel:
            self.tunnel.stop()

    # =========================================================
    # DATA RETRIEVAL
    # =========================================================

    def retrieve_data(self, how: str):
        if how == 'week':
            query = f"""
                SELECT *
                FROM {self.table}
                WHERE season = {self.season}
                  AND week = {self.week};
            """

        elif how == 'season':
            query = f"""
                SELECT *
                FROM {self.table}
                WHERE season = {self.season}
                  AND week <= {self.week};
            """

        elif how == 'all':
            query = f"""
                SELECT *
                FROM {self.table};
            """

        with self as conn:
            return pd.read_sql(query, conn)

    # =========================================================
    # INSERT QUERY
    # =========================================================

    def sql_insert_query(self) -> str:
        """Generate INSERT query"""
        cols = (
            ", ".join(self.columns)
            if isinstance(self.columns, (list, tuple))
            else self.columns
        )

        placeholders = ", ".join(["%s"] * len(self.values))

        query = f"""
            INSERT INTO {self.table} ({cols})
            VALUES ({placeholders});
        """
        return query

    # =========================================================
    # 🔥 NEW: UPSERT QUERY (FIXES YOUR DUPLICATE ERRORS)
    # =========================================================

    def sql_upsert_query(self) -> str:
        """Insert or update on duplicate key"""
        cols = (
            self.columns
            if isinstance(self.columns, str)
            else ", ".join(self.columns)
        )

        placeholders = ", ".join(["%s"] * len(self.values))

        update_clause = ", ".join([
            f"{col}=VALUES({col})"
            for col in self.columns
            if col != "id"
        ])

        query = f"""
            INSERT INTO {self.table} ({cols})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_clause};
        """

        self._query = query
        return query

    # =========================================================
    # UPDATE SINGLE FIELD
    # =========================================================

    def sql_update_table(self, set_column, new_value, id_column, id_value, season, week) -> str:
        if isinstance(id_value, str):
            query = f"""
                UPDATE {self.table}
                SET {set_column} = {new_value}
                WHERE {id_column} = '{id_value}'
                  AND season = {season}
                  AND week = {week}
            """
        else:
            query = f"""
                UPDATE {self.table}
                SET {set_column} = {new_value}
                WHERE {id_column} = {id_value}
                  AND season = {season}
                  AND week = {week}
            """

        with self as db:
            c = db.cursor()
            c.execute(query, self.values)
            db.commit()

    # =========================================================
    # COMMIT SINGLE ROW
    # =========================================================

    def commit_row(self) -> None:
        with self as db:
            c = db.cursor()
            query = self.sql_insert_query()
            c.execute(query, self.values)
            db.commit()

    # =========================================================
    # COMMIT BULK DATA
    # =========================================================

    def commit_data(self) -> None:
        with self:
            if isinstance(self.data, dict):
                for _, v in self.data.items():
                    self.values = v
                    self.commit_row()

            elif isinstance(self.data, list):
                for v in self.data:
                    self.values = v
                    self.commit_row()

            elif isinstance(self.data, pd.DataFrame):
                for _, row in self.data.iterrows():
                    self.values = tuple(row)
                    self.commit_row()