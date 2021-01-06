""" Ad representation of grid-related quantities needed to write equations. The classes
defined here are mainly wrappers that constructs Ad matrices based on grid information.

"""
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import scipy.sparse as sps

import porepy as pp

from .operators import Matrix, MergedOperator, Operator

__all__ = [
    "MortarProjections",
    "Divergence",
    "BoundaryCondition",
    "Trace",
    "SubdomainProjections",
]


class SubdomainProjections(Operator):
    """Wrapper class for generating projection to and from subdomains.

    One use case in when variables are defined on only some of subdomains.

    The class should be used through the methods (cell, face)_(projection,restriction)

    """

    def __init__(
        self,
        grids: Optional[List[pp.Grid]] = None,
        gb: Optional[List[pp.Grid]] = None,
        nd: int = 1,
    ) -> None:
        """Construct sudomain restrictions and prolongations for a set of subdomains.

        The projections will be ordered according to the ordering in grids, or the order
        of the GridBucket iteration over grids. Iit is critical that the same ordering
        is used by other operators.

        Parameters:
            grids (List of pp.Grid): List of grids. The order of the grids in the list
                sets the ordering of the subdomain projections.
            gb (pp.GridBucket): Used if grid list is not provided. The order of the
                grids is set according to iteration over the GridBucket nodes.
            is_scalar (bool, optional): If true, projections are constructed for scalar
                quantities.

        """
        grids = _grid_list(grids, gb)

        self._nd = nd
        self._is_scalar: bool = nd == 1

        self._num_grids: int = len(grids)

        self._cell_projection, self._face_projection = _subgrid_projections(
            grids, self._nd
        )

    def cell_restriction(self, grids: Union[pp.Grid, List[pp.Grid]]) -> Matrix:
        """Construct restrictions from global to subdomain cell quantities.

        Parameters:
            grids (pp.Grid or List of pp.Grids): One or several subdomains to which
                the projection should apply.

        Returns:
            pp.ad.Matrix: Matrix operator (in the Ad sense) that represent the
                projection.

        """
        if isinstance(grids, pp.Grid):
            return pp.ad.Matrix(self._cell_projection[grids].T)
        elif isinstance(grids, list):
            # A key error will be raised if a grid in g is not known to
            # self._cell_projection
            return pp.ad.Matrix(
                sps.bmat([[self._cell_projection[g].T] for g in grids]).tocsr()
            )
        else:
            raise ValueError("Argument should be a grid or a list of grids")

    def cell_prolongation(self, grids: Union[pp.Grid, List[pp.Grid]]) -> Matrix:
        """Construct prolongation from subdomain to global cell quantities.

        Parameters:
            grids (pp.Grid or List of pp.Grids): One or several subdomains to which
                the prolongation should apply.

        Returns:
            pp.ad.Matrix: Matrix operator (in the Ad sense) that represent the
                prolongation.

        """
        if isinstance(grids, pp.Grid):
            return pp.ad.Matrix(self._cell_projection[grids])
        elif isinstance(grids, list):
            # A key error will be raised if a grid in g is not known to self._cell_projection
            return pp.ad.Matrix(
                sps.bmat([[self._cell_projection[g] for g in grids]]).tocsr()
            )
        else:
            raise ValueError("Argument should be a grid or a list of grids")

    def face_restriction(self, grids: Union[pp.Grid, List[pp.Grid]]) -> Matrix:
        """Construct restrictions from global to subdomain face quantities.

        Parameters:
            grids (pp.Grid or List of pp.Grids): One or several subdomains to which
                the projection should apply.

        Returns:
            pp.ad.Matrix: Matrix operator (in the Ad sense) that represent the
                projection.

        """
        if isinstance(grids, pp.Grid):
            return pp.ad.Matrix(self._face_projection[grids].T)
        elif isinstance(grids, list):
            # A key error will be raised if a grid in g is not known to self._cell_projection
            return pp.ad.Matrix(
                sps.bmat([[self._face_projection[g].T] for g in grids]).tocsr()
            )
        else:
            raise ValueError("Argument should be a grid or a list of grids")

    def face_prolongation(self, grids: Union[pp.Grid, List[pp.Grid]]) -> Matrix:
        """Construct prolongation from subdomain to global face quantities.

        Parameters:
            grids (pp.Grid or List of pp.Grids): One or several subdomains to which
                the prolongation should apply.

        Returns:
            pp.ad.Matrix: Matrix operator (in the Ad sense) that represent the
                prolongation.

        """
        if isinstance(grids, pp.Grid):
            return pp.ad.Matrix(self._face_projection[grids])
        elif isinstance(grids, list):
            # A key error will be raised if a grid in g is not known to self._cell_projection
            return pp.ad.Matrix(
                sps.bmat([[self._face_projection[g] for g in grids]]).tocsr()
            )
        else:
            raise ValueError("Argument should be a grid or a list of grids")

    def __repr__(self) -> str:
        s = (
            f"Restriction and prolongation operators for {self._num_grids} grids\n"
            f"Aimed at variables with dimension {self._nd}\n"
        )
        return s


class MortarProjections(Operator):
    """Wrapper class to generate projections to and from MortarGrids.

    Attributes:
        mortar_to_primary_int (pp.ad.Matrix): Matrix of projections from the mortar
            grid to the primary grid. Intended for extensive quantities (so fluxes).
            Represented as an Ad Matrix operator.
        mortar_to_primary_avg (pp.ad.Matrix): Matrix of projections from the mortar
            grid to the primary grid. Intended for intensive quantities (so pressures).
            Represented as an Ad Matrix operator.
        primary_to_mortar_int (pp.ad.Matrix): Matrix of projections from the primary
            grid to the mortar grid. Intended for extensive quantities (so fluxes).
            Represented as an Ad Matrix operator.
        primary_to_mortar_avg (pp.ad.Matrix): Matrix of projections from the primary
            grid to the mortar grid. Intended for intensive quantities (so pressures).
            Represented as an Ad Matrix operator.
        mortar_to_secondary_int (pp.ad.Matrix): Matrix of projections from the mortar
            grid to the secondary grid. Intended for extensive quantities (so fluxes).
            Represented as an Ad Matrix operator.
        mortar_to_secondary_avg (pp.ad.Matrix): Matrix of projections from the mortar
            grid to the secondary grid. Intended for intensive quantities (so pressures).
            Represented as an Ad Matrix operator.
        secondary_to_mortar_int (pp.ad.Matrix): Matrix of projections from the secondary
            grid to the mortar grid. Intended for extensive quantities (so fluxes).
            Represented as an Ad Matrix operator.
        secondary_to_mortar_avg (pp.ad.Matrix): Matrix of projections from the secondary
            grid to the mortar grid. Intended for intensive quantities (so pressures).
            Represented as an Ad Matrix operator.
        sign_of_mortar_sides (pp.Ad.Matrix): Matrix represenation that assigns signs
            to two mortar sides. Needed to implement a jump operator in contact
            mechanics.

    """

    def __init__(
        self,
        grids: Optional[List[pp.Grid]] = None,
        gb: pp.GridBucket = None,
        edges: Optional[List[Tuple[pp.Grid, pp.Grid]]] = None,
        nd: int = 1,
    ) -> None:
        """Construct mortar projection object.

        The projections will be ordered according to the ordering in grids, or the order
        of the GridBucket iteration over grids. Iit is critical that the same ordering
        is used by other operators.

        Parameters:
            grids (List of pp.Grid, optional): List of grids for which the projections
                should apply. If not provided, all grids in gb will be used. The order
                 of the grids in the list sets the ordering of the subdomain projections.
            gb (pp.GridBucket): Mixed-dimensional grid.
            edges (List of edges, optional): List of edges for which the projections
                should apply. If not provided, all grids in gb will be used. The order
                 of the grids in the list sets the ordering of the subdomain projections.
            nd (int, optional): Dimension of the quantities to be projected.

        """
        grids = _grid_list(grids, gb)
        if edges is None:
            edges = [e for e, _ in gb.edges()]

        self._num_edges: int = len(edges)
        self._nd: int = nd

        ## Initialize projections

        cell_projection, face_projection = _subgrid_projections(grids, self._nd)

        # sparse blocks are slow; it should be possible to do a right multiplication
        # of local-to-global mortar indices instead of the block.

        # Data structures for constructing the projection operators
        mortar_to_primary_int, mortar_to_primary_avg = [], []
        primary_to_mortar_int, primary_to_mortar_avg = [], []

        mortar_to_secondary_int, mortar_to_secondary_avg = [], []
        secondary_to_mortar_int, secondary_to_mortar_avg = [], []

        # The goal is to construct global projections between grids and mortar grids.
        # The construction takes two stages, and is different for projections to and
        # from the mortar grid:
        # For projections from the mortar grid, a mapping is first made from local
        # mortar numbering global grid ordering. In the second stage, the mappings from
        # mortar are stacked to make a global mapping.
        # Projections to the mortar grid are made by first defining projections from
        # global grid numbering to local mortar grids, and then stack the latter.

        for e in edges:
            g_primary, g_secondary = e
            mg: pp.MortarGrid = gb.edge_props(e, "mortar_grid")
            if (g_primary.dim != mg.dim + 1) or g_secondary.dim != mg.dim:
                # This will correspond to DD of sorts; we could handle this
                # by using cell_projections for g_primary and/or
                # face_projection for g_secondary, depending on the exact
                # configuration
                raise NotImplementedError("Non-standard interface.")

            # Projections to primary
            mortar_to_primary_int.append(
                face_projection[g_primary] * mg.mortar_to_primary_int(nd)
            )
            mortar_to_primary_avg.append(
                face_projection[g_primary] * mg.mortar_to_primary_avg(nd)
            )

            # Projections from primary
            primary_to_mortar_int.append(
                mg.primary_to_mortar_int(nd) * face_projection[g_primary].T
            )
            primary_to_mortar_avg.append(
                mg.primary_to_mortar_avg(nd) * face_projection[g_primary].T
            )

            mortar_to_secondary_int.append(
                cell_projection[g_secondary] * mg.mortar_to_secondary_int(nd)
            )
            mortar_to_secondary_avg.append(
                cell_projection[g_secondary] * mg.mortar_to_secondary_avg(nd)
            )

            secondary_to_mortar_int.append(
                mg.secondary_to_mortar_int(nd) * cell_projection[g_secondary].T
            )
            secondary_to_mortar_avg.append(
                mg.secondary_to_mortar_avg(nd) * cell_projection[g_secondary].T
            )

        # Stack mappings from the mortar horizontally.
        # The projections are wrapped by a pp.ad.Matrix to be compatible with the
        # requirements for processing of Ad operators.
        self.mortar_to_primary_int = Matrix(sps.bmat([mortar_to_primary_int]).tocsr())
        self.mortar_to_primary_avg = Matrix(sps.bmat([mortar_to_primary_avg]).tocsr())
        self.mortar_to_secondary_int = Matrix(
            sps.bmat([mortar_to_secondary_int]).tocsr()
        )
        self.mortar_to_secondary_avg = Matrix(
            sps.bmat([mortar_to_secondary_avg]).tocsr()
        )

        # Vertical stacking of the projections
        self.primary_to_mortar_int = Matrix(
            sps.bmat([[m] for m in primary_to_mortar_int]).tocsr()
        )
        self.primary_to_mortar_avg = Matrix(
            sps.bmat([[m] for m in primary_to_mortar_avg]).tocsr()
        )
        self.secondary_to_mortar_int = Matrix(
            sps.bmat([[m] for m in secondary_to_mortar_int]).tocsr()
        )
        self.secondary_to_mortar_avg = Matrix(
            sps.bmat([[m] for m in secondary_to_mortar_avg]).tocsr()
        )

        # Also generate a merged version of MortarGrid.sign_of_mortar_sides:
        mats = []
        for e in edges:
            mg = gb.edge_props(e, "mortar_grid")
            mats.append(mg.sign_of_mortar_sides(nd))
        self.sign_of_mortar_sides = Matrix(sps.block_diag(mats))

    def __repr__(self) -> str:
        s = (
            f"Mortar projection for {self._num_edges} interfaces\n"
            f"Aimed at variables with dimension {self._nd}\n"
            f"Projections to primary have dimensions {self.mortar_to_primary_avg.shape}\n"
            f"Projections to secondary have dimensions {self.mortar_to_secondary_avg.shape}\n"
        )
        return s


class Trace(MergedOperator):
    """Wrapper class for Ad representations of trace operators and their inverse,
    that is, mappings between grid cells and faces.

    NOTE: The mapping will hit both boundary and interior faces, so the values
    to be mapped should be carefully filtered (e.g. by combining it with a
    mortar mapping).

    The mapping does not alter signs of variables, that is, the direction
    of face normal vectors is not accounted for.

    Attributes:
        trace (pp.ad.Matrix): Matrix of trace projections from cells to faces.
        inv_trace (pp.ad.Matrix): Matrix of trace projections from faces to cells.

    """

    def __init__(
        self,
        grids: Optional[List[pp.Grid]] = None,
        gb: Optional[List[pp.Grid]] = None,
        nd: int = 1,
    ):
        """Construct trace operators and their inverse for a given set of subdomains.

        The operators will be ordered according to the ordering in grids, or the order
        of the GridBucket iteration over grids. Iit is critical that the same ordering
        is used by other operators.

        Parameters:
            grids (List of pp.Grid): List of grids. The order of the grids in the list
                sets the ordering of the trace operators.
            gb (pp.GridBucket): Used if grid list is not provided. The order of the
                grids is set according to iteration over the GridBucket nodes.
            is_scalar (bool, optional): If true, trace operators are constructed for
                scalar quantities.

        """

        grids = _grid_list(grids, gb)

        self._nd: int = nd
        self._is_scalar: bool = nd == 1
        self._num_grids: int = len(grids)

        cell_projections, face_projections = _subgrid_projections(grids, self._nd)

        trace: sps.spmatrix = []
        inv_trace: sps.spmatrix = []

        for g in grids:
            if self._is_scalar:

                # TEMPORARY CONSTRUCT: Use the divergence operator as a trace.
                # It would be better to define a dedicated function for this,
                # perhaps in the grid itself.
                div = np.abs(pp.fvutils.scalar_divergence(g))

                # Restrict global cell values to the local grid, use transpose of div
                # to map cell values to faces.
                trace.append(div.T * cell_projections[g].T)
                # Similarly restrict a global face quantity to the local grid, then
                # map back to cells.
                inv_trace.append(div * face_projections[g].T)
            else:
                raise NotImplementedError("kronecker")

        # Stack both trace and inv_trace vertically to make them into mappings to
        # global quantities.
        # Wrap the stacked matrices into an Ad object
        self.trace = Matrix(sps.bmat([[m] for m in trace]).tocsr())
        self.inv_trace = Matrix(sps.bmat([[m] for m in inv_trace]).tocsr())

    def __repr__(self) -> str:
        s = (
            f"Trace operator for {self._num_grids} grids\n"
            f"Aimed at variables with dimension {self._nd}\n"
            f"Projection from grid to mortar has dimensions {self.trace}\n"
        )
        return s


class Divergence(MergedOperator):
    """Wrapper class for Ad representations of divergence operators."""

    def __init__(
        self,
        grids: Optional[List[pp.Grid]] = None,
        gb: Optional[pp.GridBucket] = None,
        is_scalar: bool = True,
    ):
        """Construct divergence operators for a set of subdomains.

        The operators will be ordered according to the ordering in grids, or the order
        of the GridBucket iteration over grids. Iit is critical that the same ordering
        is used by other operators.

        IMPLEMENTATION NOTE: Only scalar quantities so far; vector operators will be
        added in due course.

        Parameters:
            grids (List of pp.Grid): List of grids. The order of the grids in the list
                sets the ordering of the divergence operators.
            gb (pp.GridBucket): Used if grid list is not provided. The order of the
                grids is set according to iteration over the GridBucket nodes.
            is_scalar (bool, optional): If true, divergence operators are constructed
                for scalar quantities.

        """

        self._g: List[pp.Grid] = _grid_list(grids, gb)

        self.scalar = is_scalar
        self._set_tree(None)

    def __repr__(self) -> str:
        if self.scalar:
            s = "Scalar "
        else:
            s = "Vector "

        s += f"divergence defined on {len(self.g)} grids\n"

        nf = 0
        nc = 0
        for g in self._g:
            if self.scalar:
                nf += g.num_faces
                nc += g.num_cells
            else:
                # EK: the notion of vector divergence for grids of co-dimension >= 1
                # is not clear, but we ignore this here.
                nf += g.num_faces * g.dim
                nc += g.num_cells * g.dim

        s += f"The total size of the matrix is ({nc}, {nf})\n"

        return s

    def parse(self, gb: pp.GridBucket) -> sps.spmatrix:
        """Convert the Ad expression into a divergence operators on all relevant grids,
        represented as a sparse block matrix.

        Pameteres:
            gb (pp.GridBucket): Not used, but needed for compatibility with the general
                parsing method for Operators.

        Returns:
            sps.spmatrix: Block matrix representation of a divergence operator on
                multiple grids.

        """
        if self.scalar:
            mat = [pp.fvutils.scalar_divergence(g) for g in self._g]
        else:
            mat = [pp.fvutils.vector_divergence(g) for g in self._g]
        matrix = sps.block_diag(mat)
        return matrix


class BoundaryCondition(MergedOperator):
    """Wrapper class for Ad representations of boundary conditions for a given keyword."""

    def __init__(
        self,
        keyword: str,
        grids: Optional[List[pp.Grid]] = None,
        gb: Optional[pp.GridBucket] = None,
    ):
        """Construct a wrapper for boundary conditions for a set of subdomains.

        The boundary values will be ordered according to the ordering in grids, or theorder
        ordre of the GridBucket iteration over grids. Iit is critical that the same
        ordering is used by other operators.

        IMPLEMENTATION NOTE: Only scalar quantities so far; vector operators will be
        added in due course.

        Parameters:
            keyword (str): Keyword that should be used to access the data dictionary
                to get the relevant boundary conditions.
            grids (List of pp.Grid): List of grids. The order of the grids in the list
                sets the ordering of the boundary values.
            gb (pp.GridBucket): Used if grid list is not provided. The order of the
                grids is set according to iteration over the GridBucket nodes.

        """

        self._keyword = keyword
        self._g: List[pp.Grid] = _grid_list(grids, gb)
        self._set_tree()

    def __repr__(self) -> str:
        s = f"Boundary Condition operator with keyword {self.keyword}\n"

        dims = np.zeros(4, dtype=np.int)
        for g in self.g:
            dims[g.dim] += 1

        for d in range(3, -1, -1):
            if dims[d] > 0:
                s += f"{dims[d]} grids of dimension {d}\n"

        return s

    def parse(self, gb: pp.GridBucket) -> np.ndarray:
        """Convert the Ad expression into numerical values for the boundary conditions,
        in the form of an np.ndarray concatenated for all grids.

        Pameteres:
            gb (pp.GridBucket): Mixed-dimensional grid. The boundary condition will be
                taken from the data dictionaries with the relevant keyword.

        Returns:
            np.ndarray: Value of boundary conditions.

        """
        val = []
        for g in self._g:
            data = gb.node_props(g)
            val.append(data[pp.PARAMETERS][self._keyword]["bc_values"])

        return np.hstack([v for v in val])


#### Helper methods below


def _grid_list(grids: List[pp.Grid], gb: pp.GridBucket) -> List[pp.Grid]:
    # Helper method to parse input data
    if grids is None:
        if gb is None:
            raise ValueError(
                "Trace needs either either a list of grids or a GridBucket"
            )
        grids = [g for g, _ in gb]
    return grids


def _subgrid_projections(
    grids: List[pp.Grid], nd: int
) -> Tuple[Dict[pp.Grid, sps.spmatrix], Dict[pp.Grid, sps.spmatrix]]:
    """Construct prolongation matrices from individual grids to a set of grids.

    Matrices for both cells and faces are constructed.

    The global cell and face numbering is set according to the order of the
    input grids.

    """
    face_projection: Dict[pp.Grid, np.ndarray] = {}
    cell_projection: Dict[pp.Grid, np.ndarray] = {}

    tot_num_faces = np.sum([g.num_faces for g in grids]) * nd
    tot_num_cells = np.sum([g.num_cells for g in grids]) * nd

    face_offset = 0
    cell_offset = 0

    for g in grids:
        face_ind = face_offset + pp.fvutils.expand_indices_nd(
            np.arange(g.num_faces), nd
        )
        cell_ind = cell_offset + pp.fvutils.expand_indices_nd(
            np.arange(g.num_cells), nd
        )
        face_sz, cell_sz = g.num_faces * nd, g.num_cells * nd
        face_projection[g] = sps.coo_matrix(
            (np.ones(face_sz), (face_ind, np.arange(face_sz))),
            shape=(tot_num_faces, face_sz),
        ).tocsr()
        cell_projection[g] = sps.coo_matrix(
            (np.ones(cell_sz), (cell_ind, np.arange(cell_sz))),
            shape=(tot_num_cells, cell_sz),
        ).tocsr()

        # Correct start of the numbering for the next grid
        if g.dim > 0:
            # Point grids have no faces
            face_offset = face_ind[-1] + 1

        cell_offset = cell_ind[-1] + 1

    return cell_projection, face_projection