"""Small GeoJSON polygon validation and exact planar point inclusion (no dateline crossing)."""
from functools import lru_cache
import hashlib
import json
import math


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def on_segment(a,b,p):
    return abs(cross(a,b,p))<1e-10 and min(a[0],b[0])-1e-10<=p[0]<=max(a[0],b[0])+1e-10 and min(a[1],b[1])-1e-10<=p[1]<=max(a[1],b[1])+1e-10


def intersects(a,b,c,d):
    return (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0) or any([on_segment(a,b,c),on_segment(a,b,d),on_segment(c,d,a),on_segment(c,d,b)])


def validate_geometry(geometry):
    if geometry.get('type')!='Polygon' or not isinstance(geometry.get('coordinates'),list) or len(geometry['coordinates'])!=1:
        raise ValueError('A single GeoJSON Polygon exterior ring is supported; holes and MultiPolygons are not supported')
    ring=geometry['coordinates'][0]
    if not 4<=len(ring)<=501 or ring[0]!=ring[-1]:
        raise ValueError('Polygon must be closed with 3–500 vertices')
    for point in ring:
        if not isinstance(point,list) or len(point)!=2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in point):
            raise ValueError('coordinates must be finite longitude,latitude pairs')
        if not -180<=point[0]<=180 or not -90<=point[1]<=90:raise ValueError('coordinates outside WGS84')
    west,south=min(p[0] for p in ring),min(p[1] for p in ring)
    east,north=max(p[0] for p in ring),max(p[1] for p in ring)
    if east-west>180:raise ValueError('Split polygons crossing the antimeridian')
    for i in range(len(ring)-1):
        if ring[i]==ring[i+1]:raise ValueError('duplicate adjacent vertices')
        for j in range(i+2,len(ring)-1):
            if i==0 and j==len(ring)-2:continue
            if intersects(ring[i],ring[i+1],ring[j],ring[j+1]):raise ValueError('self-intersecting polygon')
    # Spherical longitude/sine-latitude area integral, approximate for straight map segments.
    area=abs(sum(math.radians(b[0]-a[0])*(math.sin(math.radians(a[1]))+math.sin(math.radians(b[1]))) for a,b in zip(ring,ring[1:])))*6371.0088**2/2
    if not 0.001<=area<=5_000_000:raise ValueError('Area must be 0.001–5000000 km²')
    canonical=json.dumps({'type':'Polygon','coordinates':[ring]},separators=(',',':'),sort_keys=True)
    return {'area_id':hashlib.sha256(canonical.encode()).hexdigest(),'geometry':canonical,'bbox':f'{west},{south},{east},{north}','approx_area_km2':area}


@lru_cache(maxsize=128)
def parsed(geometry):return json.loads(geometry)['coordinates'][0]


def within_area(lon,lat,geometry):
    ring=parsed(geometry);inside=False;p=(lon,lat)
    for a,b in zip(ring,ring[1:]):
        if on_segment(a,b,p):return True
        if (a[1]>lat)!=(b[1]>lat) and lon<(b[0]-a[0])*(lat-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside


def load_area(area_id):
    from .ingestion import connect
    if len(area_id)!=64 or any(c not in '0123456789abcdef' for c in area_id):raise ValueError('invalid area_id')
    with connect() as db:
        row=db.execute('SELECT * FROM areas WHERE id=?',(area_id,)).fetchone()
    if not row:raise ValueError('unknown area_id')
    return dict(row)
