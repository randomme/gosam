#!/usr/bin/env python
# this file is part of gosam (generator of simple atomistic models) 
# Licence: GNU General Public License version 2

import sys
from math import sin, cos, pi, atan, sqrt, degrees, radians, asin, acos
from copy import deepcopy
from numpy import dot, array, identity

import graingen
import mdprim
from csl import find_orthorhombic_pbc
from rotmat import round_to_multiplicity
from utils import get_command_line


fcc_node_pos = [
    (0.0, 0.0, 0.0),
    (0.5, 0.5, 0.0),
    (0.0, 0.5, 0.5),
    (0.5, 0.0, 0.5),
] 

def get_diamond_node_pos():
    node_pos = []
    for i in fcc_node_pos:
        node_pos.append(i)
        node_pos.append((i[0]+0.25, i[1]+0.25, i[2]+0.25))
    return node_pos


def make_lattice(cell, node_pos, node_atoms):
    nodes = [graingen.Node(i, node_atoms) for i in node_pos]
    lattice = graingen.CrystalLattice(cell, nodes)
    return lattice


def make_simple_cubic_lattice():
    cell = graingen.CubicUnitCell(1.)
    node = graingen.Node((0.0, 0.0, 0.0), [("X", 0.0, 0.0, 0.0)])
    return graingen.CrystalLattice(cell, [node])


def make_sic_lattice():
    print "---> Preparing Cubic SiC"
    #cell = graingen.CubicUnitCell(4.3581) # 4.3596 4.36
    cell = graingen.CubicUnitCell(4.32119155) # value from Tersoff '89 / should be 4.321059889

    # nodes in unit cell (as fraction of unit cell parameters)
    node_pos = fcc_node_pos[:]

    # atoms in node (as fraction of unit cell parameters)
    node_atoms = [
        ("Si", 0.0, 0.0, 0.0),
        ("C",  0.25,0.25,0.25), 
    ]
    return make_lattice(cell, node_pos, node_atoms)

def make_sic_polytype_lattice(polytype="AB"):
    print "---> Preparing SiC polytype " + polytype
    #a = 3.073
    #h = 2.51
    a_c = 4.359 # lattice parameter for cubic SiC
    a = a_c / sqrt(2)
    h = a_c / sqrt(3)
    cell, nodes = graingen.generate_polytype(a=a, h=h, polytype=polytype)
    #atoms in node (as fraction of (a,a,h) parameters)
    node_atoms = [
        ("Si", 0.0, 0.0, 0.0),
        ("C",  0.0, 0.0, 0.75 / len(polytype)), 
    ]
    return make_lattice(cell, nodes, node_atoms)

def make_diamond_lattice(atom_name="C", a=3.567):
    cell = graingen.CubicUnitCell(a)
    node_pos = get_diamond_node_pos()
    node_atoms = [ (atom_name, 0.0, 0.0, 0.0) ]
    return make_lattice(cell, node_pos, node_atoms)

def make_si_lattice():
    return make_diamond_lattice(atom_name="Si", a=5.43)

class OrthorhombicPbcModel(graingen.FreshModel):
    def __init__(self, lattice, dimensions, title):
        pbc = identity(3) * dimensions 
        graingen.FreshModel.__init__(self, lattice, pbc, title=title)

    def get_vertices(self):
        return [(x, y, z) for x in self._min_max[0] 
                          for y in self._min_max[1]
                          for z in self._min_max[2]]

    def _do_gen_atoms(self, vmin, vmax):
        self._min_max = zip(vmin, vmax)
        self.compute_scope()
        print self.get_scope_info()
        for node, abs_pos in self.get_all_nodes():
            for atom in node.atoms_in_node:
                xyz = dot(abs_pos+atom.pos, self.unit_cell.M_1)
                if (vmin < xyz).all() and (xyz <= vmax).all():
                    self.atoms.append(mdprim.Atom(atom.name, xyz))


class RotatedMonocrystal(OrthorhombicPbcModel):
    """Monocrystal rotated using rot_mat rotation matrix
    """
    def __init__(self, lattice, dim, rot_mat, title=None):
        self.lattice = lattice
        self.dim = array(dim, dtype=float)
        self.rot_mat = rot_mat
        if title is None:
            title = "generated by gosam.monocryst"
        OrthorhombicPbcModel.__init__(self, lattice, self.dim, title=title)

    def generate_atoms(self, upper=None, z_margin=0.):
        """upper and z_margin are used for building bicrystal
        """
        self.atoms = []
        vmin, vmax = self.get_box_to_fill(self.dim, upper, z_margin)
        if self.rot_mat is not None:
            self.unit_cell.rotate(self.rot_mat)
        self._do_gen_atoms(vmin, vmax)
        if upper is None:
            print "Number of atoms in monocrystal: %i" % len(self.atoms) 
        return self.atoms

    def get_box_to_fill(self, dim, upper, z_margin):
        # make it a bit asymmetric, to avoid problems with PBC
        eps = 0.001
        vmin = -self.dim/2. + eps
        vmax = self.dim/2. + eps
        assert upper in (True, False, None)
        if upper is True:
            vmin[2] = eps
            if z_margin:
                vmax[2] -= z_margin / 2
        elif upper is False:
            vmax[2] = eps
            if z_margin:
                vmin[2] += z_margin / 2
        return vmin, vmax



# primitive adjusting of PBC box for [010] rotation
def test_rotmono_adjust():    
    lattice = make_sic_lattice()
    a = lattice.unit_cell.a
    dimensions = [10*a, 10*a, 10*a]
    theta = radians(float(sys.argv[1]))

    d = dimensions[0]
    n_ = d * sin(theta) / a
    m_ = d / (a * cos(theta))
    n = round(n_)
    m = round(m_)
    new_th = 0.5 * asin(2.*n/m)
    new_d = m * a * cos(new_th)
    print "theta =", degrees(new_th), "  d =", new_d
    dimensions[0] = new_d
    dimensions[1] = round(dimensions[1] / a) * a
    theta = new_th

    rot_mat = graingen.rodrigues((0,1,0), theta, verbose=False) 
    config = RotatedMonocrystal(lattice, dimensions, rot_mat)
    config.generate_atoms()
    config.export_atoms("monotest.cfg", format="atomeye")


def mono(lattice, nx, ny, nz, output_filename="mono.cfg"):
    min_dim = lattice.unit_cell.get_orthorhombic_supercell()
    dim = [round_to_multiplicity(min_dim[0], 10*nx),
           round_to_multiplicity(min_dim[1], 10*ny),
           round_to_multiplicity(min_dim[2], 10*nz)]
    print "dimensions [A]:", dim[0], dim[1], dim[2]
    config = RotatedMonocrystal(deepcopy(lattice), dim, rot_mat=None,
                                title=get_command_line())
    config.generate_atoms()
    config.export_atoms(output_filename)


def get_named_lattice(name):
    name = name.lower()
    if name == "sic":
        lattice = make_sic_lattice()
    elif name == "si":
        lattice = make_si_lattice()
    elif name == "diamond":
        lattice = make_diamond_lattice()
    elif name.startswith("sic:"):
        lattice = make_sic_polytype_lattice(name[4:])
    else:
        raise ValueError("Unknown lattice: %s" % name)
    return lattice


usage = """Usage: 
monocryst.py crystal nx ny nz filename
 where crystal is one of "si", "sic", "sic:ABABC". 
  In the last case any polytype can be given" 
"""


def main():
    if len(sys.argv) != 6:
        print usage
        sys.exit()

    lattice = get_named_lattice(name)
    nx, ny, nz = float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]) 
    mono(lattice, nx, ny, nz, output_filename=sys.argv[5])



if __name__ == '__main__':
    main()


