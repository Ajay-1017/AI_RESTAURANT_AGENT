import math

from app.schemas.restaurant import Location

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: Location, b: Location) -> float:
    """Great-circle distance between two points on Earth, in kilometres.

    Latitude/longitude are angles on a sphere, so flat x/y distance would be wrong.
    """
    lat1, lng1, lat2, lng2 = map(math.radians, (a.lat, a.lng, b.lat, b.lng))
    d_lat = lat2 - lat1
    d_lng = lng2 - lng1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
