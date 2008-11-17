#!/usr/bin/python
import distutils.core
import py2exe

distutils.core.setup(name="LuckyTubes",
                     windows=["ltgui.py", "luckytubes.py", "youtubedl.py"])
