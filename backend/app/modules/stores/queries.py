from app.core.errors import error_response


STORE_COLUMNS = "id, slug, city, name, address, latitude, longitude, timezone, opening_hours, languages, is_demo, image_url"


def stores(connection, city):
    query = f"SELECT {STORE_COLUMNS} FROM stores WHERE active"
    params = ()
    if city is not None:
        query += " AND city = %s"
        params = (city.value,)
    rows = connection.execute(query + " ORDER BY city, slug", params).fetchall()
    return {"data": rows}


def store_detail(store_id, request, connection):
    row = connection.execute(
        f"SELECT {STORE_COLUMNS} FROM stores WHERE active AND id = %s", (store_id,)
    ).fetchone()
    if row is None:
        return error_response(request, 404, "STORE_NOT_FOUND", "找不到這間門市。")
    return row
