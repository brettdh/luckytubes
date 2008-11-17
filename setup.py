#!/usr/bin/python
import distutils.core
import py2exe

setup(name="LuckyTubes",
      windows=["ltgui.py", "luckytubes.py", "youtubedl.py"])
