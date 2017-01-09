"""
Module for partitioning of grids based on various methods.

Intended support is by Cartesian indexing, and METIS-based.

"""

import pymetis
import numpy as np

from core.grids import structured
from utils import permutations

def partition_metis(g, num_part):
    """
    Partition a grid using metis.

    This function requires that pymetis is installed, as can be done by

        pip install pymetis

    This will install metis itself in addition to the python bindings. There
    are other python bindings for metis as well, but pymetis has done the job
    until now.

    Parameters:
        g: core.grids.grid: To be partitioned. Only the cell_face attribute is
            used
        num_part (int): Number of partitions.

    Returns:
        np.array (size:g.num_cells): Partition vector, one number in
            [0, num_part) for each cell.

    """

    # Create a copy of the cell-face relation, so that we can modify it at will
    cell_face = g.cell_faces.copy()

    # Direction of normal vector does not matter here, only 0s and 1s
    cell_faces.data = np.abs(cell_faces.data)

    # Find connection between cells via the cell-face map
    c2c = cell_faces.transpose() * cell_faces
    # Only care about absolute values
    c2c.data = np.clip(c2c.data, 0, 1)

    # Convert the cells into the format required by pymetis
    adjacency_list = [c2c.getrow(i).indices for i in range(c2c.shape[0])]
    # Call pymetis
    part = pymetis.part_graph(10, adjacency=adjacency_list)

    # The meaning of the first number returned by pymetis is not clear (poor
    # documentation), only return the partitioning.
    return np.array(part[1])


def partition_structured(g, coarse_dims=None, num_part=None):
    """
    Define a partitioning of a grid based on logical Cartesian indexing.

    The grid should have a field cart_dims, describing the Cartesian dimensions
    of the grid.

    The coarse grid can be specified either by its Cartesian dimensions
    (parameter coarse_dims), or by its total number of partitions (num_part).
    In the latter case, a partitioning will be inferred from the fine-scale
    Cartesian dimensions, in a way that gives roughly the same number of cells
    in each direction.

    Parameters:
        g: core.grids.grid: To be partitioned. Only the cell_face attribute is
            used
        coarse_dims (np.array): Cartesian dimensions of the coarse grids.
        num_part (int): Number of partitions.

    Returns:
        np.array (size:g.num_cells): Partition vector, one number in
            [0, num_part) for each cell.

    Raises:
        Value error if both coarse_dims and num_part are None.

    """


    if (coarse_dims is None) and (num_part is None):
        raise ValueError('Either coarse dimensions or number of coarse cells \
                         must be specified')

    nd = g.dim
    fine_dims = g.cart_dims
    # Number of fine cells per coarse cell
    fine_per_coarse = np.floor(fine_dims / coarse_dims)

    # First define the coarse index for the individual dimensions.
    ind = []
    for i in range(nd):
        # Fine indexes where the coarse index will increase
        incr_ind = np.arange(0, fine_dims[i], fine_per_coarse[i], dtype='i')

        # If the coarse dimension is not an exact multiple of the fine, there
        # will be an extra cell in this dimension. Remove this.
        if incr_ind.size > coarse_dims[i]:
            incr_ind = incr_ind[:-1]

        # Array for coarse index of fine cells
        loc_ind = np.zeros(fine_dims[i])
        # The index will increase by one
        loc_ind[incr_ind] += 1
        # A cumulative sum now gives the index, but subtract by one to be 
        # 0-offset
        ind.append(np.cumsum(loc_ind) - 1)

    # Then combine the indexes. In 2D meshgrid does the job, in 3D it turned
    # out that some acrobatics was necessary to get the right ordering of the
    # cells.
    if nd == 2:
        xi, yi = np.meshgrid(ind[0], ind[1])
        # y-index jumps in steps of the number of coarse x-cells
        glob_dims = (xi + yi * coarse_dims[0]).ravel('C')
    elif nd == 3:
        xi, yi, zi = np.meshgrid(ind[0], ind[1], ind[2])
        # Combine indices, with appropriate jumps in y and z counting
        glob_dims = (xi + yi * coarse_dims[0]
                   + zi * np.prod(coarse_dims[:2]))
        # This just happened to work, may be logical, but the documentanion of
        # np.meshgrid was hard to comprehend.
        glob_dims = np.swapaxes(np.swapaxes(glob_dims, 1, 2), 0, 1).ravel('C')

    # Return an int
    return glob_dims.astype('int')


def determine_coarse_dimensions(target, fine_size):
    """
    For a logically Cartesian grid determine a coarse partitioning based on a
    target number of coarse cells.

    The target size in general will not be a product of the possible grid
    dimensions (it may be a prime, or it may be outside the bounds [1,
    fine_size]. For concreteness, we seek to have roughly the same number of
    cells in each directions (given by the Nd-root of the target). If this
    requires more coarse cells in a dimension than there are fine cells there,
    the coarse size is set equal to the fine, and the remaining cells are
    distributed to the other dimensions.

    Parameters:
        target (int): Target number of coarse cells.
        fine_size (np.ndarray): Number of fine-scale cell in eac dimension

    Returns:
        np.ndarray: Coarse dimension sizes.

    Raises:
        ValueError if the while-loop runs more iterations than the number of
            dimensions. This should not happen, in practice it means there is
            bug.

    """

    # The algorithm may be unstable for values outside the relevant bounds
    target = np.maximum(1, np.minimum(target, fine_size.prod()))

    nd = fine_size.size

    # Array to store optimal values. Set the default value to one, this avoids
    # interfering with target_now below.
    optimum = np.ones(nd)
    found = np.zeros(nd, dtype=np.bool)

    # Counter for number of iterations. Should be unnecessary, remove when the
    # code is trusted.
    it_counter = 0

    # Loop until all dimensions have been assigned a number of cells.
    while not np.all(found) and it_counter <= nd:

        it_counter += 1

        # Remaining cells to deal with
        target_now = target / optimum.prod()

        # The simplest option is to take the Nd-root of the target number. This
        # will generally not give integers, and we will therefore settle for the
        # combination of rounding up and down which brings us closest to the
        # target.
        # There should be at least one coarse cell in each dimension, and at
        # maximum as many cells as on the fine scale.
        s_num = np.power(target_now, 1/(nd - found.sum()))
        s_low = np.maximum(np.ones(nd), np.floor(s_num))
        s_high = np.minimum(fine_size, np.ceil(s_num))

        # Find dimensions where we have hit the ceiling
        hit_ceil = np.squeeze(np.argwhere(np.logical_and(s_high == fine_size,
                                                         ~found)))
        # These have a bound, and will have their leeway removed
        optimum[hit_ceil] = s_high[hit_ceil]
        found[hit_ceil] = True

        # If the ceiling was hit in some dimension, we have to start over
        # again.
        if np.any(hit_ceil):
            continue

        # There is no room for variations in found cells
        s_low[found] = optimum[found]
        s_high[found] = optimum[found]

        # Array for storing the combinations.
        coarse_size = np.vstack((s_low, s_high))
        # The closest we've been to hit the target size. Set this to an
        # unrealistically high number
        dist = fine_size.prod()

        # Loop over all combinations of rounding up and down, and test if we
        # are closer to the target number.
        for perm in permutations.multinary_permutations(2, nd):
            size_now = np.zeros(nd)
            for i, bit in enumerate(perm):
                size_now[i] = coarse_size[bit, i]
            if np.abs(target - size_now.prod()) < dist:
                dist = target - size_now.prod()
                optimum = size_now

        # All dimensions that may hit the ceiling have been found, and we have
        # the optimum solution. Declare victory and return home.
        found[:] = True

    if it_counter > nd:
        raise ValueError('Maximum number of iterations exceeded. There is a \
                         bug somewhere.')

    return optimum

