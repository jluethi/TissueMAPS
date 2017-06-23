# Copyright 2016 Markus D. Herrmann, University of Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
'''Jterator module for separation of clumps in a binary image,
where a `clump` is defined as a connected component of certain size and shape.
'''
import numpy as np
import cv2
import mahotas as mh
import skimage.morphology
import logging
import collections

from jtlib.segmentation import separate_clumped_objects
from jtlib.features import Morphology, create_feature_image

VERSION = '0.1.1'

logger = logging.getLogger(__name__)

Output = collections.namedtuple('Output', ['separated_mask', 'figure'])



def main(mask, intensity_image, min_area, max_area,
        min_cut_area, max_circularity, max_convexity, cutting_passes,
        plot=False, selection_test_mode=False):
    '''Detects clumps in `mask` given criteria provided by the user
    and cuts them along the borders of watershed regions, which are determined
    based on the distance transform of `mask`.

    Parameters
    ----------
    mask: numpy.ndarray[Union[numpy.int32, numpy.bool]]
        2D binary or labele image encoding potential clumps
    intensity_image: numpy.ndarray[numpy.uint8 or numpy.uint16]
        2D grayscale image with intensity values of the objects that should
        be detected
    min_area: int
        minimal area an object must have to be considered a clump
    max_area: int
        maximal area an object can have to be considered a clump
    min_cut_area: int
        minimal area a cut object can have
        (useful to limit size of cut objects)
    max_circularity: float
        maximal circularity an object can have to be considerd a clump
    max_convexity: float
        maximal convexity an object can have to be considerd a clump
    cutting_passes: int
        number of cutting cycles to separate clumps that consist of more than
        two subobjects
    plot: bool, optional
        whether a plot should be generated
    selection_test_mode: bool, optional
        whether, instead of the normal plot, heatmaps should be generated that
        display values of the selection criteria *area*, *circularity* and
        *convexity* for each individual object in `mask` as well as
        the selected "clumps" based on the criteria provided by the user

    Returns
    -------
    jtmodules.separate_clumps.Output
    '''
    separated_mask = mask > 0
    for n in range(cutting_passes):
        logger.info('cutting pass #%d', n+1)
        separated_mask = separate_clumped_objects(
            separated_mask, min_cut_area, min_area, max_area,
            max_circularity, max_convexity
        )

    if plot:
        from jtlib import plotting
        if selection_test_mode:
            logger.info('create plot for selection test mode')
            labeled_mask, n_objects = mh.label(mask)
            f = Morphology(labeled_mask)
            values = f.extract()
            area_img = create_feature_image(
                values['Morphology_Area'].values, labeled_mask
            )
            convexity_img = create_feature_image(
                values['Morphology_Convexity'].values, labeled_mask
            )
            circularity_img = create_feature_image(
                values['Morphology_Circularity'].values, labeled_mask
            )
            area_colorscale = plotting.create_colorscale(
                'Greens', n_objects,
                add_background=True, background_color='white'
            )
            circularity_colorscale = plotting.create_colorscale(
                'Blues', n_objects,
                add_background=True, background_color='white'
            )
            convexity_colorscale = plotting.create_colorscale(
                'Reds', n_objects,
                add_background=True, background_color='white'
            )
            plots = [
                plotting.create_float_image_plot(
                    area_img, 'ul', colorscale=area_colorscale
                ),
                plotting.create_float_image_plot(
                    convexity_img, 'ur', colorscale=convexity_colorscale
                ),
                plotting.create_float_image_plot(
                    circularity_img, 'll', colorscale=circularity_colorscale
                ),
                plotting.create_mask_image_plot(
                    clumps_mask, 'lr'
                ),
            ]
            figure = plotting.create_figure(
                plots,
                title=(
                    'Selection criteria: "area" (green), "convexity" (red) '
                    'and "circularity" (blue)'
                )
            )
        else:
            logger.info('create plot')

            cut_mask = mask - separated_mask
            clumps_mask = np.zeros(mask.shape, bool)
            initial_objects_label_image, n_initial_objects = mh.label(mask > 0)
            for i in range(1, n_initial_objects+1):
                index = initial_objects_label_image == i
                if len(np.unique(separated_mask[index])) > 1:
                    clumps_mask[index] = True

            labeled_separated_mask, n_objects = mh.label(separated_mask)
            colorscale = plotting.create_colorscale(
                'Spectral', n=n_objects, permute=True, add_background=True
            )
            outlines = mh.morph.dilate(mh.labeled.bwperim(separated_mask))
            cutlines = mh.morph.dilate(mh.labeled.bwperim(cut_mask))
            plots = [
                plotting.create_mask_image_plot(
                    labeled_separated_mask, 'ul', colorscale=colorscale
                ),
                plotting.create_intensity_overlay_image_plot(
                    intensity_image, outlines, 'ur'
                ),
                plotting.create_mask_overlay_image_plot(
                    clumps_mask, cutlines, 'll'
                )
            ]
            figure = plotting.create_figure(
                plots, title='separated clumps'
            )
    else:
        figure = str()

    return Output(separated_mask, figure)
