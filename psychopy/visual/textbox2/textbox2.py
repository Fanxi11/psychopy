#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
#
#  FreeType high-level python API - Copyright 2011-2015 Nicolas P. Rougier
#  Distributed under the terms of the new BSD license.
#
# -----------------------------------------------------------------------------

"""
TextBox2 provides a combination of features from TextStim and TextBox and then
some more added:

    - fast like TextBox (TextStim is pyglet-based and slow)
    - provides for fonts that aren't monospaced (unlike TextBox)
    - adds additional options to use <b>bold<\b> and <i>italic<\i> tags in text

"""
import numpy as np
import random
import OpenGL.GL as gl
import ctypes

from ..basevisual import BaseVisualStim, ColorMixin, ContainerMixin
from psychopy.tools.attributetools import attributeSetter
from psychopy.tools.monitorunittools import convertToPix
from .fontmanager import FontManager, GLFont
from .. import shaders

allFonts = FontManager()

# compile global shader programs later (when we're certain a GL context exists)
rgbShader = None
alphaShader = None

codes = {'BOLD_START': u'\uE100',
         'BOLD_END': u'\uE101',
         'ITAL_START': u'\uE102',
         'ITAL_END': u'\uE103'}

defaultLetterHeight = {'cm': 1.0,
                       'deg': 1.0,
                       'degs': 1.0,
                       'degFlatPos': 1.0,
                       'degFlat': 1.0,
                       'norm': 0.1,
                       'height': 0.2,
                       'pix': 20,
                       'pixels': 20}

defaultBoxWidth = {'cm': 15.0,
                   'deg': 15.0,
                   'degs': 15.0,
                   'degFlatPos': 15.0,
                   'degFlat': 15.0,
                   'norm': 1,
                   'height': 1,
                   'pix': 500,
                   'pixels': 500}


class TextBox2(BaseVisualStim, ContainerMixin):
    def __init__(self, win, text, font,
                 pos=(0, 0), units='pix', letterHeight=12,
                 size=None,
                 color=(1.0, 1.0, 1.0),
                 colorSpace='rgb',
                 opacity=1.0,
                 bold=False,
                 italic=False,
                 anchor='center',
                 alignHoriz='center',
                 alignVert='center',
                 flipHoriz=False,
                 flipVert=False,
                 name='', autoLog=None):

        BaseVisualStim.__init__(self, win, units=units, name=name,
                                autoLog=autoLog)
        self.win = win
        # first set params needed to create font (letter sizes etc)
        self.letterHeight = letterHeight
        # self._pixLetterHeight helps get font size right but not final layout
        self._pixLetterHeight = convertToPix((self.letterHeight,0), pos=(0,0),
                                             units=self.units, win=self.win)[0]
        if size is None:
            size = (defaultBoxWidth[units], -1)
        self.size = size  # the w,h of the text box (-1 means not constrained)
        self.bold = bold
        self.italic = italic
        self.glFont = None  # will be set by the self.font attribute setter
        self.font = font
        # once font is set up we can set the shader (depends on rgb/a of font)
        if self.glFont.atlas.format == 'rgb':
            global rgbShader
            self.shader = rgbShader = shaders.Shader(
                shaders.vertSimple, shaders.fragTextBox2)
        else:
            global alphaShader
            self.shader = alphaShader = shaders.Shader(
                shaders.vertSimple, shaders.fragTextBox2alpha)
        # params about positioning
        self.anchor = anchor  # 'center', 'top_left', 'bottom-center'...
        self._needVertexUpdate = False  # this will be set True during layout
        # standard stimulus params
        self.pos = pos
        self.color = color
        self.colorSpace = colorSpace
        self.opacity = opacity
        self._indices = None
        self._colors = None
        self.nChars = None  # len(text) can be more (if including format codes)

        self.flipHoriz = flipHoriz
        self.flipVert = flipVert
        self.text = text  # setting this triggers a _layout() call so do last

    @attributeSetter
    def font(self, fontName, italic=False, bold=False):
        if isinstance(fontName, GLFont):
            self.glFont = fontName
            self.__dict__['font'] = fontName.name
        else:
            self.__dict__['font'] = fontName
            self.glFont = allFonts.getFont(fontName, size=self._pixLetterHeight,
                                           bold=self.bold, italic=self.italic)

    @attributeSetter
    def anchor(self, anchor):
        """anchor is a string of terms, top, bottom, left, right, center

        e.g. 'top_center', 'center-right', 'topleft', 'center' are all valid"""
        self.__dict__['anchor'] = anchor
        # look for unambiguous terms first (top, bottom, left, right)
        self._anchorY = None
        self._anchorX = None
        if 'top' in anchor:
            self._anchorY = 'top'
        elif 'bottom' in anchor:
            self._anchorY = 'bottom'
        if 'right' in anchor:
            self._anchorX = 'right'
        elif 'left' in anchor:
            self._anchorX = 'left'
        # then 'center' can apply to either axis that isn't already set
        if self._anchorX is None:
            self._anchorX = 'center'
        if self._anchorY is None:
            self._anchorY = 'center'


    @attributeSetter
    def text(self, text):
        self.__dict__['text'] = text
        self._layout()

    def _layout(self):
        """Layout the text, calculating the vertex locations
        """
        text = self.text
        text = text.replace('<i>', codes['ITAL_START'])
        text = text.replace('<\i>', codes['ITAL_END'])
        text = text.replace('<b>', codes['BOLD_START'])
        text = text.replace('<\b>', codes['BOLD_END'])
        color = self.color
        font = self.glFont

        # the vertices are initially pix (natural for freetype)
        # then we convert them to the requested units for self._vertices
        # then they are converted back during rendering using standard BaseStim
        vertices = np.zeros((len(text) * 4, 2), dtype=np.float32)
        self._indices = np.zeros((len(text) * 6), dtype=np.uint)
        self._colors = np.zeros((len(text) * 4, 4), dtype=np.float32)
        self._texcoords = np.zeros((len(text) * 4, 2), dtype=np.float32)
        pen = [0, 0]
        prev = None
        fakeItalic = 0.0
        fakeBold = 0.0
        nChars = -1
        # for some reason glyphs too wide when using alpha channel only
        if font.atlas.format == 'alpha':
            alphaCorrection = 1 / 3.0
        else:
            alphaCorrection = 1

        for i, charcode in enumerate(text):
            if charcode in codes.values():
                if charcode == codes['ITAL_START']:
                    fakeItalic = 0.1 * font.size
                elif charcode == codes['ITAL_END']:
                    fakeItalic = 0.0
                elif charcode == codes['BOLD_START']:
                    fakeBold = 0.3 * font.size
                elif charcode == codes['BOLD_END']:
                    pen[0] -= fakeBold / 2  # we expected bigger pen move so cut
                    fakeBold = 0.0
                continue
            nChars += 1
            glyph = font[charcode]
            # kerning = glyph.get_kerning(prev)
            xBotL = pen[0] + glyph.offset[0] - fakeItalic - fakeBold / 2
            xTopL = pen[0] + glyph.offset[0] - fakeBold / 2
            yTop = pen[1] + glyph.offset[1]
            xBotR = xBotL + glyph.size[0] * alphaCorrection + fakeBold
            xTopR = xTopL + glyph.size[0] * alphaCorrection + fakeBold
            yBot = yTop - glyph.size[1]
            u0 = glyph.texcoords[0]
            v0 = glyph.texcoords[1]
            u1 = glyph.texcoords[2]
            v1 = glyph.texcoords[3]

            index = i * 4
            indices = [index, index + 1, index + 2, index, index + 2, index + 3]
            theseVertices = [[xTopL, yTop], [xBotL, yBot],  # for this letter
                             [xBotR, yBot], [xTopR, yTop]]
            texcoords = [[u0, v0], [u0, v1],
                         [u1, v1], [u1, v0]]

            vertices[i * 4:i * 4 + 4] = theseVertices
            self._indices[i * 6:i * 6 + 6] = indices
            self._texcoords[i * 4:i * 4 + 4] = texcoords
            self._colors[i * 4:i * 4 + 4] = color
            pen[0] = pen[0] + glyph.advance[0] + fakeBold / 2  # + kerning
            pen[1] = pen[1] + glyph.advance[1]
            prev = charcode

        self.nChars = nChars
        width = pen[0] - glyph.advance[0] + glyph.size[0] * alphaCorrection

        if self._anchorY == 'top':
            dy = -round(font.ascender)  # TODO: so far this is only for 1 line
        elif self._anchorY == 'center':
            dy = +round(-font.height / 2 - font.descender)
        elif self._anchorY == 'bottom':
            dy = -round(font.descender)
        else:
            dy = 0

        if self._anchorX == 'right':
            dx = -width / 1.0
        elif self._anchorX == 'center':
            dx = -width / 2.0
        else:  # left is what happens automatically
            dx = 0
        vertices += (round(dx), round(dy))

        self.vertices = vertices * self.letterHeight / self._pixLetterHeight
        # if we had to add more glyphs to make possible then 
        if self.glFont._dirty:
            self.glFont.upload()
            self.glFont._dirty = False
        self._needVertexUpdate = True

    def draw(self):
        if self._needVertexUpdate:
            self._updateVertices()
        gl.glPushMatrix()
        self.win.setScale('pix')

        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.glFont.textureID)
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glDisable(gl.GL_DEPTH_TEST)

        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)

        gl.glVertexPointer(2, gl.GL_FLOAT, 0,
                           self.verticesPix)
        gl.glColorPointer(4, gl.GL_FLOAT, 0,
                          self._colors)
        gl.glTexCoordPointer(2, gl.GL_FLOAT, 0,
                             self._texcoords)

        self.shader.bind()
        self.shader.setInt('texture', 0)
        self.shader.setFloat('pixel', [1.0 / 512, 1.0 / 512])
        gl.glDrawElements(gl.GL_TRIANGLES, len(self._indices),
                          gl.GL_UNSIGNED_INT, self._indices)
        self.shader.unbind()
        gl.glDisableVertexAttribArray(1);
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)

        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        gl.glDisable(gl.GL_TEXTURE_2D)

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
