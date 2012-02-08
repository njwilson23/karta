""" Convenience functions for XY(Z) tables. """

import numpy as np

def load_xy(fnm, delimiter=","):
    """ Load a flowline file and return a size-2 array of coordinates. """
    with open(fnm) as f:
        coords = [[float(j) for j in i.split(delimiter)] for i in f.readlines()]
    return np.array(coords)



def xyz2array_reg(X, Y, Z):
    """ Return an array from X,Y,Z vectors, assuming gridding is
    regular. """
    xmin = min(X)
    xmax = max(X)
    ymin = min(Y)
    ymax = max(Y)

    nx = sum([y==ymin for y in Y])
    ny = sum([x==xmin for x in X])

    XYZ = [(x,y,z) for x,y,z in zip(X,Y,Z)]
    XYZ.sort(key=lambda a: a[1])
    XYZ.sort(key=lambda a: a[0])
    Zs = [a[2] for a in XYZ]

    A = np.zeros([ny, nx])
    for i in range(ny):
        A[i,:] = Zs[i*nx:(i+1)*nx]

    return A

def array2xyz(A, X, Y):
    """ There are a few occasions when an XYZ list is the proper data
    format. This function converts from an array *A* with coordinates
    defined by *X* and *Y* to a list of (x,y,z) tuples.
    """
    xyz = []
    m, n = A.shape
    for j in range(n):
        for i in range (m):
            xyz.append( (X[i], Y[j], A[i,j]) )
    return xyz

