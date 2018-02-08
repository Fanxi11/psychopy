#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
#
#  FreeType high-level python API - Copyright 2011-2015 Nicolas P. Rougier
#  Distributed under the terms of the new BSD license.
#
# -----------------------------------------------------------------------------
# Shader compilation code
# -----------------------------------------------------------------------------
#
# Copyright Tristam Macdonald 2008.
#
# Distributed under the Boost Software License, Version 1.0
# (see http://www.boost.org/LICENSE_1_0.txt)
#

import sys, os
import math
import numpy as np
import freetype as ft
import OpenGL.GL as gl
import ctypes
import glob

from psychopy.constants import PY3
if PY3:
    unichr = chr

font_family_aliases = set([
        'serif',
        'sans-serif',
        'sans serif',
        'cursive',
        'fantasy',
        'monospace',
        'sans'])

#  OS Font paths
X11FontDirectories  = [
    # an old standard installation point
    "/usr/X11R6/lib/X11/fonts/TTF/",
    "/usr/X11/lib/X11/fonts",
    # here is the new standard location for fonts
    "/usr/share/fonts/",
    # documented as a good place to install new fonts
    "/usr/local/share/fonts/",
    # common application, not really useful
    "/usr/lib/openoffice/share/fonts/truetype/",
    ]

OSXFontDirectories = [
    "/Library/Fonts/",
    "/Network/Library/Fonts/",
    "/System/Library/Fonts/",
    # fonts installed via MacPorts
    "/opt/local/share/fonts"
    ""
]


class _TextureAtlas:
    """ A TextureAtlas is the texture used by the GLFont to store the glyphs

    Group multiple small data regions into a larger texture.

    The algorithm is based on the article by Jukka Jylänki : "A Thousand Ways
    to Pack the Bin - A Practical Approach to Two-Dimensional Rectangle Bin
    Packing", February 27, 2010. More precisely, this is an implementation of
    the Skyline Bottom-Left algorithm based on C++ sources provided by Jukka
    Jylänki at: http://clb.demon.fi/files/RectangleBinPack/

    Example usage:
    --------------

    atlas = TextureAtlas(512,512,3)
    region = atlas.get_region(20,20)
    ...
    atlas.set_region(region, data)
    """

    def __init__(self, width=1024, height=1024, format='alpha'):
        """
        Initialize a new atlas of given size.

        Parameters
        ----------

        width : int
            Width of the underlying texture

        height : int
            Height of the underlying texture

        format : 'alpha' or 'rgb'
            Depth of the underlying texture
        """
        self.width = int(math.pow(2, int(math.log(width, 2) + 0.5)))
        self.height = int(math.pow(2, int(math.log(height, 2) + 0.5)))
        self.format = format
        self.nodes = [(0,0,self.width),]
        self.textureID = 0
        self.used = 0
        if format == 'rgb':
            self.data = np.zeros((self.height, self.width, 3),
                                 dtype=np.ubyte)
        elif format == 'alpha':
            self.data = np.zeros((self.height, self.width),
                                 dtype=np.ubyte)
        else:
            raise TypeError("TextureAtlas should have format of 'alpha' or "
                            "'rgb' not {}".format(repr(format)))

    def upload(self):
        """
        Upload atlas data into video memory.
        """
        if not self.textureID:
            self.textureID = gl.glGenTextures(1)

        gl.glBindTexture( gl.GL_TEXTURE_2D, self.textureID )
        gl.glTexParameteri( gl.GL_TEXTURE_2D,
                            gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP )
        gl.glTexParameteri( gl.GL_TEXTURE_2D,
                            gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP )
        gl.glTexParameteri( gl.GL_TEXTURE_2D,
                            gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR )
        gl.glTexParameteri( gl.GL_TEXTURE_2D,
                            gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR )
        if self.format == 'alpha':
            gl.glTexImage2D( gl.GL_TEXTURE_2D, 0, gl.GL_ALPHA,
                             self.width, self.height, 0,
                             gl.GL_ALPHA, gl.GL_UNSIGNED_BYTE, self.data )
        else:
            gl.glTexImage2D( gl.GL_TEXTURE_2D, 0, gl.GL_RGB,
                             self.width, self.height, 0,
                             gl.GL_RGB, gl.GL_UNSIGNED_BYTE, self.data )

    def set_region(self, region, data):
        """
        Set a given region width provided data.

        Parameters
        ----------

        region : (int,int,int,int)
            an allocated region (x,y,width,height)

        data : numpy array
            data to be copied into given region
        """

        x, y, width, height = region
        if self.format=='rgb':
            self.data[int(y):int(y+height),int(x):int(x+width), :] = data
        else:
            self.data[int(y):int(y+height),int(x):int(x+width)] = data

    def get_region(self, width, height):
        """
        Get a free region of given size and allocate it

        Parameters
        ----------

        width : int
            Width of region to allocate

        height : int
            Height of region to allocate

        Return
        ------
            A newly allocated region as (x,y,width,height) or (-1,-1,0,0)
        """

        best_height = sys.maxsize
        best_index = -1
        best_width = sys.maxsize
        region = 0, 0, width, height

        for i in range(len(self.nodes)):
            y = self.fit(i, width, height)
            if y >= 0:
                node = self.nodes[i]
                if (y+height < best_height or
                    (y+height == best_height and node[2] < best_width)):
                    best_height = y+height
                    best_index = i
                    best_width = node[2]
                    region = node[0], y, width, height

        if best_index == -1:
            return -1,-1,0,0

        node = region[0], region[1]+height, width
        self.nodes.insert(best_index, node)

        i = best_index+1
        while i < len(self.nodes):
            node = self.nodes[i]
            prev_node = self.nodes[i-1]
            if node[0] < prev_node[0]+prev_node[2]:
                shrink = prev_node[0]+prev_node[2] - node[0]
                x,y,w = self.nodes[i]
                self.nodes[i] = x+shrink, y, w-shrink
                if self.nodes[i][2] <= 0:
                    del self.nodes[i]
                    i -= 1
                else:
                    break
            else:
                break
            i += 1

        self.merge()
        self.used += width*height
        return region

    def fit(self, index, width, height):
        """
        Test if region (width,height) fit into self.nodes[index]

        Parameters
        ----------

        index : int
            Index of the internal node to be tested

        width : int
            Width or the region to be tested

        height : int
            Height or the region to be tested

        """

        node = self.nodes[index]
        x,y = node[0], node[1]
        width_left = width

        if x+width > self.width:
            return -1

        i = index
        while width_left > 0:
            node = self.nodes[i]
            y = max(y, node[1])
            if y+height > self.height:
                return -1
            width_left -= node[2]
            i += 1
        return y

    def merge(self):
        """
        Merge nodes
        """

        i = 0
        while i < len(self.nodes)-1:
            node = self.nodes[i]
            next_node = self.nodes[i+1]
            if node[1] == next_node[1]:
                self.nodes[i] = node[0], node[1], node[2]+next_node[2]
                del self.nodes[i+1]
            else:
                i += 1


class GLFont:
    """
    A GLFont gathers a set of glyphs for a given font filename and size.
    """

    def __init__(self, filename, size, textureSize=1024):
        """
        Initialize font

        Parameters:
        -----------

        atlas: TextureAtlas
            Texture atlas where glyph texture will be stored
        
        filename: str
            Font filename

        size : float
            Font size
        """
        self.atlas = _TextureAtlas(textureSize, textureSize, format='alpha')
        self.filename = filename
        self.size = size
        self.glyphs = {}
        face = ft.Face( self.filename )
        face.set_char_size( int(self.size*64))
        self._dirty = False
        metrics = face.size
        self.ascender  = metrics.ascender/64.0
        self.descender = metrics.descender/64.0
        self.height    = metrics.height/64.0
        self.linegap   = self.height - self.ascender + self.descender
        self.format = self.atlas.format

    def __getitem__(self, charcode):
        """
        x.__getitem__(y) <==> x[y]
        """
        if charcode not in self.glyphs.keys():
            self.load('%c' % charcode)
        return self.glyphs[charcode]


    @property
    def textureID(self):
        """
        Get underlying texture identity .
        """

        if self._dirty:
            self.atlas.upload()
        self._dirty = False
        return self.atlas.textureID

    def preloadAll(self, nMax=None):
        """
        :return:
        """
        face = ft.Face( self.filename)
        
        n = 0
        chrs = list(face.get_chars())
        for c in chrs:
            if nMax is not None and n>nMax:
                break
            
            self.load(unichr(c[1]), face=face)

    def load(self, charcodes = '', face=None):
        """
        Build glyphs corresponding to individual characters in charcodes.

        Parameters:
        -----------

        charcodes: [str | unicode]
            Set of characters to be represented
        """
        if face is None:
            face = ft.Face( self.filename )
        pen = ft.Vector(0,0)
        hres = 16*72
        hscale = 1.0/16

        for charcode in charcodes:
            if charcode in self.glyphs.keys():
                continue
            face.set_char_size( int(self.size * 64), 0, hres, 72 )
            matrix = ft.Matrix( int((hscale) * 0x10000), int((0.0) * 0x10000),
                             int((0.0)    * 0x10000), int((1.0) * 0x10000) )
            face.set_transform( matrix, pen )

            self._dirty = True
            flags = ft.FT_LOAD_RENDER | ft.FT_LOAD_FORCE_AUTOHINT
            flags |= ft.FT_LOAD_TARGET_LCD

            face.load_char( charcode, flags )
            bitmap = face.glyph.bitmap
            left   = face.glyph.bitmap_left
            top    = face.glyph.bitmap_top
            width  = face.glyph.bitmap.width
            rows   = face.glyph.bitmap.rows
            pitch  = face.glyph.bitmap.pitch

            if self.format=='rgb':
                x, y, w, h = self.atlas.get_region(width/5, rows + 2)
            else:
                x, y, w, h = self.atlas.get_region(width+2, rows+2)

            if x < 0:
                print ('Missed !')
                continue
            x,y = x+1, y+1
            w,h = w-2, h-2
            data = []
            for i in range(rows):
                data.extend(bitmap.buffer[i*pitch:i*pitch+width])
            if self.format == 'rgb':
                data = np.array(data, dtype=np.ubyte).reshape(
                    int(h), int(w), 3)
            else:
                data = np.array(data, dtype=np.ubyte).reshape(
                    int(h), int(w))

            if self.format == 'rgb':
                Z = (((data/255.0)**1.5)*255).astype(np.ubyte)
            self.atlas.set_region((x,y,w,h), data)

            # Build glyph
            size = w, h
            offset = left, top
            advance = face.glyph.advance.x, face.glyph.advance.y

            u0 = (x + 0.0)/float(self.atlas.width)
            v0 = (y + 0.0)/float(self.atlas.height)
            u1 = (x + w - 0.0)/float(self.atlas.width)
            v1 = (y + h - 0.0)/float(self.atlas.height)
            texcoords = (u0, v0, u1, v1)
            glyph = TextureGlyph(charcode, size, offset, advance, texcoords)
            self.glyphs[charcode] = glyph

            # Generate kerning
            for g in self.glyphs.values():
                # 64 * 64 because of 26.6 encoding AND the transform matrix used
                # in texture_font_load_face (hres = 64)
                kerning = face.get_kerning(g.charcode, charcode,
                                           mode=ft.FT_KERNING_UNFITTED)
                if kerning.x != 0:
                    glyph.kerning[g.charcode] = kerning.x/(64.0*64.0)
                kerning = face.get_kerning(charcode, g.charcode,
                                           mode=ft.FT_KERNING_UNFITTED)
                if kerning.x != 0:
                    g.kerning[charcode] = kerning.x/(64.0*64.0)


class TextureGlyph:
    """
    A texture glyph gathers information relative to the size/offset/advance and
    texture coordinates of a single character. It is generally built
    automatically by a TextureFont.
    """

    def __init__(self, charcode, size, offset, advance, texcoords):
        """
        Build a new texture glyph

        Parameter:
        ----------

        charcode : char
            Represented character

        size: tuple of 2 ints
            Glyph size in pixels

        offset: tuple of 2 floats
            Glyph offset relatively to anchor point

        advance: tuple of 2 floats
            Glyph advance

        texcoords: tuple of 4 floats
            Texture coordinates of bottom-left and top-right corner
        """
        self.charcode = charcode
        self.size = size
        self.offset = offset
        self.advance = advance
        self.texcoords = texcoords
        self.kerning = {}


    def get_kerning(self, charcode):
        """ Get kerning information

        Parameters:
        -----------

        charcode: char
            Character preceding this glyph
        """
        if charcode in self.kerning.keys():
            return self.kerning[charcode]
        else:
            return 0


def findSystemFonts():
    """Returns a list of available font names in the system folders

    :return: list of strings
    """
    if sys.platform == 'win32':
        # for windows matplotlib uses windows registry to find folder
        from matplotlib import font_manager
        return font_manager.findSystemFonts()
    elif sys.platform == 'darwin':
        # on mac matplotlib doesn't include 'ttc' files (which are fine)
        paths = OSXFontDirectories
    elif sys.platform.startswith('linux'):
        paths = X11FontDirectories
    fontPaths = []
    for thisFolder in paths:
        for thisExt in ['ttf', 'otf', 'ttc', 'dfont']:
            fontPaths.extend(glob.glob("{}{}*.{}".format(
                thisFolder, os.path.sep, thisExt)))
    return fontPaths


def getIdFromArgs(fontInfo, size, bold, italic):
    """Generate a string identifier for this font/size to store in font dict

    :param fontInfo: FontInfo class from FontManager.getFontsMatching()
    :param size:
    :param dpi:
    :return: a string
    """
    flags=""
    if bold:
        flags += "_bold"
    if italic:
        flags += "_italic"
    return "%s_%d%s" % (fontInfo.getID(), size, flags)


class FontManager(object):
    """FontManager provides a simple API for finding and loading font files
    (.ttf) via the FreeType lib

    The FontManager finds supported font files on the computer and
    initially creates a dictionary containing the information about
    available fonts. This can be used to quickly determine what font family
    names are available on the computer and what styles (bold, italic) are
    supported for each family.

    This font information can then be used to create the resources necessary
    to display text using a given font family, style, size, color, and dpi.

    The FontManager is currently used by the psychopy.visual.TextBox stim
    type. A user script can access the FontManager via:

    fonts = visual.textbox2.getFontManager()

    A user script never creates an instance of the FontManager class and
    should always access it using visual.textbox.getFontManager().

    Once a font of a given size and dpi has been created; it is cached by the
    FontManager and can be used by all TextBox instances created within the
    experiment.

    """
    freetype_import_error = None
    fontDict = {}
    fontStyles = []
    _available_fontInfo = {}

    def __init__(self, monospaceOnly=False):
        # if FontManager.freetype_import_error:
        #    raise Exception('Appears the freetype library could not load.
        #       Error: %s'%(str(FontManager.freetype_import_error)))

        self.monospaceOnly = monospaceOnly
        self.updateFontInfo(monospaceOnly)

    def getFontFamilyNames(self):
        """Returns a list of the available font family names.
        """
        return list(self._available_fontInfo.keys())

    def getFontStylesForFamily(self, family_name):
        """For the given family_name, a list of style names supported is
        returned.
        """
        style_dict = self._available_fontInfo.get(family_name)
        if style_dict:
            return list(style_dict.keys())

    def getFontFamilyStyles(self):
        """Returns a list where each element of the list is a itself a
        two element list of [fontName,[fontStyle_names_list]]
        """
        return self.fontStyles

    def getFontsMatching(self, fontName, bold=False, italic=False,
                         fontStyle=None):
        """
        Returns the list of FontInfo instances that match the provided
        fontName and style information. If no matching fonts are
        found, None is returned.
        """
        style_dict = self._available_fontInfo.get(fontName)
        if style_dict is None:
            return None
        if fontStyle and fontStyle in style_dict:
            return style_dict[fontStyle]
        for style, fonts in style_dict.items():
            b, i = self.booleansFromStyleName(style)
            if b == bold and i == italic:
                return fonts
        return None

    def addFontFile(self, fontPath, monospaceOnly=False):
        """
        Add a Font File to the FontManger font search space. The
        fontPath must be a valid path including the font file name.
        Relative paths can be used, with the current working directory being
        the origin.

        If monospaceOnly is True, the font file will only be added if it is a
        monospace font (as only monospace fonts are currently supported by
        TextBox).

        Adding a Font to the FontManager is not persistent across runs of
        the script, so any extra font paths need to be added each time the
        script starts.
        """
        return self.addFontFiles((fontPath,), monospaceOnly)

    def addFontFiles(self, fontPaths, monospaceOnly=False):
        """ Add a list of font files to the FontManger font search space.
        Each element of the fontPaths list must be a valid path including
        the font file name. Relative paths can be used, with the current
        working directory being the origin.

        If monospaceOnly is True, each font file will only be added if it is
        a monospace font (as only monospace fonts are currently supported by
        TextBox).

        Adding fonts to the FontManager is not persistent across runs of
        the script, so any extra font paths need to be added each time the
        script starts.
        """

        fi_list = []
        for fp in fontPaths:
            if os.path.isfile(fp) and os.path.exists(fp):
                face = ft.Face(fp)
                if monospaceOnly:
                    if face.is_fixed_width:
                        fi_list.append(self._createFontInfo(fp, face))
                else:
                    fi_list.append(self._createFontInfo(fp, face))

        self.fontStyles.sort()

        return fi_list

    def addFontDirectory(self, fontDir, monospaceOnly=False, recursive=False):
        """
        Add any font files found in fontDir to the FontManger font search
        space. Each element of the fontPaths list must be a valid path
        including the font file name. Relative paths can be used, with the
        current working directory being the origin.

        If monospaceOnly is True, each font file will only be added if it is
        a monospace font (as only monospace fonts are currently supported by
        TextBox).

        Adding fonts to the FontManager is not persistant across runs of
        the script, so any extra font paths need to be added each time the
        script starts.
        """

        from os import walk

        fontPaths = []
        for (dirpath, dirnames, filenames) in walk(fontDir):
            ttf_files = [os.path.join(dirpath, fname)
                         for fname in filenames
                         if fname.lower().endswith('.ttf')]
            fontPaths.extend(ttf_files)
            if not recursive:
                break

        return self.addFontFiles(fontPaths)

        return fi

    # Class methods for FontManager below this comment should not need to be
    # used by user scripts in most situations. Accessing them is okay.

    def getGLFont(self, name, size=32, bold=False, italic=False,
                  monospace=False):
        """
        Return a FontAtlas object that matches the family name, style info,
        and size provided. FontAtlas objects are cached, so if multiple
        TextBox instances use the same font (with matching font properties)
        then the existing FontAtlas is returned. Otherwise, a new FontAtlas is
        created , added to the cache, and returned.
        """
        fontInfos = self.getFontsMatching(name, bold, italic)
        if len(fontInfos) == 0:
            return False
        fontInfo = fontInfos[0]
        fid = getIdFromArgs(fontInfo, size, bold, italic)
        glFont = self.fontDict.get(fid)
        if glFont is None:
            glFont = GLFont(fontInfo.path, size)
            glFont = self.fontDict.setdefault(fid, glFont)  # gets

        return glFont

    def getFontInfo(self, refresh=False, monospace=False):
        """
        Returns the available font information as a dict of dict's.
        The first level dict has keys for the available font families.
        The second level dict has keys for the available styles of the
        associated font family. The values in the second level font
        family - style dict are each a list containing FontInfo objects.
        There is one FontInfo object for each physical font file found that
        matches the associated font family and style.
        """
        if refresh or not self._available_fontInfo:
            self.updateFontInfo(monospace)
        return self._available_fontInfo

    def updateFontInfo(self, monospaceOnly=False):
        self._available_fontInfo.clear()
        del self.fontStyles[:]
        fonts_found = findSystemFonts()
        self.addFontFiles(fonts_found, monospaceOnly)

    def booleansFromStyleName(self, style):
        """
        For the given style name, return a
        bool indicating if the font is bold, and a second indicating
        if it is italics.
        """
        italic = False
        bold = False
        s = style.lower().strip()
        if s == 'regular':
            return False, False
        if s.find(b'italic') >= 0 or s.find(b'oblique') >= 0:
            italic = True
        if s.find(b'bold') >= 0:
            bold = True
        return bold, italic

    def _createFontInfo(self, fp, fface):
        fns = (fface.family_name, fface.style_name)
        if fns in self.fontStyles:
            pass
        else:
            self.fontStyles.append(
                (fface.family_name, fface.style_name))

        styles_for_font_dict = self._available_fontInfo.setdefault(
            fface.family_name, {})
        fonts_for_style = styles_for_font_dict.setdefault(fface.style_name, [])
        fi = FontInfo(fp, fface)
        fonts_for_style.append(fi)
        return fi

    def __del__(self):
        self.font_store = None
        if self.fontDict:
            self.fontDict.clear()
            self.fontDict = None
        if self._available_fontInfo:
            self._available_fontInfo.clear()
            self._available_fontInfo = None


class FontInfo(object):

    def __init__(self, fp, face):
        self.path = fp
        self.family_name = face.family_name
        self.style_name = face.style_name
        self.charmaps = [charmap.encoding_name for charmap in face.charmaps]
        self.num_faces = face.num_faces
        self.num_glyphs = face.num_glyphs
        #self.size_info= [dict(width=s.width,height=s.height,
        #    x_ppem=s.x_ppem,y_ppem=s.y_ppem) for s in face.available_sizes]
        self.units_per_em = face.units_per_EM
        self.monospace = face.is_fixed_width
        self.charmap_id = face.charmap.index
        self.label = "%s_%s" % (face.family_name, face.style_name)
        self.id = self.label

    def getID(self):
        return self.id

    def asdict(self):
        d = {}
        for k, v in self.__dict__.items():
            if k[0] != '_':
                d[k] = v
        return d
