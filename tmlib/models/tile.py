# TmLibrary - TissueMAPS library for distibuted image analysis routines.
# Copyright (C) 2016  Markus D. Herrmann, University of Zurich and Robin Hafen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import os
import logging
import numpy as np
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import UniqueConstraint

from tmlib.image import PyramidTile
from tmlib.metadata import PyramidTileMetadata
from tmlib.models import ExperimentModel

logger = logging.getLogger(__name__)


class ChannelLayerTile(ExperimentModel):

    '''A *channel layer tile* is a component of an image pyramid. Each tile
    holds a single 2D 8-bit pixel plane with pre-defined dimensions.

    '''

    __tablename__ = 'channel_layer_tiles'

    __table_args__ = (
        UniqueConstraint(
            'z', 'y', 'x', 'channel_layer_id'
        ),
        Index(
            'ix_channel_layer_tiles_z_y_x_channel_layer_id',
            'z', 'y', 'x', 'channel_layer_id'
        )
    )

    __distribute_by_hash__ = 'channel_layer_id'

    _pixels = Column('pixels', BYTEA)

    #: int: zero-based zoom level index
    z = Column(Integer)

    #: int: zero-based coordinate on vertical axis
    y = Column(Integer)

    #: int: zero-based coordinate on horizontal axis
    x = Column(Integer)

    #: int: ID of parent channel layer
    channel_layer_id = Column(Integer, index=True, nullable=False)

    def __init__(self, z, y, x, channel_layer_id, pixels=None):
        '''
        Parameters
        ----------
        z: int
            zero-based zoom level index
        y: int
            zero-based row index of the tile at given zoom level
        x: int
            zero-based column index of the tile at given zoom level
        channel_layer_id: int
            ID of the parent channel pyramid
        pixels: tmlib.image.PyramidTile, optional
            pixels array (default: ``None``)
        '''
        self.y = y
        self.x = x
        self.z = z
        self.channel_layer_id = channel_layer_id
        self.pixels = pixels

    @hybrid_property
    def pixels(self):
        '''tmlib.image.PyramidTile: JPEG encoded tile'''
        # TODO: consider creating a custom SQLAlchemy column type
        metadata = PyramidTileMetadata(
            z=self.z, y=self.y, x=self.x,
            channel_layer_id=self.channel_layer_id
        )
        return PyramidTile.create_from_binary(self._pixels, metadata)

    @pixels.setter
    def pixels(self, tile):
        # TODO: It might be better to use Postgis raster format, but there don't
        # seem to be good solutions for inserting raster data via SQLAlchemy
        if tile is not None:
            self._pixels = tile.jpeg_encode()
        else:
            self._pixels = None

    def __repr__(self):
        return '<%s(id=%r, z=%r, y=%r, x=%r)>' % (
            self.__class__.__name__, self.id, self.z, self.y, self.x
        )


