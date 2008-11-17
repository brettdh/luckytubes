#!/usr/bin/python

# Copyright 2008 Scott Wolchok.
# This file is part of LuckyTubes.

# LuckyTubes is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# LuckyTubes is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with LuckyTubes.  If not, see <http://www.gnu.org/licenses/>.

"""LuckyTubes GUI -- thin wrapper for luckytubes.py"""

import threading

import wx

import luckytubes


VERSION = "0.1"

class FetchThread(threading.Thread):
  def __init__(self, ltargs, *args, **kwargs):
    threading.Thread.__init__(self, *args, **kwargs)
    self.ltargs = ltargs

  def run(self):
    luckytubes.main(self.ltargs)

class LtPanel(wx.Panel):
  def __init__(self, parent, *args, **kwargs):
    wx.Panel.__init__(self, parent, *args, **kwargs)

    # The search row.
    self.search_box = wx.TextCtrl(self, id=wx.ID_ANY, value='rickroll')
    search_button = wx.Button(self, id=wx.ID_ANY, label='Play it!')

    search_button.Bind(wx.EVT_BUTTON, self.run_lt)

    search_sizer = wx.BoxSizer(wx.HORIZONTAL)
    search_sizer.Add(self.search_box, flag=wx.EXPAND | wx.ALL, border=3,
                     proportion=1)
    search_sizer.Add(search_button, flag=wx.ALIGN_LEFT | wx.ALL, border=5)


        # Put it all together.
    top_sizer = wx.BoxSizer(wx.VERTICAL)
    for sizer in (search_sizer,):
      top_sizer.Add(sizer, flag=wx.ALIGN_CENTER, proportion=0)

    self.SetSizer(top_sizer)
    top_sizer.Fit(self)

  def run_lt(self, e):
    FetchThread([self.search_box.GetValue()]).start()


class LtMainFrame(wx.Frame):
  """Main frame of LtGUI (there's only one).

  This class is just boilerplate: menu bar, panel, etc.
  """
  def __init__(self, parent, id, title, pos=wx.DefaultPosition,
               size=(-1, 150)):
    wx.Frame.__init__(self, parent, id, title, pos, size)
    self.panel = LtPanel(self)

    self._setup_menu_bar()
    self.Show()

  def _setup_menu_bar(self):
    file_menu = wx.Menu()
    item = file_menu.Append(wx.ID_EXIT, "E&xit", "Terminate the program")
    self.Bind(wx.EVT_MENU, lambda e: self.Close(), item)

    help_menu = wx.Menu()
    item = help_menu.Append(wx.ID_ABOUT, "&About",
                            "Information about this program")
    self.Bind(wx.EVT_MENU, lambda e: self.show_about_box(), item)

    menu_bar = wx.MenuBar()
    menu_bar.Append(file_menu, "&File")
    menu_bar.Append(help_menu, "&Help")
    self.SetMenuBar(menu_bar)

  @staticmethod
  def show_about_box(self):
    """Show the about box."""
    info = wx.AboutDialogInfo()
    info.AddDeveloper("Scott Wolchok")
    info.SetCopyright("Copyright (C) Scott Wolchok 2008")
    info.SetVersion(VERSION)
    info.SetLicense(open("COPYING").read())
    wx.AboutBox(info)

def main():
  app = wx.App()
  app.SetAppName("LuckyTubes")
  frame = LtMainFrame(None, wx.ID_ANY, app.GetAppName())
  app.MainLoop()

if __name__ == "__main__":
  main()
