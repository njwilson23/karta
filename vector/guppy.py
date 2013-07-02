"""
Geographical measurement and simple analysis module for Python 2.X.X. Provides
Point, Multipoint, Line, and Polygon classes, with methods for simple
measurements such as distance, area, and bearing.

Written by Nat Wilson (njwilson23@gmail.com)
"""

import math
import sys
import traceback
import numpy as np
import vtk
import geojson
import xyfile

from collections import deque
from metadata import GeoMetadata

try:
    import _cvectorgeo as _vecgeo
except ImportError:
    sys.stderr.write("falling back on slow _vectorgeo")
    import _vectorgeo as _vecgeo

try:
    import shapely.geometry as geometry
except ImportError:
    pass


class Point(object):
    """ This defines the point class, from which x,y[,z] points can be
    constructed.
    """
    _geotype = "Point"
    _datatype = None
    properties = {}

    def __init__(self, coords, data=None):
        self.vertex = coords
        self._setxyz()
        self.data = data
        return

    def _setxyz(self):
        self.x = self.vertex[0]
        self.y = self.vertex[1]
        try:
            self.z = self.vertex[2]
            self.rank = 3
        except IndexError:
            self.z = None
            self.rank = 2
        return

    def __repr__(self):
        return 'Point(' + str(self.vertex) + ')'

    def __eq__(self, other):
        if hasattr(other, "vertex"):
            return self.vertex == other.vertex
        else:
            return False

    def get_vertex(self):
        """ Return the Point vertex as a tuple. """
        return self.vertex

    def coordsxy(self, convert_to=False):
        """ Returns the x,y coordinates. Convert_to may be set to 'deg'
        or 'rad' for convenience.  """
        if convert_to == 'rad':
            return (self.x*3.14159/180., self.y*3.14159/180.)
        elif convert_to == 'deg':
            return (self.x/3.14159*180., self.y/3.14159*180.)
        else:
            return (self.x, self.y)

    def bearing(self, other, spherical=False):
        """ Returns the bearing from self to other in radians. Returns
        None if points have equal x and y. See point.azimuth() for
        z-axis directions. """
        dx = self.x - other.x
        dy = self.y - other.y

        if spherical is False:
            if dx == 0.0:
                if dy > 0.0:
                    return 0.0
                elif dy < 0.0:
                    return math.pi
                else:
                    return None

            elif dy >= 0.0:
                return math.atan(dy / dx)

            else:
                return math.atan(dy / dx) + math.pi

        elif spherical is True:
            raise NotImplementedError
        else:
            raise Exception("Value for 'spherical' kwarg not understood")
        return

    def azimuth(self, other, spherical=False):
        """ Returns the aximuth from self to other in radians. Returns None
        if points are coincident. """

        if self.z is None:
            raise GGeoError("Point.azimuth() cannot be called from a rank 2 "
                            "coordinate.")
        elif other.z is None:
            raise GGeoError("Point.azimuth() cannot be called on a rank 2 "
                            "coordinate.")

        distxy = math.sqrt((self.x-other.x)**2. + (self.y-other.y)**2.)
        dz = other.z - self.z

        if spherical is False:
            if distxy == 0.0:
                if dz > 0.0:
                    return 0.5 * np.pi
                elif dz < 0.0:
                    return -0.5 * np.pi
                elif dz == 0.0:
                    return np.nan
            else:
                return math.atan(dz / distxy)

        elif spherical is True:
            raise NotImplementedError("Not implemented")
        else:
            raise GuppyError("Value for 'spherical' kwarg not understood")
        return

    def walk(self, distance, bearing, azimuth=0.0, spherical=False):
        """ Wraps walk() """
        return walk(self, distance, bearing, azimuth=0.0, spherical=False)

    def distance(self, other):
        """ Returns a cartesian distance. """
        flat_dist = math.sqrt((self.x-other.x)**2. + (self.y-other.y)**2.)
        if self.z is None or other.z is None:
            return flat_dist
        else:
            return math.sqrt(flat_dist**2. + (self.z-other.z)**2.)

    def shift(self, shift_vector):
        """ Shift point by the amount given by a vector. Operation occurs
        in-place """
        if len(shift_vector) != self.rank:
            raise GGeoError('Shift vector length must equal geometry rank.')

        self.vertex = tuple([a+b for a,b in zip(self.vertex, shift_vector)])
        self._setxyz()
        return

    def as_geojson(self, **kwargs):
        """ Write data as a GeoJSON string to a file-like object `f`.

        Parameters
        ----------
        f : file-like object to recieve the GeoJSON string

        *kwargs* include:
        crs : coordinate reference system
        crs_fmt : format of `crs`; may be one of ('epsg','ogc_crs_urn')
        bbox : an optional bounding box tuple in the form (w,e,s,n)
        """
        writer = geojson.GeoJSONWriter(self, **kwargs)
        return writer.print_json()

    def to_geojson(self, f, **kwargs):
        """ Write data as a GeoJSON string to a file-like object `f`.

        Parameters
        ----------
        f : file-like object to recieve the GeoJSON string

        *kwargs* include:
        crs : coordinate reference system
        crs_fmt : format of `crs`; may be one of ('epsg','ogc_crs_urn')
        bbox : an optional bounding box tuple in the form (w,e,s,n)
        """
        writer = geojson.GeoJSONWriter(self, **kwargs)
        writer.write_json(f)
        return writer

    def to_shapely(self):
        """ Returns a Shapely Point instance. """
        try:
            return geometry.Point(self.x, self.y, self.z)
        except NameError:
            raise ImportError('Shapely module did not import\n')


class Multipoint(object):
    """ Point cloud with associated attributes. This is a base class for the
    polyline and polygon classes. """
    _geotype = "Multipoint"
    _datatype = None
    properties = {}

    def __init__(self, vertices, data=None, properties=None, **kwargs):
        """ Create a feature with multiple vertices.

        vertices : a list of tuples containing point coordinates.

        data : is either `None` a list of point attributes, or a dictionary of
        point attributes. If `data` is not `None`, then it (or its values) must
        match `vertices` in length.
        """
        if len(vertices) > 0:
            self.rank = len(vertices[0])

            if self.rank > 3 or self.rank < 2:
                raise GInitError('Input must be doubles or triples\n')
            elif False in [self.rank == len(i) for i in vertices]:
                raise GInitError('Input must have consistent rank\n')
            else:
                self.vertices = [tuple(i) for i in vertices]

            self.data = GeoMetadata(data)

            if hasattr(properties, 'keys'):
                self.properties = properties

        else:
            self.rank = None
            self.vertices = []
            self.data = []
        return

    #def __repr__(self):
    #    return 'Multipoint(' + reduce(lambda a,b: str(a) + ' ' + str(b),
    #            self.vertices) + ')'

    def __len__(self):
        return len(self.vertices)

    def __getitem__(self, key):
        if not isinstance(key, int):
            raise GGeoError('Indices must be integers')
        return self.vertices[key]

    def __setitem__(self, key, value):
        if not isinstance(key, int):
            raise GGeoError('Indices must be integers')
        if len(value) != self.rank:
            raise GGeoError('Cannot insert values with'
                            'rank != {0}'.format(self.rank))
        self.vertices[key] = value

    def __delitem__(self, key):
        if len(self) > key:
            del self.vertices[key]
            if hasattr(self.data, 'keys') and hasattr(data.values, '__call__'):
                for k in self.data:
                    del self.data[k][key]
            else:
                del self.data[key]
        else:
            raise GGeoError('Index ({0}) exceeds length'
                            '({1})'.format(key, len(self)))

    def __iter__(self):
        return (pt for pt in self.vertices)

    def _bbox_overlap(self, other):
        """ Return whether bounding boxes between self and another geometry
        overlap.
        """
        reg0 = self.get_bbox()
        reg1 = other.get_bbox()
        return (reg0[0] < reg1[1] and reg0[1] > reg1[0] and
                reg0[2] < reg1[3] and reg0[3] > reg1[2])

    def get_bbox(self):
        """ Return the extents of a bounding box as
            (xmin, ymax, ymin, ymax, [zmin, zmin]).
        """
        if self.rank == 2:
            x, y = self.get_coordinate_lists()
            bbox = (min(x), max(x), min(y), max(y))
        elif self.rank == 3:
            x, y, z = self.get_coordinate_lists()
            bbox = (min(x), max(x), min(y), max(y), min(z), max(z))
        return bbox

    def print_vertices(self):
        """ Prints an enumerated list of indices. """
        for i, vertex in enumerate(self.vertices):
            print i, '\t', vertex

    def get_vertices(self):
        """ Return vertices as a list of tuples. """
        return np.array(self.vertices)

    def get_data(self, fields=None):
        """ Return data as an array, regardless of internal type. Optionally
        takes the keyword argument *fields*, which is an iterable listing the
        columns from the data dictionary to retrieve. """
        if hasattr(self.data, 'keys') and hasattr(self.data.values, '__call__'):
            if fields is not None:
                data = np.array([self.data[key] for key in fields])
            else:
                data = np.array(self.data.values())
        else:
            data = np.array(self.data)
        return data.T

    def get_coordinate_lists(self):
        """ Return X, Y, and Z lists. If self.rank == 2, Z will be
        zero-filled. """
        X = [i[0] for i in self.vertices]
        Y = [i[1] for i in self.vertices]
        if self.rank == 3:
            Z = [i[2] for i in self.vertices]
            return X, Y, Z
        else:
            return X, Y

    def shift(self, shift_vector):
        """ Shift feature by the amount given by a vector. Operation
        occurs in-place """
        if len(shift_vector) != self.rank:
            raise GGeoError('Shift vector length must equal geometry rank.')

        if self.rank == 2:
            f = lambda pt: (pt[0] + shift_vector[0], pt[1] + shift_vector[1])
        elif self.rank == 3:
            f = lambda pt: (pt[0] + shift_vector[0], pt[1] + shift_vector[1],
                            pt[2] + shift_vector[2])
        self.vertices = map(f, self.vertices)
        return

    def _matmult(self, A, x):
        """ Return Ax=b """
        b = []
        for a in A:
            b.append(sum([ai * xi for ai, xi in zip(a, x)]))
        return b

    def rotate2d(self, thetad, origin=(0, 0)):
        """ Rotate rank 2 Multipoint around *origin* counter-clockwise by
        *thetad* degrees. """
        # First, shift by the origin
        self.shift([-a for a in origin])

        # Multiply by a rotation matrix
        theta = thetad / 180.0 * math.pi
        R = ((math.cos(theta), -math.sin(theta)),
             (math.sin(theta), math.cos(theta)))
        rvertices = [self._matmult(R, x) for x in self.vertices]
        self.vertices = rvertices

        # Shift back
        self.shift(origin)
        return

    def _distance_to(self, pt):
        """ Calculate distance of each member point to an external point. """
        dist = lambda pts: np.sqrt((pts[0] - pts[1])**2)
        pta = np.array(pt.vertex)
        return map(dist, ((np.array(v) - pta) for v in self.vertices))

    def _subset(self, idxs):
        """ Return a subset defined by index in *idxs*. """
        subset = Multipoint([self.vertices[i] for i in idxs])
        if hasattr(self.data, 'keys'):
            ddict = {}
            for k in self.data:
                ddict[k] = [self.data[k][i] for i in idxs]
            subset.data = ddict
        else:
            subset.data = [self.data[i] for i in idxs]
        return subset

    def near(self, pt, radius):
        """ Return Multipoint of subset of member vertices that are within
        *radius* of *pt*.
        """
        distances = self._distance_to(pt)
        nearidx = [i for i,d in enumerate(distances) if d < radius]
        subset = self._subset(nearidx)
        return subset

    def nearest_to(self, pt):
        """ Returns the internal point that is nearest to pt (Point class).

        Warning: If two points are equidistant, only one will be returned.
        """
        distances = self._distance_to(pt)
        idx = distances.index(min(distances))
        return self._subset(list(idx))

    def get_extents(self):
        """ Calculate a bounding box. """
        def gen_minmax(G):
            """ Get the min/max from a single pass through a generator. """
            mn = mx = G.next()
            for x in G:
                mn = min(mn, x)
                mx = max(mx, x)
            return mn, mx
        # Get the min/max for a generator defined for each dimension
        return map(gen_minmax,
                    map(lambda i: (c[i] for c in self.vertices),
                        range(self.rank)))

    # This code should compute the convex hull of the points and then test the
    # hull's combination space
    # Alternatively, calculate the eigenvectors, rotate, and cherrypick the
    # points
    #def max_dimension(self):
    #    """ Return the two points in the Multipoint that are furthest
    #    from each other. """
    #    dist = lambda xy0, xy1: math.sqrt((xy1[0]-xy0[0])**2 +
    #                                      (xy1[1]-xy0[1])**2)

    #    P = [(p0, p1) for p0 in self.vertices for p1 in self.vertices]
    #    D = map(dist, (p[0] for p in P), (p[1] for p in P))
    #    return P[D.index(max(D))]

    def to_xyfile(self, fnm, fields=None, delimiter=' ', header=None):
        """ Write data to a delimited ASCII table.

        fnm         :   filename to write to

        kwargs:
        fields      :   specify the fields to be written (default all)

        Additional kwargs are passed to `xyfile.write_xy`.
        """
        if False in (a is None for a in self.data):
            dat = np.hstack([self.get_vertices(), self.get_data(fields)])
        else:
            dat = self.get_vertices()
        xyfile.write_xy(dat, fnm, delimiter=delimiter, header=header)
        return

    def as_geojson(self, **kwargs):
        """ Print representation of internal data as a GeoJSON string.

        Parameters
        ----------
        crs : coordinate reference system
        crs_fmt : format of `crs`; may be one of ('epsg','ogc_crs_urn')
        bbox : an optional bounding box tuple in the form (w,e,s,n)
        """
        writer = geojson.GeoJSONWriter(self, **kwargs)
        return writer.print_json()

    def to_geojson(self, f, **kwargs):
        """ Write data as a GeoJSON string to a file-like object `f`.

        Parameters
        ----------
        f : file-like object to recieve the GeoJSON string

        *kwargs* include:
        crs : coordinate reference system
        crs_fmt : format of `crs`; may be one of ('epsg','ogc_crs_urn')
        bbox : an optional bounding box tuple in the form (w,e,s,n)
        """
        writer = geojson.GeoJSONWriter(self, **kwargs)
        writer.write_json(f)
        return writer

    def to_vtk(self, f, **kwargs):
        """ Write data to an ASCII VTK .vtp file. """
        vtk.mp2vtp(self, f, **kwargs)
        return


class ConnectedMultipoint(Multipoint):
    """ Class for Multipoints in which vertices are assumed to be connected. """

    def length(self, spherical=False):
        """ Returns the length of the line/boundary. """
        if spherical is True:
            raise NotImplementedError("Spherical metrics not implemented")
        points = [Point(i) for i in self.vertices]
        distances = [a.distance(b) for a, b in zip(points[:-1], points[1:])]
        return sum(distances)

    def segments(self):
        """ Returns an iterator of adjacent line segments. """
        return ((self.vertices[i], self.vertices[i+1])
                for i in range(len(self.vertices)-1))

    def nearest_on_boundary(self, pt):
        """ Returns the point on the Multipoint boundary that is nearest to pt
        (point class).

        Warning: If two points are equidistant, only one will be returned.
        """
        point_dist = map(_vecgeo.pt_nearest,
                                [pt.vertex for seg in self.segments()],
                                [seg[0] for seg in self.segments()],
                                [seg[1] for seg in self.segments()])
        distances = [i[1] for i in point_dist]
        return Point(point_dist[distances.index(min(distances))][0])


class Line(ConnectedMultipoint):
    """ This defines the polyline class, from which geographic line
    objects can be constructed. Line objects consist of joined,
    georeferenced line segments.
    """
    _geotype = "Line"

    #def __repr__(self):
    #    return 'Line(' + reduce(lambda a,b: str(a) + ' ' + str(b),
    #            self.vertices) + ')'

    def add_vertex(self, vertex):
        """ Add a vertex to self.vertices. """
        if isinstance(vertex, Point):
            if self.rank == 2:
                self.vertices.append((vertex.x, vertex.y))
            elif self.rank == 3:
                self.vertices.append((vertex.x, vertex.y, vertex.z))
            if self._datatype == vertex._datatype:
                if self._datatype == "dict-like":
                    for key in self.data:
                        self.data[key] += vertex.data[key]
                elif self._datatype == "list-like":
                    self.data += vertex.data
            else:
                raise GGeoError('Cannot add inconsistent data types')
        else:
            if self.rank == 2:
                self.vertices.append((vertex[0], vertex[1]))
            elif self.rank == 3:
                self.vertices.append((vertex[0], vertex[1], vertex[2]))

    def remove_vertex(self, index):
        """ Removes a vertex from the register by index. """
        self.vertices.pop(index)

    def extend(self, other):
        """ Combine two lines, provided that that the data formats are similar.
        """
        if self.rank == other.rank:
            if self._geotype == other._geotype:
                vertices = self.vertices + other.vertices
                if self._datatype == other._datatype:
                    if self._datatype == "dict-like":
                        data = {}
                        for k in set(self.data.keys()).intersection(set(other.data.keys())):
                            data[k] = self.data[k] + other.data[k]
                    elif self._datatype == "list-like":
                        data = self.data + other.data
                else:
                    raise GGeoError('Cannot add inconsistent data types')
            else:
                GGeoError('Cannot add inconsistent geometry types')
        else:
            GGeoError('Cannot add geometries with inconsistent rank')
        return Line(vertices, data=data)

    def distances(self):
        """ Returns the cumulative length of each segment, prefixed by zero. """
        d = [0.0]
        for i, vert in enumerate(self.vertices[1:]):
            d_ = math.sqrt(sum([(a-b)**2 for a,b in zip(self.vertices[i], vert)]))
            d.append(d_ + d[i])
        return d

    def displacement(self):
        """ Returns the distance between the first and last vertex. """
        return Point(self.vertices[0]).distance(Point(self.vertices[-1]))

    def intersects(self, other):
        """ Return whether an intersection exists with another geometry. """
        interxbool = (_vecgeo.intersects(a[0][0], a[1][0], b[0][0], b[1][0],
                                         a[0][1], a[1][1], b[0][1], b[1][1])
                    for a in self.segments() for b in other.segments())
        if self._bbox_overlap(other) and (True in interxbool):
            return True
        else:
            return False

    def intersections(self, other):
        """ Return the intersections with another geometry. """
        interx = (_vecgeo.intersections(a[0][0], a[1][0], b[0][0], b[1][0],
                                        a[0][1], a[1][1], b[0][1], b[1][1])
                    for a in self.segments() for b in other.segments())
        return filter(lambda a: np.nan not in a, interx)

    def to_polygon(self):
        """ Returns a polygon. """
        return Polygon(self.vertices)

    def to_shapely(self):
        """ Returns a Shapely LineString instance. """
        try:
            if self.rank == 2:
                return geometry.LineString([(v[0], v[1]) for v in self.vertices])
            elif self.rank == 3:
                return geometry.LineString([(v[0], v[1], v[2]) for v in self.vertices])
        except NameError:
            raise GuppyError('Shapely module not available\n')


class Polygon(ConnectedMultipoint):
    """ This defines the polygon class, from which geographic
    polygons objects can be created. Polygon objects consist of
    point nodes enclosing an area.
    """
    _geotype = "Polygon"
    subs = []

    def __init__(self, vertices, **kwargs):
        Multipoint.__init__(self, vertices, **kwargs)
        if vertices[0] != vertices[-1]:
            self.vertices.append(vertices[0])
        self.subs = kwargs.get('subs', [])
        return

    #def __repr__(self):
    #    return 'Polygon(' + reduce(lambda a,b: str(a) + ' ' + str(b),
    #            self.vertices) + ')'

    def perimeter(self):
        """ Return the perimeter of the polygon. If there are sub-polygons,
        their perimeters are added recursively. """
        return self.length() + sum([p.perimeter() for p in self.subs])

    def area(self):
        """ Return the two-dimensional area of the polygon. If there are
        sub-polygons, their areas are subtracted. """
        a = 0.0
        for i in range(len(self.vertices)-1):
            a += 0.5 * abs((self.vertices[i][0] + self.vertices[i+1][0])
                         * (self.vertices[i][1] - self.vertices[i+1][1]))
        return a - sum(map(lambda p: p.area(), self.subs))

    def contains(self, pt):
        """ Returns True if pt is inside or on the boundary of the
        polygon, and False otherwise.
        """
        def possible(pt, v1, v2):
            """ Quickly assess potential for an intersection with an x+
            pointing ray. """
            x = pt.vertex[0]
            y = pt.vertex[1]
            if ( ((y > v1[1]) is not (y > v2[1]))
            and ((x < v1[0]) or (x < v2[0])) ):
                return True
            else:
                return False

        # Find how many boundaries a ray pointing out from point crosses
        bool2int = lambda tf: (tf and 1 or 0)
        rvertices = deque(self.vertices)
        rvertices.rotate(1)
        segments = [(v1, v2) for v1, v2 in zip(self.vertices, rvertices)
                    if possible(pt, v1, v2)]

        n_intersect = sum([bool2int(
            isinstance(ray_intersection(pt.vertex, seg[0], seg[1]), tuple))
            for seg in segments])

        if n_intersect % 2 == 1:    # If odd, point is inside so check subpolys
            if True not in (p.contains(pt) for p in self.subs):
                return True
        return False                # Point was outside or was in a subpoly

    def to_polyline(self):
        """ Returns a self-closing polyline. Discards sub-polygons. """
        return Line(self.vertices)

    def to_shapely(self):
        """ Returns a Shapely Polygon instance. """
        try:
            shp = geometry.Polygon(self.vertices,
                                   interiors=[p.vertices for p in self.subs])
        except NameError:
            raise ImportError('Shapely module did not import\n')
        return shp


class GuppyError(Exception):
    """ Base class for guppy module errors. """
    def __init__(self, message=''):
        self.message = message
    def __str__(self):
        return self.message


class GInitError(GuppyError):
    """ Exception to raise when a guppy object fails to initialize. """
    def __init__(self, message=''):
        self.message = message


class GUnitError(GuppyError):
    """ Exception to raise there is a projected unit problem. """
    def __init__(self, message=''):
        self.message = message


class GGeoError(GuppyError):
    """ Exception to raise when a guppy object attempts an invalid transform. """
    def __init__(self, message=''):
        self.message = message


def ray_intersection(pt, endpt1, endpt2, direction=0.0):
    """ Determines whether a ray intersects a line segment. If yes,
    returns the point of intersection. If no, return None. Input
    "points" should be tuples or similar. Input direction is in
    radians, and defines the ray path from pt.
    """
    m_ray = math.tan(direction)
    if endpt2[0] != endpt1[0]:
        m_lin = float(endpt2[1] - endpt1[1]) / float(endpt2[0] - endpt1[0])
        if m_ray == m_lin:      # Lines are parallel
            return
        else:
            x_int = ( (m_ray * pt[0] - m_lin * endpt1[0] - pt[1] + endpt1[1])
                / (m_ray - m_lin) )

        # Test that y_int is within segment and ray points toward segment
        if ( (x_int >= endpt1[0]) is not (x_int >= endpt2[0]) and
            (x_int-pt[0] > 0) is (math.cos(direction) > 0) ):
            y_int = ( (m_ray * m_lin * pt[0] - m_ray * m_lin * endpt1[0]
                + m_ray * endpt1[1] - m_lin * pt[1]) / (m_ray - m_lin) )
            return (x_int, y_int)
        else:
            return

    else:       # Line segment is vertical
        if direction % math.pi/2. == 0.0 and direction != 0.0:
            # Lines are parallel
            return
        x_int = float(endpt1[0])
        y_int = (x_int - pt[0]) * m_ray + pt[1]
        # Test that y_int is within segment and ray points toward segment
        if ( (y_int >= endpt1[1]) is not (y_int >= endpt2[1]) and
            (x_int-pt[0] > 0) is (math.cos(direction) > 0) ):
            return (x_int, y_int)
        else:
            return


def distance(pntlist, angular_unit="deg", space_unit="km", method="vicenty"):
    """ Computes the great circle distance between n point pairs on a
    sphere. Returns a list of length (n-1)

    [pntlist] contains a list of point objects

    [angular_unit] may be "deg" (default) or "rad".

    [space_unit] may be "km" (kilometers, default), "m" (meters), "mi"
    (miles), "ft" (feet), or "nm" (nautical miles).

    [method] may be "vicenty" (default) or "haversine". The Haversine
    method is roughly 20% faster, but may yield rounding errors when
    coordinates are antipodal.
    """

    radius = 6371.

    if angular_unit == "deg":
        xpts = [i.x * 3.14159 / 180. for i in pntlist]
        ypts = [i.y * 3.14159 / 180. for i in pntlist]
    elif angular_unit == "rad":
        xpts = [i.x for i in pntlist]
        ypts = [i.y for i in pntlist]
    else:
        raise GUnitError("Angular unit unrecognized")
        return None

    distances = []

    for i in xrange(len(pntlist)-1):

        x1 = xpts[i]
        x2 = xpts[i+1]
        y1 = ypts[i]
        y2 = ypts[i+1]
        dx = x2 - x1
        dy = y2 - y1
        if method == "haversine":
            try:
                distance = 2 * radius * math.asin(math.sqrt((math.sin(dy /
                    2.))**2 + math.cos(y1) * math.cos(y2) *
                    (math.sin(dx / 2.))**2))
            except GGeoError:
                traceback.print_exc()
        elif method == "vicenty":
            try:
                a = math.sqrt((math.cos(y2) * math.sin(dx))**2 +
                    (math.cos(y1) * math.sin(y2) - math.sin(y1) *
                    math.cos(y2) * math.cos(dx))**2)
                b = (math.sin(y1) * math.sin(y2) + math.cos(y1) *
                    math.cos(y2) * math.cos(dx))
                distance = radius * math.atan2(a, b)
            except ZeroDivisionError:
                raise GGeoError("Zero in denominator")
                return None
            except:
                traceback.print_exc()
        else:
            raise Exception("Distance method unrecognized")
            return None

        distances.append(distance)

    if space_unit == "km": pass
    elif space_unit == "m": distances = [i * 1000. for i in distances]
    elif space_unit == "mi": distances = [i * 0.6213712 for i in distances]
    elif space_unit == "ft": distances = [i * 3280.840 for i in distances]
    elif space_unit == "nm": distances = [i * 0.5399568 for i in distances]
    else:
        print "Space unit unrecognized"
        return None

    return distances


def walk(start_pt, distance, bearing, azimuth=0.0, spherical=False):
    """ Returns the point reached when moving in a given direction for
    a given distance from a specified starting location.

        start_pt (point): starting location
        distance (float): distance to walk
        bearing (float): horizontal walk direction in radians
        azimuth (float): vertical walk direction in radians

        [NOT IMPLEMENTED]
        spherical (bool): use a spherical reference surface (globe)
    """
    if azimuth != 0.0:
        distxy = distance * math.sin(azimuth)
        dz = distance * math.cos(azimuth)
    else:
        distxy = distance
        dz = 0.0
    dx = distxy * math.sin(bearing)
    dy = distxy * math.cos(bearing)

    if start_pt.rank == 3:
        return Point((start_pt.x+dx, start_pt.y+dy, start_pt.z+dz))
    elif start_pt.rank == 2:
        if azimuth != 0:
            sys.stderr.write("Warning: start_pt has rank 2 but azimuth is "
                             "nonzero\n")
        return Point((start_pt.x+dx, start_pt.y+dy))


def sortby(A, B):
    """ Sort a list A by the values in an ordered list B. """
    if len(A) != len(B):
        raise GGeoError("A and B must be of the same length")
    comb = zip(B,A)
    comb.sort()
    return [i[1] for i in comb]


def tighten(X, Z):
    """ Return a list of corrected measurements from observations of
    topography across a cross-section. The inputs are equal length
    lists of observed distance and elevation.

    Usage scenario: While surveying transects using a tape, the tape
    is anchored to the topographical surface, rather than directly
    between same-height endpoints.
    """
    if len(X) != len(Z):
        raise GGeoError('Observation vectors must have equal length')

    DZ = [z2-z1 for z2,z1 in zip(Z[1:], Z[:-1])]
    DX = [x2-x1 for x2,x1 in zip(X[1:], X[:-1])]

    DXt = [math.sqrt(x*x-z*z) for x,z in zip(DX, DZ)]

    Xt = map(lambda i: sum(DXt[:i]) + X[0], range(len(DX)))

    return zip(Xt, Z)

