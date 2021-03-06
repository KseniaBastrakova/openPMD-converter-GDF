""" Add particle patches to OpenPMD file"""

import argparse
import os
import h5py
from shutil import copyfile
import re
import numpy as np


class List_coorditates():
    """ Collect values from datasets in hdf file """

    def __init__(self):
        self.list_x = []
        self.list_y = []
        self.list_z = []

    def __call__(self, name, node):
        if name == 'position':
            for key in node.keys():
                if key == 'x':
                    self.list_x = node[key][()]
                elif key == 'y':
                    self.list_y = node[key][()]
                elif key == 'z':
                    self.list_z = node[key][()]
        return None


class List_values():
    def __init__(self):
        self.list_values = []

    def __call__(self, name, node):
        if isinstance(node, h5py.Dataset):
            self.list_values.append(node)
        return None


class Extent_values():
    def __init__(self, unitSI, grid_sizes, devices_numbers):
        self.unitSI = unitSI
        self.x_range, self.y_range, self.z_range = get_ranges(grid_sizes)
        if len(devices_numbers) > 2:
            self.dimension = 3
            self.x_split = devices_numbers[0]
            self.y_split = devices_numbers[1]
            self.z_split = devices_numbers[2]
        else:
            self.dimension = 2
            self.x_split = devices_numbers[0]
            self.y_split = devices_numbers[1]

    def get_x_extent(self):
        return self.get_extent(self.x_range, self.x_split)

    def gef_dimention(self):
        return self.dimension

    def get_y_extent(self):
        return self.get_extent(self.y_range, self.y_split)

    def get_z_extent(self):
        if self.z_range != None:
            return self.get_extent(self.z_range, self.z_split)
        else:
            return None

    def get_extent(self, current_range, split):
        extent = []
        lenght = current_range[1] - current_range[0]
        current_part = lenght / float(split)
        start_value = current_range[0]
        for i in range(0, split):
            if (start_value + current_part) < current_range[1]:
                extent.append(current_part/self.unitSI)
                start_value = start_value + current_part
            else:
                extent.append((current_range[1] - start_value)/self.unitSI)
                start_value = start_value + current_range[1] - start_value

        return extent


def get_ranges(grid_sizes):
    x_range = None
    y_range = None
    z_range = None
    if len(grid_sizes) == 2:
        x_range = (grid_sizes[0], grid_sizes[1])
    if len(grid_sizes) == 4:
        x_range = (grid_sizes[0], grid_sizes[1])
        y_range = (grid_sizes[2], grid_sizes[3])
    elif len(grid_sizes) == 6:
        x_range = (grid_sizes[0], grid_sizes[1])
        y_range = (grid_sizes[2], grid_sizes[3])
        z_range = (grid_sizes[4], grid_sizes[5])
    return x_range, y_range, z_range


def count_points_idx(coordinate_lists, grid_sizes, devices_numbers):
    list_x = coordinate_lists.list_x
    list_y = coordinate_lists.list_y
    list_z = coordinate_lists.list_z

    x_range, y_range, z_range = get_ranges(grid_sizes)
    size_array = len(list_z)

    patch_data = None

    if size_array != 0 and len(devices_numbers) == 3:
        splitting_x = devices_numbers[0]
        splitting_y = devices_numbers[1]
        splitting_z = devices_numbers[2]
        patch_data = Particles_data(list_x, splitting_x, x_range, list_y, splitting_y, y_range,
                                    list_z, splitting_z, z_range)
    else:
        splitting_x = devices_numbers[0]
        splitting_y = devices_numbers[1]
        patch_data = Particles_data(list_x, splitting_x, x_range, list_y, splitting_y, y_range)

    size_indexes = patch_data.get_size_split()

    list_number_particles_in_parts, links_to_array = \
        points_to_patches(patch_data)

    resultArray, final_size = divide_points_to_patches(size_array, size_indexes, list_number_particles_in_parts,
                                                       links_to_array)

   # test_print_2d(list_x, list_y, resultArray, final_size)
    return resultArray, final_size, list_number_particles_in_parts


def move_values(file_with_patches, final_size, values_list, resultArray):

    for dataset in values_list.list_values:
        name_dataset = dataset.name
        size = len(dataset.value)
        moved_values = np.zeros(size)
        for i in range(0, len(final_size) - 1):
            for j in range(int(final_size[i]), int(final_size[i + 1])):
                moved_values[j] = (dataset.value[int(resultArray[j])])
        del file_with_patches[name_dataset]
        file_with_patches.create_dataset(name_dataset, data=moved_values)


def handle_particle_group(group, file_with_patches, devices_numbers, grid_sizes, field_size):
    """ move values according the patches,  count idxs, change grids """

    coordinate_lists = List_coorditates()
    group.visititems(coordinate_lists)
    values_list = List_values()
    group.visititems(values_list)

    resultArray, final_size, list_number_particles_in_parts\
        = count_points_idx(coordinate_lists, grid_sizes, devices_numbers)

    values_extent = Extent_values(field_size, grid_sizes, devices_numbers)

    move_values(file_with_patches, final_size, values_list, resultArray)
    return final_size, list_number_particles_in_parts, values_extent, coordinate_lists


def OpenPMD_add_patches(hdf_file_name, name_of_file_with_patches, grid_sizes, devices_numbers, field_size):
    """ Add patche to OpenPMD file """

    copyfile(hdf_file_name, name_of_file_with_patches)
    file_with_patches = h5py.File(name_of_file_with_patches)
    hdf_file = h5py.File(hdf_file_name)
    particles_name = get_particles_name(hdf_file)
    hdf_datasets = Particles_groups(particles_name)

    file_with_patches.visititems(hdf_datasets)

    for group in hdf_datasets.particles_groups:
        final_size, list_number_particles_in_parts, values_extent, coordinate_lists = \
            handle_particle_group(group, file_with_patches, devices_numbers, grid_sizes, field_size)
        add_patch_to_particle_group(group, final_size, list_number_particles_in_parts, values_extent)


class Particles_groups():
    """ Collect values from datasets in hdf file """

    def __init__(self, particles_name):
        self.particles_groups = []
        self.positions = []
        self.name_particles = particles_name

    def __call__(self, name, node):
        if isinstance(node, h5py.Group):
            name_idx = node.name.find(self.name_particles)
            if name_idx != -1:
                group_particles_name = node.name[name_idx + len(self.name_particles) + 1:]
                if group_particles_name.endswith('position'):
                    self.positions.append(node)
                if group_particles_name.find('/') == -1 and len(group_particles_name) != 0:
                    self.particles_groups.append(node)
        return None


class Particles_data():
    """ Class with  calculating position of particles"""

    def __init__(self, list_x, splitting_x, range_x, list_y, splitting_y, range_y,
                 list_z=None, splitting_z=None, range_z=None):
        self.x_coord = list_x
        self.y_coord = list_y
        self.z_coord = list_z
        self.x_split = splitting_x
        self.y_split = splitting_y
        self.z_split = splitting_z
        self.x_range = range_x
        self.y_range = range_y
        self.z_range = range_z

    def get_size_split(self):
        size = 0
        if self.z_split == None:
            size = self.x_split * self.y_split
        else:
            size = self.x_split * self.y_split * self.z_split
        return size

    def get_array_lenght(self):
        return len(self.x_coord)

    def get_patch_x(self, i):
        return get_positon(self.x_range[1], self.x_range[0], self.x_split, self.x_coord[i])

    def get_patch_y(self, i):
        return get_positon(self.y_range[1], self.y_range[0], self.y_split, self.y_coord[i])

    def get_patch_z(self, i):
        return get_positon(self.z_range[1], self.z_range[0], self.z_split, self.z_coord[i])

    def get_position_idx2d(self, x_patch, y_patch):
        return x_patch * self.y_split + y_patch

    def get_position_idx3d(self, x_patch, y_patch, z_patch):
        return (x_patch * self.y_split + y_patch) * self.z_split + z_patch

    def get_position_idx(self, i):
        particle_idx = 0
        if self.z_split == None:
            x_patch = self.get_patch_x(i)
            y_patch = self.get_patch_y(i)
            particle_idx = self.get_position_idx2d(x_patch, y_patch)
        else:
            x_patch = self.get_patch_x(i)
            y_patch = self.get_patch_y(i)
            z_patch = self.get_patch_z(i)
            particle_idx = self.get_position_idx3d(x_patch, y_patch, z_patch)
        return particle_idx


def add_patch_to_particle_group(group, final_size, list_number_particles_in_parts, values_extent):
    """Add patch to ecach particle group: """

    patch_group = group.require_group('ParticlePatches')
    patch_group.create_dataset('numParticlesOffset', data=final_size.data, dtype=np.dtype('int64'))
    patch_group.create_dataset('numParticles', data=list_number_particles_in_parts.data, dtype=np.dtype('int64'))
    extent_group = patch_group.require_group('extent')
    offset_group = patch_group.require_group('offset')
    add_extent(extent_group, values_extent)
    add_offset(offset_group, values_extent)


def add_extent(extent_group, values_extent):
    """ Add extent group to particle group """

    if values_extent.gef_dimention() == 2:
        array_x = values_extent.get_x_extent()
        array_y = values_extent.get_y_extent()
        extent_group.create_dataset('x', data=array_x, dtype=np.dtype('int'))
        extent_group.create_dataset('y', data=array_y, dtype=np.dtype('int'))
    elif values_extent.gef_dimention() == 3:
        array_x = values_extent.get_x_extent()
        array_y = values_extent.get_y_extent()
        array_z = values_extent.get_z_extent()
        extent_group.create_dataset('x', data=array_x, dtype=np.dtype('int'))
        extent_group.create_dataset('y', data=array_y, dtype=np.dtype('int'))
        extent_group.create_dataset('z', data=array_z, dtype=np.dtype('int'))


def add_offset(offset_group, values_extent):
    """ Add offset group to particle group """

    if values_extent.gef_dimention() == 2:
        array_x = values_extent.get_x_extent()
        offset_x = np.cumsum(array_x,  dtype=int)
        array_y = values_extent.get_y_extent()
        offset_y = np.cumsum(array_y, dtype=int)
        offset_group.create_dataset('x', data=offset_x, dtype=np.dtype('int'))
        offset_group.create_dataset('y', data=offset_y, dtype=np.dtype('int'))
    elif values_extent.gef_dimention() == 3:
        array_x = values_extent.get_x_extent()
        array_y = values_extent.get_y_extent()
        array_z = values_extent.get_z_extent()
        offset_x = np.cumsum(array_x, dtype=int)
        offset_y = np.cumsum(array_y, dtype=int)
        offset_z = np.cumsum(array_z, dtype=int)
        offset_group.create_dataset('x', data=offset_x, dtype=np.dtype('int'))
        offset_group.create_dataset('y', data=offset_y, dtype=np.dtype('int'))
        offset_group.create_dataset('z', data=offset_z, dtype=np.dtype('int'))


def test_patches(grid_sizes, devices_numbers, numParticlesOffset, arrayX, arrayY):

    maxX = max(arrayX)
    minX = min(arrayX)
    if len(devices_numbers) == 3:
        print('3-D patches')
    elif len(devices_numbers) == 2:
        print('2-d patches')
        len_x = (grid_sizes[1] - grid_sizes[0]) / devices_numbers[0]
        len_y = (grid_sizes[3] - grid_sizes[2]) / devices_numbers[1]

        patchX = []
        patchY = []
        for i in range(0, devices_numbers[0]):
            Xstart = grid_sizes[0] + i * len_x
            Xend = 0
            if i == devices_numbers[0]:
                Xend = grid_sizes[1]
            else:
                Xend = grid_sizes[0] + (i + 1) * len_x
            patchX.append((Xstart, Xend))

        for i in range(0, devices_numbers[1]):
            Ystart = grid_sizes[2] + i * len_y
            Yend = 0
            if i == devices_numbers[1]:
                Yend = grid_sizes[3]
            else:
                Yend = grid_sizes[2] + (i + 1) * len_y
            patchY.append((Ystart, Yend))

        numXpatch = devices_numbers[0]
        numYpatch = devices_numbers[1]

        for i in range(0, numXpatch):
            for j in range(0, numYpatch):
                idx = j + i * numYpatch
                check_particles_in_patch(numParticlesOffset[idx], numParticlesOffset[idx + 1], patchX[i], patchY[j], arrayX, arrayY)

    elif len(devices_numbers) == 1:
        print('1-d patches')


def check_particles_in_patch(idxStartPatch, idxEndPatch, rangeX, rangeY, arrayX, arrayY):

    particle_in_patch = True
    for i in range(idxStartPatch, idxEndPatch):
        pointX = float(arrayX[i])
        pointY = float(arrayY[i])
      #  print('point ==  ' + str(pointX) +' , ' + str(pointY))
        if point_in_range(rangeX, pointX) and point_in_range(rangeY, pointY):
            particle_in_patch = True
        else:
            particle_in_patch = False
            print('ERRROR!!!! point ' + str(pointX) + ', ' + str(pointY) + 'is not in: '+ str(rangeX) + ', '+ str(rangeY))
        #    break
    return particle_in_patch


def point_in_range(rangePoint, point):
    startValue = float(rangePoint[0])
    endValue = float(rangePoint[1])
    if startValue <= point and point <= endValue:
        return True
    else:
        return False


def count_indexes(links_to_array, final_size, size_indexes, size_array):
    """ Add offset group to particle group """

    counter_indexes = np.zeros(size_indexes)
    resultArray = np.zeros(max(size_indexes, size_array))

    for i in range(0, len(links_to_array)):
        xy_idx = links_to_array[i]
        start_size = final_size[xy_idx]
        adding_counter = counter_indexes[xy_idx]
        resultArray[int(start_size + adding_counter)] = i
        counter_indexes[xy_idx] = adding_counter + 1
    return resultArray


def points_to_patches(patch_data):
    """ Devide points to patches """

    list_number_particles_in_parts = np.zeros(patch_data.get_size_split() + 1, dtype=int)
    links_to_array = []
    for i in range(0, patch_data.get_array_lenght()):
        particle_idx = patch_data. get_position_idx(i)
        sum_links = list_number_particles_in_parts[particle_idx]
        list_number_particles_in_parts[particle_idx] = sum_links + 1
        links_to_array.append(particle_idx)
    return list_number_particles_in_parts, links_to_array


def divide_points_to_patches(size_array, size_indexes, list_number_particles_in_parts, links_to_array):
    final_size = np.cumsum(list_number_particles_in_parts, dtype=int)
    final_size = np.insert(final_size, 0, 0)
    resultArray = count_indexes(links_to_array, final_size, size_indexes, size_array)
    return resultArray, final_size


def test_print_2d(list_x, list_y, resultArray, final_size):
    for i in range(0, len(final_size) - 1):
        print('-----------------------------------------------')
        print('particles in ' + str(i))
        print('start   ' + str(int(final_size[i])) + str(' end   ') + str(int(final_size[i + 1] - 1)))
        for j in range(int(final_size[i]), int(final_size[i + 1])):
            print('x ==  ' + str(list_x[int(resultArray[j])]) + 'y ==  ' + str(list_y[int(resultArray[j])]))


def get_positon(max_coord, min_coord, separator, x_current):
    """ Get name of particles group """
    lenght = max_coord - min_coord
    return max(0, min(int((x_current - min_coord) * separator / lenght), separator - 1))


def get_particles_name(hdf_file):
    """ Get name of particles group """

    particles_name = ''
    if hdf_file.attrs.get('particlesPath') != None:
        particles_name = hdf_file.attrs.get('particlesPath')
        particles_name = decode_name(particles_name)
    else:
        particles_name = 'particles'
    return particles_name


def decode_name(attribute_name):
    """ Decode name from binary """

    decoding_name = attribute_name.decode('ascii', errors='ignore')
    decoding_name = re.sub(r'\W+', '', decoding_name)
    return decoding_name


def add_patches(hdf_file, hdf_file_with_patches, grid_sizes, devices_number):
    """ Check correct of arguments"""

    name_of_file_with_patches = ''
    field_size = 0.00001
    if hdf_file != '':
        if os.path.exists(hdf_file):
            name = hdf_file[:-4]
            idx_of_name = name.rfind('/')
            if idx_of_name != -1:
                name_of_file_with_patches = hdf_file_with_patches + hdf_file[idx_of_name + 1: -4] + 'with_patches.h5'
            else:
                name_of_file_with_patches = hdf_file_with_patches + hdf_file[:-3] + '.h5'
            OpenPMD_add_patches(hdf_file, name_of_file_with_patches, grid_sizes, devices_number, field_size)
        else:
            print('The .hdf file does not exist')


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="add patches to OpenPMD file")
    parser.add_argument("-hdf", metavar='hdf_file', type=str,
                        help="hdf file without patches")
    parser.add_argument("-result", metavar='hdf_file_with_patches', type=str,
                        help="path to result file with patches")
    parser.add_argument("-gridSize", type=float, nargs='*',
                        help="Size of the simulation grid in cells as x y z")
    parser.add_argument("-devicesNumber", type=int, nargs='*',
                        help="Number of devices in each dimension (x,y,z)")

    args = parser.parse_args()
    add_patches(args.hdf, args.result, args.gridSize, args.devicesNumber)



