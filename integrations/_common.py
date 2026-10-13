def get_field(obj, *path, default=0):
    """Lee obj.a.b o obj["a"]["b"] indistintamente (respuestas SDK u objetos dict)."""
    for key in path:
        if obj is None:
            return default
        obj = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    return default if obj is None else obj


def day_anchor(day) -> "datetime":
    """Fecha de un registro diario del proveedor (día UTC) anclada a las 12:00 UTC.
    A medianoche UTC caería en el día anterior en América (UTC-6 → 18:00 del día previo); a mediodía
    conserva su fecha calendario en cualquier zona entre UTC-11 y UTC+11."""
    from datetime import date, datetime, time, timezone

    if isinstance(day, datetime):
        day = day.astimezone(timezone.utc).date()
    assert isinstance(day, date)
    return datetime.combine(day, time(12), tzinfo=timezone.utc)
