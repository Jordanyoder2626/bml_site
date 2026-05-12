import mysql.connector
import glob

def split_sql(sql_script):
    # naive but effective splitter for most schema files
    statements = []
    statement = ""

    for line in sql_script.splitlines():
        line = line.strip()

        if not line or line.startswith("--"):
            continue

        statement += line + " "

        if line.endswith(";"):
            statements.append(statement.strip())
            statement = ""

    if statement.strip():
        statements.append(statement.strip())

    return statements


try:
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Sammygrace26",
        database="fantasy"
    )

    if connection.is_connected():
        print("Successfully connected to MySQL!")

        cursor = connection.cursor()

        sql_files = sorted(glob.glob("databases/*.sql"))

        if not sql_files:
            print("No SQL files found.")
        else:
            for file_path in sql_files:
                print(f"Running: {file_path}")

                with open(file_path, "r", encoding="utf-8") as f:
                    sql_script = f.read()

                statements = split_sql(sql_script)

                for stmt in statements:
                    cursor.execute(stmt)

                connection.commit()
                print(f"Finished: {file_path}")

        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()
        print("MySQL version:", version[0])

except mysql.connector.Error as err:
    print("Connection failed:", err)

finally:
    if 'connection' in locals() and connection.is_connected():
        connection.close()
        print("Connection closed")