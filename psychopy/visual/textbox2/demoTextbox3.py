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

win = visual.Window([800, 800], monitor='testMonitor')
logging.exp("{:.3f}: created window".format(c.getTime()))

text = u"<i>The quick</i> brown <b>fox</b> jumped"
text2 = u"Some text in Times"
loremIpsum = u"PsychoPy is an open-source Python application allowing you to run a supercali-fragilisticexpeilidocious wide range of neuroscience, psychology and psychophysics experiments. It’s a free, powerful alternative to Presentation™ or e-Prime™, written in Python (a free alternative to Matlab™ g)."

fontSize = 16
# preload some chars into a font to see how long it takes
nChars = 256
arial = allFonts.getFont("Arial", fontSize)
logging.exp("{:.3f}: created font".format(c.getTime()))
arial.preload(nChars)
logging.exp("{:.3f}: preloaded {} chars".format(c.getTime(), nChars))
# arial.saveToCache()  # can't yet retrieve the font but it's interesting to see!


txt1 = TextBox2(win, color=[0.5, 0, 0, 0], text='Toptastic', font='Times',
                pos=(-2, 2), letterHeight=2, units='deg',
                anchor='left')
box1 = visual.Rect(win, pos=txt1.pos, width=txt1.size[0], height=txt1.size[1],
                   units='deg', lineColor='blue')
print('box1 size', txt1.size)
box1.draw()
txt1.draw()

x, y = 0, 0
#
center = visual.Rect(win, width=2, height=2, units='pix')
center.draw()

txt2 = TextBox2(win, color=[0, 0, 0, 0], text=loremIpsum, font='Arial',
                pos=(x, y), anchor='center', size=(20, -1), units='cm',
                lineSpacing=1.1,
                letterHeight=1.)
print(txt2.size)
box2 = visual.Rect(win, width=txt2.size[0], height=txt2.size[1],
                   pos=txt2.pos, units='cm')
box2.draw()
txt2.draw()

logging.exp("{:.3f}: drew altered Arial text".format(c.getTime()))

win.flip()
logging.exp("{:.3f}: drew TextBox Times (no preload)".format(c.getTime()))

stims = [center, box1, txt1, box2, txt2, ]
win.flip()
for frame in range(1000):
    txt2.pos += 0.001
    for stim in stims:
        stim.draw()
    if event.getKeys():
        core.quit()

    win.flip()
logging.flush()
