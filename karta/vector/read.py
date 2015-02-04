""" Convenience reader functions """

import os
from numbers import Number
import shapefile
from . import geometry
from . import geojson
from . import xyfile
from ..crs2 import LonLatWGS84, CustomCRS, CRSError
from .metadata import Metadata

def read_geojson(f):
    """ Read a GeoJSON object file and return a list of geometries """

    def convert_geometry(geom, defaultcrs=None, **kw):
        if isinstance(geom, geojson.Point):
            return geometry.Point(geom.coordinates, crs=geom.crs, **kw)
        elif isinstance(geom, geojson.MultiPoint):
            return geometry.Multipoint(geom.coordinates, crs=geom.crs, **kw)
        elif isinstance(geom, geojson.LineString):
            return geometry.Line(geom.coordinates, crs=geom.crs, **kw)
        elif isinstance(geom, geojson.Polygon):
            return geometry.Polygon(geom.coordinates[0],
                                 subs=geom.coordinates[1:],
                                 crs=geom.crs, **kw)
        else:
            raise TypeError("Argument to convert_geometry is a not a JSON geometry")

    def convert_feature(feat, **kw):
        data = feat.properties["vector"]
        for key, val in data.items():
            if any(isinstance(a, Number) or hasattr(a, "dtype") for a in val):
                for i in range(len(val)):
                    if val[i] is None:
                        val[i] = float('nan')
        prop = feat.properties["scalar"]
        return convert_geometry(feat.geometry, data=data, properties=prop, **kw)

    R = geojson.GeoJSONReader(f)
    gplist = []
    for item in R.items():
        if isinstance(item, geojson.Feature):
            gplist.append(convert_feature(item))
        elif isinstance(item, geojson.FeatureCollection):
            for feature in item.features:
                gplist.append(convert_feature(feature, defaultcrs=item.crs))
        else:
            gplist.append(convert_geometry(item))
    return gplist

def _geojson_properties2karta(properties, n):
    """ Takes a dictionary (derived from a GeoJSON properties object) and
    divides it into singleton properties and *n*-degree data. """
    props = {}
    data = {}
    for (key, value) in properties.items():
        if isinstance(value, list) or isinstance(value, tuple):
            if len(value) == n:
                data[key] = value
            else:
                raise ValueError("properties must be singleton or per-vertex")
        else:
            props[key] = value
    return props, data

def read_xyfile(f, delimiter='', header_rows=0, astype=geometry.Multipoint, coordrank=2):
    """ Read an ASCII delimited table and return a geometry object given by *astype*.
    """
    dat = xyfile.load_xy(f, delimiter=delimiter, header_rows=header_rows)
    ncols = dat.shape[1]
    if ncols >= coordrank:
        coords = dat[:,:coordrank]
        if ncols > coordrank:
            data = dat[:,coordrank:]
        else:
            data = None
        return astype(coords, data=data)
    else:
        raise IOError('data table has insufficient number of columns')

### Shapefile functions ###

def get_filenames(stem, check=False):
    """ Given a filename basename, return the associated shapefile paths. If
    `check` is True, ensure that the files exist."""
    shp = stem + '.shp'
    shx = stem + '.shx'
    dbf = stem + '.dbf'
    if check:
        for fnm in (shp, shx, dbf):
            if not os.path.isfile(fnm):
                raise Exception('missing {0}'.format(fnm))
    return {'shp':shp, 'shx':shx, 'dbf':dbf}

def open_file_dict(fdict):
    """ Open each file in a dictionary of filenames and return a matching
    dictionary of the file objects. """
    files = {}
    for ext in fdict.keys():
        files[ext] = open(fdict[ext], 'rb')
    return files

dBase_type_dict = {"I": int,
                   "O": float,
                   "C": str,
                   "@": lambda a: a,    # Temporary
                   "D": lambda a: a,
                   "L": bool}

def recordsasdata(reader):
    """ Interpret shapefile records as a Metadata object """
    d = {}
    idfunc = lambda a: a
    records = [rec for rec in reader.records()]
    for (i,k) in enumerate(reader.fields[1:]):
        f = dBase_type_dict.get(k[1], idfunc)
        d[k[0]] = [f(rec[i]) for rec in records]
    return Metadata(d)

def recordsasproperties(reader):
    """ Interpret shapefile records as a list of properties dictionaries """
    proplist = []
    keys = reader.fields
    idfunc = lambda a: a
    for (i,rec) in enumerate(reader.records()):
        properties = {}
        for (k,v) in zip(keys, rec):
            f = dBase_type_dict.get(k[1], idfunc)
            properties[k[0]] = f(v)
        proplist.append(properties)
    return proplist

def read_shapefile(name, crs=LonLatWGS84):
    """ Read a shapefile given `name`, which may include or exclude the .shp
    extension. The CRS must be specified, otherwise it is assumed to be
    cartesian. """
    if os.path.splitext(name)[1] == ".shp":
        name = name[:-4]
    fnms = get_filenames(name, check=True)

    try:
        files = open_file_dict(fnms)
        reader = shapefile.Reader(shp=files['shp'], shx=files['shx'],
                                  dbf=files['dbf'])

        if reader.shapeType == 1:       # Points
            verts = [shp.points[0] for shp in reader.shapes()]
            d = recordsasdata(reader)
            geoms = [geometry.Multipoint(verts, data=d, crs=crs)]

        elif reader.shapeType == 3:     # Lines
            plist = recordsasproperties(reader)
            geoms = []
            for (shp,prop) in zip(reader.shapes(), plist):
                parts = list(shp.parts)
                parts.append(len(shp.points))
                for (i0, i1) in zip(parts[:-1], parts[1:]):
                    points = shp.points[i0:i1]
                    geoms.append(geometry.Line(points, properties=prop, crs=crs))

        elif reader.shapeType == 5:     # Polygon
            plist = recordsasproperties(reader)
            geoms = []
            for (shp,prop) in zip(reader.shapes(), plist):
                parts = list(shp.parts)
                parts.append(len(shp.points))
                for (i0, i1) in zip(parts[:-1], parts[1:]):
                    # Shapefile polygons are closed explicitly, while karta
                    # polygons are closed implicitly
                    points = shp.points[i0:i1-1]
                    geoms.append(geometry.Polygon(points, properties=prop, crs=crs))

        else:
            raise NotImplementedError("Shapefile shape type {0} not "
                "implemented".format(reader.shapeType))

    finally:
        for f in files.values():
            f.close()

    return geoms

