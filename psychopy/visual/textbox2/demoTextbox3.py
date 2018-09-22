#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
#
#  FreeType high-level python API - Copyright 2011-2015 Nicolas P. Rougier
#  Distributed under the terms of the new BSD license.
#
# -----------------------------------------------------------------------------


from psychopy import visual, core, event, logging

logging.console.setLevel(logging.DEBUG)
c = core.Clock()

from psychopy.visual.textbox2 import TextBox2, allFonts

import sys

win = visual.Window([800, 800], monitor='testMonitor')
logging.exp("{:.3f}: created window".format(c.getTime()))

text = u"<i>The quick<\i> brown <b>fox<\b> jumped"
text2 = u"Some text in Times"
loremIpsum = """Lorem Ipsum is simply dummy text of the printing and typesetting 
industry. Lorem Ipsum has been the industry's standard dummy text ever since 
the 1500s, when an unknown printer took a galley of type and scrambled it to 
make a type specimen book. It has survived not only five centuries, but also 
the leap into electronic typesetting, remaining essentially unchanged. It was 
popularised in the 1960s with the release of Letraset sheets containing Lorem 
Ipsum passages, and more recently with desktop publishing software like Aldus 
PageMaker including versions of Lorem Ipsum."""

fontSize = 36

# preload some chars into a font to see how long it takes
nChars = 256
arial = allFonts.getFont("Arial", fontSize)
logging.exp("{:.3f}: created font".format(c.getTime()))
arial.preload(nChars)
logging.exp("{:.3f}: preloaded {} chars".format(c.getTime(), nChars))
# arial.saveToCache()  # can't yet retrieve the font but it's interesting to see!

labels = []
x, y = 0, 0
#
txt2 = TextBox2(win, color=[0, 0, 0, 0], text=text, font='Arial',
                pos=(x, y), letterHeight=fontSize)
txt2.draw()

logging.exp("{:.3f}: drew TextBox Arial (preloaded)".format(c.getTime()))
txt2.text = "Lorem Ipsum"
txt2.pos += [0, fontSize]
txt2.draw()
logging.exp("{:.3f}: drew altered Arial text".format(c.getTime()))

txt3 = TextBox2(win, color=[0.5, 0, 0, 0], text='Xg', font='Times',
                pos=(-5, 5), letterHeight=2, units='degFlat',
                anchor='centre')
box = visual.Rect(win, pos=(-5, 5), width=5, height=2, units='cm')
box.draw()
txt3.draw()
win.flip()
event.waitKeys()
core.quit()
logging.exp("{:.3f}: drew TextBox Times (no preload)".format(c.getTime()))

stims = [txt2, box, txt3]
win.flip()
logging.exp("{:.3f}: ready".format(c.getTime(), len(labels)))
for frame in range(10):
    for stim in stims:
        stim.draw()

    win.flip()
logging.flush()
event.waitKeys()
