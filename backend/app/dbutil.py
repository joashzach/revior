"""DB helpers: fast bulk insert (COPY / jsonb), array-parameter id filters."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ARRAY, BigInteger, any_, literal, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

COPY_THRESHOLD = 40   # below this a single jsonb statement is just as fast


def in_ids(col, ids):
    """`col IN (...)` for large id sets as a single array parameter (`col = ANY(:ids)`) - keeps statements tiny."""
    return col == any_(literal(list(ids), ARRAY(BigInteger)))


def _fill_defaults(table, rows: list[dict], keys: list[str]) -> tuple[list[dict], list[str]]:
    """Python-side column defaults (created_at, status, ...) for columns omitted from the rows."""
    for c in table.columns:
        if c.key not in keys and c.default is not None and not c.primary_key:
            arg = c.default.arg
            val = arg(None) if callable(arg) else arg
            rows = [{**r, c.key: val} for r in rows]
            keys.append(c.key)
    keys.sort()
    return rows, keys


async def bulk(session: AsyncSession, model, rows: list[dict], returning: tuple | None = None):
    """Bulk insert. Large batches use ``COPY`` (ids for `returning` come from sequence values reserved up
    front); small ones a single ``jsonb_populate_recordset`` statement. Keys missing in some rows become NULL
    (the column must be nullable or present in every row). Returns tuples of the `returning` columns."""
    if not rows:
        return []
    table = model.__table__
    keys = sorted({k for r in rows for k in r})
    rows, keys = _fill_defaults(table, rows, keys)
    if len(rows) >= COPY_THRESHOLD:
        return await _copy(session, table, rows, keys, returning)
    cols = ", ".join(f'"{k}"' for k in keys)
    sql = (f'INSERT INTO "{table.name}" ({cols}) SELECT {cols} '
           f'FROM jsonb_populate_recordset(NULL::"{table.name}", CAST(:data AS jsonb))')
    if returning:
        sql += " RETURNING " + ", ".join(f'"{c.key}"' for c in returning)
    res = await session.execute(text(sql), {"data": json.dumps(rows, default=str)})
    return [tuple(r) for r in res.all()] if returning else []


def _encode(col, v):
    if v is None:
        return None
    if isinstance(col.type, JSONB) or isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    if isinstance(v, (datetime, date)):
        return v
    return v


async def _copy(session: AsyncSession, table, rows: list[dict], keys: list[str], returning):
    ret_cols = [c.key for c in returning] if returning else []
    want_ids = "id" in ret_cols and "id" not in keys
    if want_ids:
        seq = f"pg_get_serial_sequence('\"{table.name}\"', 'id')"
        ids = [r[0] for r in (await session.execute(text(
            f"SELECT nextval({seq}) FROM generate_series(1, :n)"), {"n": len(rows)})).all()]
        rows = [{**r, "id": i} for r, i in zip(rows, ids)]
        keys = sorted(keys + ["id"])
    cols = {c.key: c for c in table.columns}
    records = [tuple(_encode(cols[k], r.get(k)) for k in keys) for r in rows]
    conn = await session.connection()
    raw = await conn.get_raw_connection()
    await raw.driver_connection.copy_records_to_table(table.name, records=records, columns=keys, schema_name="public")
    return [tuple(r.get(c) for c in ret_cols) for r in rows] if returning else []
