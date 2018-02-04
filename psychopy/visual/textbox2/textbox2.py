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

import OpenGL.GL as gl
import ctypes

from ..basevisual import BaseVisualStim, ColorMixin, ContainerMixin
from .fontmanager import FontManager, TextureAtlas, TextureFont
from ..shaders import Shader, fragTextBox2, vertTextBox2
#
# allFonts = FontManager(monospace_only = False)
#
shader = None


class TextBox2:
    def __init__(self, win, text, font, atlas, color=(1.0, 1.0, 1.0, 0.0),  x=0, y=0,
                 width=None, height=None, anchor_x='left', anchor_y='baseline',
                 shader = None):
        self.win = win
        self.text = text

        self.vertices = np.zeros((len(text)*4,3), dtype=np.float32)
        self.indices  = np.zeros((len(text)*6, ), dtype=np.uint)
        self.colors   = np.zeros((len(text)*4,4), dtype=np.float32)
        self.texcoords= np.zeros((len(text)*4,2), dtype=np.float32)
        self.attrib   = np.zeros((len(text)*4,1), dtype=np.float32)
        pen = [x,y]
        prev = None
        if shader is None:
            shader = Shader(vertTextBox2, fragTextBox2)
        self.shader = shader
        self.atlas = atlas
        self.font = font


        for i,charcode in enumerate(text):
            glyph = font[charcode]
            kerning = glyph.get_kerning(prev)
            x0 = pen[0] + glyph.offset[0] + kerning
            dx = x0-int(x0)
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
            vertices  = [[x0,y0,1],[x0,y1,1],[x1,y1,1], [x1,y0,1]]
            texcoords = [[u0,v0],[u0,v1],[u1,v1], [u1,v0]]
            colors    = [color,]*4

            self.vertices[i*4:i*4+4] = vertices
            self.indices[i*6:i*6+6] = indices
            self.texcoords[i*4:i*4+4] = texcoords
            self.colors[i*4:i*4+4] = colors
            self.attrib[i*4:i*4+4] = dx
            pen[0] = pen[0]+glyph.advance[0]/64.0 + kerning
            pen[1] = pen[1]+glyph.advance[1]/64.0
            prev = charcode

        width = pen[0]-glyph.advance[0]/64.0+glyph.size[0]

        if anchor_y == 'top':
            dy = -round(font.ascender)
        elif anchor_y == 'center':
            dy = +round(-font.height/2-font.descender)
        elif anchor_y == 'bottom':
            dy = -round(font.descender)
        else:
            dy = 0

        if anchor_x == 'right':
            dx = -width/1.0
        elif anchor_x == 'center':
            dx = -width/2.0
        else:
            dx = 0
        self.vertices += (round(dx), round(dy), 0)
        if self.font._dirty:
            self.atlas.upload()
            self.font._dirty = False

    def draw(self):
        gl.glPushMatrix()
        self.win.setScale('pix')

        gl.glEnable( gl.GL_TEXTURE_2D )
        gl.glDisable( gl.GL_DEPTH_TEST )

        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)

        gl.glVertexPointer(3, gl.GL_FLOAT, 0, self.vertices)

        gl.glColorPointer(4, gl.GL_FLOAT, 0, self.colors)
        gl.glTexCoordPointer(2, gl.GL_FLOAT, 0, self.texcoords)

        r,g,b = 0,0,0
        gl.glColor( 1, 0, 1, 1 )
        gl.glEnable( gl.GL_BLEND )
        #gl.glBlendFunc( gl.GL_CONSTANT_COLOR_EXT,  gl.GL_ONE_MINUS_SRC_COLOR )
        #gl.glBlendColor(r,g,b,1)
        gl.glBlendFunc( gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA )
        gl.glBlendColor( 1, 1, 1, 1 )

        gl.glEnableVertexAttribArray( 1 );
        gl.glVertexAttribPointer( 1, 1, gl.GL_FLOAT, gl.GL_FALSE, 0, self.attrib)

        self.shader.bind()
        self.shader.setInt('texture', 0)
        self.shader.setFloat('pixel', [1.0/512, 1.0/512])
        gl.glDrawElements(gl.GL_TRIANGLES, len(self.indices),
                          gl.GL_UNSIGNED_INT, self.indices)
        self.shader.unbind()
        gl.glDisableVertexAttribArray( 1 );
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable( gl.GL_TEXTURE_2D )
        gl.glDisable( gl.GL_BLEND )

        gl.glPopMatrix()