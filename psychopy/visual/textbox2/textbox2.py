#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
#
#  FreeType high-level python API - Copyright 2011-2015 Nicolas P. Rougier
#  Distributed under the terms of the new BSD license.
#
# -----------------------------------------------------------------------------
'''
Subpixel rendering AND positioning using OpenGL and shaders.

'''
import numpy as np
import random
import OpenGL.GL as gl
import ctypes

from ..basevisual import BaseVisualStim, ColorMixin, ContainerMixin
from psychopy.tools.attributetools import attributeSetter
from psychopy.tools.monitorunittools import convertToPix
from .fontmanager import FontManager, TextureAtlas, TextureFont
from ..shaders import Shader, fragTextBox2, vertSimple
#
# allFonts = FontManager(monospace_only = False)
#
shader = None


class TextBox2(BaseVisualStim, ContainerMixin):
    def __init__(self, win, text, font, atlas,
                 pos=(0,0), units='pix', letterHeight=12,
                 width=None, height=None,  # by default use the text contents
                 shader = None,
                 color=(1.0, 1.0, 1.0),
                 colorSpace='rgb',
                 opacity=1.0,
                 bold=False,
                 italic=False,
                 anchor_x = 'left', anchor_y = 'baseline',
                 alignHoriz='center',
                 alignVert='center',
                 flipHoriz=False,
                 flipVert=False,
                 name='', autoLog=None):
        BaseVisualStim.__init__(self, win, units=units, name=name,
                                          autoLog=False)
        self.win = win
        if shader is None:
            shader = Shader(vertSimple, fragTextBox2)
        self.shader = shader
        self.atlas = atlas
        self.font = font
        self.letterHeight = letterHeight
        self.bold = bold
        self.italic = italic
        self.anchor_y = anchor_y
        self.anchor_x = anchor_x
        self._needVertexUpdate = False
        # standard stimulus params
        self.pos = pos
        self.color = color
        self.colorSpace = colorSpace
        self.opacity = opacity
        self._indices = None
        self._colors = None

        self.flipHoriz = flipHoriz
        self.flipVert = flipVert
        self.text = text  # setting this triggers a _layout() call so do last

    @attributeSetter
    def text(self, text):
        self.__dict__['text'] = text
        self._layout()

    def _layout(self):
        """Layout the text, calculating the vertex locations
        """
        text = self.text
        color = self.color
        font = self.font
        self.vertices = np.zeros((len(text)*4,2), dtype=np.float32)
        self._indices  = np.zeros((len(text)*6, ), dtype=np.uint)
        self._colors   = np.zeros((len(text)*4,4), dtype=np.float32)
        self._texcoords= np.zeros((len(text)*4,2), dtype=np.float32)
        pen = [0,0]
        prev = None

        for i,charcode in enumerate(text):
            glyph = font[charcode]
            kerning = glyph.get_kerning(prev)
            print(kerning)
            x0 = pen[0] + glyph.offset[0] + kerning
            x0 = int(x0)
            y0 = pen[1] + glyph.offset[1]
            x1 = x0 + glyph.size[0]
            y1 = y0 - glyph.size[1]
            u0 = glyph.texcoords[0]
            v0 = glyph.texcoords[1]
            u1 = glyph.texcoords[2]
            v1 = glyph.texcoords[3]


            index     = i*4
            indices   = [index, index+1, index+2, index, index+2, index+3]
            vertices  = [[x0,y0],[x0,y1],[x1,y1], [x1,y0]]
            texcoords = [[u0,v0],[u0,v1],[u1,v1], [u1,v0]]
            colors    = [color,]*4

            self.vertices[i*4:i*4+4] = vertices
            self._indices[i*6:i*6+6] = indices
            self._texcoords[i*4:i*4+4] = texcoords
            self._colors[i*4:i*4+4] = color
            pen[0] = pen[0]+glyph.advance[0]/64.0 + kerning
            pen[1] = pen[1]+glyph.advance[1]/64.0
            prev = charcode

        width = pen[0]-glyph.advance[0]/64.0+glyph.size[0]

        if self.anchor_y == 'top':
            dy = -round(font.ascender)
        elif self.anchor_y == 'center':
            dy = +round(-font.height/2-font.descender)
        elif self.anchor_y == 'bottom':
            dy = -round(font.descender)
        else:
            dy = 0

        if self.anchor_x == 'right':
            dx = -width/1.0
        elif self.anchor_x == 'center':
            dx = -width/2.0
        else:
            dx = 0
        self.vertices += (round(dx), round(dy))
        # if we had to add more glyphs to make possible then 
        if self.font._dirty:
            self.atlas.upload()
            self.font._dirty = False
        self._needVertexUpdate = True

    def draw(self):
        if self._needVertexUpdate:
            self._updateVertices()
        gl.glPushMatrix()
        self.win.setScale('pix')

        gl.glEnable( gl.GL_TEXTURE_2D )
        gl.glDisable( gl.GL_DEPTH_TEST )

        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)

        gl.glVertexPointer(2, gl.GL_FLOAT, 0, self.verticesPix)

        gl.glColorPointer(4, gl.GL_FLOAT, 0, self._colors)
        gl.glTexCoordPointer(2, gl.GL_FLOAT, 0, self._texcoords)

        gl.glEnable( gl.GL_BLEND )

        self.shader.bind()
        self.shader.setInt('texture', 0)
        self.shader.setFloat('pixel', [1.0/512, 1.0/512])
        gl.glDrawElements(gl.GL_TRIANGLES, len(self._indices),
                          gl.GL_UNSIGNED_INT, self._indices)
        self.shader.unbind()
        gl.glDisableVertexAttribArray( 1 );
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable( gl.GL_TEXTURE_2D )
        gl.glDisable( gl.GL_BLEND )

        gl.glPopMatrix()

    def _updateVertices(self):
        """Sets Stim.verticesPix and ._borderPix from pos, size, ori,
        flipVert, flipHoriz
        """
        # check whether stimulus needs flipping in either direction
        flip = np.array([1, 1])
        if hasattr(self, 'flipHoriz') and self.flipHoriz:
            flip[0] = -1  # True=(-1), False->(+1)
        if hasattr(self, 'flipVert') and self.flipVert:
            flip[1] = -1  # True=(-1), False->(+1)

        if hasattr(self, 'vertices'):
            verts = self.vertices
        else:
            verts = self._verticesBase

        # set size and orientation, combine with position and convert to pix:
        if hasattr(self, 'fieldSize'):
            # this is probably a DotStim and size is handled differently
            verts = np.dot(verts * flip, self._rotationMatrix)
        else:
            verts = np.dot(verts * flip, self._rotationMatrix)
        verts = convertToPix(vertices=verts, pos=self.pos,
                             win=self.win, units=self.units)
        self.__dict__['verticesPix'] = verts

        if hasattr(self, 'border'):
            # border = self.border
            border = np.dot(self.size * self.border *
                            flip, self._rotationMatrix)
            border = convertToPix(
                vertices=border, pos=self.pos, win=self.win,
                units=self.units)
            self.__dict__['_borderPix'] = border

        self._needVertexUpdate = False