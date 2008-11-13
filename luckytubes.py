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

class LuckyTubes(object):
  def __init__(self):
    self.service = gdata.youtube.service.YouTubeService()
    self.extractor = youtubedl.YoutubeIE()

  def fetch_video(self, url, video_filename, final_filename):
    """Fetch the video at the given (YouTube) URL. Includes caching,
    extracting audio, etc.

    Args:
      url: A URL for an FLV to download.
      video_filename: Name of the video file.
      final_filename: Name of the resulting audio file.

    Returns:
      True if download and extract were successful, False otherwise.
    """
    if not os.path.exists(final_filename):
      if not os.path.exists(video_filename):
        print "Downloading " + video_filename
        # TODO: optional backgrounding
        pid = os.fork()
        if pid > 0:
          sys.exit(0)
        print "PID: %d" % os.getpid()
        urllib.urlretrieve(url, video_filename + ".part")
        os.rename(video_filename+".part", video_filename)

      print "Converting " + final_filename
      # TODO: Hide ffmpeg's output if we're backgrounding the fetch.
      if os.system("ffmpeg -i %s %s" % (video_filename, final_filename)) != 0:
        return False
      else:
        os.remove(video_filename)
    # Make sure we didn't leave the full video in the cache last time
    # we fetched it
    elif os.path.exists(video_filename):
        os.remove(video_filename)

    return True

  def lucky_search(self, search_terms, racy=True):
    """Search for something on YouTube. "Feel lucky" -- return the
    first result.

    Args:
      search_terms: space-separated list to pass to YouTube search.
      racy: whether to include restricted ("racy") videos.

    Returns:
      Tuple (url, vid_id, title, ext) representing file URL, unique ID
        ID, simple video title, and extension for the video file,
        respectively.
    """

    query = gdata.youtube.service.YouTubeVideoQuery()
    query.vq = search_terms
    query.orderby = 'relevance'

    if racy:
      query.racy = 'include'
    else:
      query.racy = 'exclude'

    feed = self.service.YouTubeQuery(query)
    info = self.extractor.extract(feed.entry[0].media.player.url)[0]

    return (info['url'], info['id'], info['stitle'], info['ext'])

  def search(self, search_terms):
    url, vid_id, simpletitle, ext = self.lucky_search(search_terms)
    print "Video URL: " + url
    basename = "%s%s_%s." % (CACHE,simpletitle,vid_id)
    filename = basename+ext
    finalname = basename+"mp3"

    if self.fetch_video(url, filename, finalname):
      os.system("amarok " + finalname)
    else:  # assume we at least got FLV
      os.system("amarok " + filename)


if __name__ == "__main__":
  if not os.path.exists(CACHE):
    os.makedirs(CACHE)
  # TODO: options
    
  LuckyTubes().search(' '.join(sys.argv[1:]))
