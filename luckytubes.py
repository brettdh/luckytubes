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

"""LuckyTubes -- play music off YouTube by feeling lucky!"""

import os
import os.path
import sys
import urllib
import youtubedl

import gdata.youtube.service

CACHE=os.path.join(os.environ["HOME"],".luckytubes" + os.sep)
VIDEO_SEARCH_URL="http://gdata.youtube.com/feeds/api/videos?q=%s&max-results=10&v=2"

# TODO: Package the code into a class instead of icky globals
service = gdata.youtube.service.YouTubeService()
ex = youtubedl.YoutubeIE()

def search(vidname):
    query = gdata.youtube.service.YouTubeVideoQuery()
    query.vq = vidname
    query.orderby = 'relevance'
    query.racy = 'include'
    feed = service.YouTubeQuery(query)
    info = ex.extract(feed.entry[0].media.player.url)[0]
    url = info['url']
    vid_id = info['id']
    simpletitle = info['stitle']
    ext = info['ext']

    print "Video URL: " + feed.entry[0].media.player.url
    basename = "%s%s_%s." % (CACHE,simpletitle,vid_id)
    filename = basename+ext
    finalname = basename+"mp3"
#    print [x.url for x in feed.entry[0].media.content if 'rtsp' in x.url]
#    return
    finalOK = True
    if not os.path.exists(finalname):
      if not os.path.exists(filename):
        print "Downloading " + filename
        # TODO: optional backgrounding
        pid = os.fork()
        if pid > 0:
          sys.exit(0)
        print "PID: %d" % os.getpid()
        urllib.urlretrieve(url, filename + ".part")
        os.rename(filename+".part", filename)

      print "Converting " + finalname
      # TODO: Hide ffmpeg's output if we're backgrounding the fetch.
      if os.system("ffmpeg -i %s %s" % (filename, finalname)) != 0:
        finalOK = False
      else:
        os.remove(filename)
    # Make sure we didn't leave the full video in the cache last time
    # we fetched it
    elif os.path.exists(filename):
        os.remove(filename)
    
    if finalOK:
      os.system("amarok " + finalname)
    else:
      os.system("amarok " + filename)


if __name__ == "__main__":
  if not os.path.exists(CACHE):
    os.makedirs(CACHE)
  # TODO: options
  search(' '.join(sys.argv[1:]))
