from time import perf_counter
from database import connect

for _ in range(3):
    start = perf_counter()
    with connect() as connection:
        connected = perf_counter()
        connection.execute("SELECT 1").fetchone()
        queried = perf_counter()

    print(
        f"建立連線：{connected - start:.3f} 秒；"
        f"SELECT 1：{queried - connected:.3f} 秒"
    )
