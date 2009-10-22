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

import optparse
import os
import os.path
import sys
import urllib

import gdata.youtube.service
import youtubedl

VIDEO_SEARCH_URL = 'http://gdata.youtube.com/feeds/api/' + \
    'videos?q=%s&max-results=10&v=2'

class Error(Exception):
  """LuckyTubes error."""
  pass

class SearchFailedError(Error):
  '''Search had no results.'''
  pass

def daemonize():
  """Detach this process from the terminal. Only works on 'nix.
  This function is
  Copyright  (C) 2005 Chad J. Schroeder
  From http://code.activestate.com/recipes/278731/

  In LuckyTubes, we don't bother closing file descriptors, we just
  want to detach from terminal.
  """
  def fork_once():
    """Fork the program, wrapping exceptions appropriately."""
    try:
      return os.fork()
    except OSError, ex:
      raise Error, "Couldn't daemonize: %s [%d]" % (ex.strerror, ex.errno)

  pid = fork_once()
  if pid == 0:
    os.setsid()
    pid = fork_once()

    if pid == 0:
      os.chdir('/')
    else:
      os._exit(0)
  else:
    os._exit(0)

  # Drop stdin, stdout, stderr.
  os.close(0)
  os.close(1)
  os.close(2)
  os.open(os.devnull, os.O_RDWR)
  os.dup2(0, 1)
  os.dup2(0, 2)


class LtDownloader(object):
  params = {}
  def to_stdout(self, message, skip_eol=False):
    print message

  def process_info(self, *args):
    pass


class LuckyTubes(object):
  """Handle to LuckyTubes "service"."""
  def __init__(self, quiet, cachedir, high_quality):
    """Inits LuckyTubes with options.
    
    Args:
      nofork: True iff we should remain in the foreground instead of forking.
      verbose: True iff we want chatty output indicating our progress.
      cachedir: path to LuckyTubes cache directory.
    """

    self.service = gdata.youtube.service.YouTubeService()
    self.extractor = youtubedl.YoutubeIE(LtDownloader())
    self.quiet = quiet
    self.cachedir = cachedir
    self.high_quality = high_quality

  def vprint(self, out):
    """Print only if not quiet."""
    if not self.quiet:
      print out

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
        self.vprint('Downloading %s' % video_filename)

        if self.quiet:
          daemonize()
          self.vprint('PID: %d' % os.getpid())

        urllib.urlretrieve(url, video_filename + '.part')
        os.rename(video_filename+'.part', video_filename)

      self.vprint('Converting ' + final_filename)

      if os.system('ffmpeg -i %s -vn -acodec copy %s' % (video_filename, final_filename)) != 0:
        return False
      else:
        os.remove(video_filename)
    # Make sure we didn't leave the full video in the cache last time
    # we fetched it.
    elif os.path.exists(video_filename):
      os.remove(video_filename)

    return True

  def get_watch_url(self, search_terms, racy=True):
    """Search for something on YouTube. "Feel lucky" -- return the
    first result.

    Args:
      search_terms: space-separated list to pass to YouTube search.
      racy: whether to include restricted ("racy") videos.

    Returns:
      YouTube result URL for the video (suitable for browsing or input
      to youtube-dl).
    """

    query = gdata.youtube.service.YouTubeVideoQuery()
    query.vq = search_terms
    query.orderby = 'relevance'

    if racy:
      query.racy = 'include'
    else:
      query.racy = 'exclude'

    feed = self.service.YouTubeQuery(query)
    try:
      return feed.entry[0].media.player.url
    except (IndexError, e):
      raise SearchFailedError(e)

  def extract_video_info(self, view_url):
    """Extract information for the given video for downloading and 
    labeling.

    Args:
      view_url: the URL for the video on YouTube (the one you browse to).

    Returns:
      Tuple (url, vid_id, title, ext) representing file URL, unique ID
        ID, simple video title, and extension for the video file,
        respectively.
    """
    info = self.extractor.extract(view_url)

    return (info['url'], info['id'], info['stitle'], info['ext'])

  def search_and_download(self, search_terms):
    view_url = self.get_watch_url(search_terms)
    self.download(view_url)

  def download(self, view_url):
    url, vid_id, simpletitle, ext = self.extract_video_info(view_url)

    if self.high_quality:
      url += '&fmt=18'
      final_ext = 'm4a'
    else:
      final_ext = 'mp3'

    self.vprint('Video URL: ' + url)
    basename = '%s%s_%s.' % (self.cachedir, simpletitle, vid_id)
    filename = basename+ext
    finalname = basename+final_ext

    # System default in Windows (and pray it adds to playlist!)
    if 'win' in sys.platform:
      player = 'start '
      # Show them the download.
      os.system('start ' + self.cachedir)
    else:
      # TODO: configurable player...
      player = 'amarok '

    if self.fetch_video(url, filename, finalname):
      os.system(player + finalname)
    else:  # assume we at least got FLV
      os.system(player + filename)


def main(argv):
  parser = optparse.OptionParser()
  parser.add_option('-u', '--url-only', '--search-only',
                    dest='url_only',
                    action='store_true',
                    help='Only print the URL to watch the video')
  parser.add_option('-q', '--quiet', dest='quiet', action='store_true',
                    help='Don\'t print any output')
  parser.add_option('-b', '--best', '--high-quality', dest='high_quality',
                    action='store_true', help='Use high-quality video')
  parser.add_option('-y', '--by-url', dest='by_url', action='store_true',
                    help='Don\'t search, just download by URL')
  parser.add_option('--cache', dest='cachedir',
      help='Directory to cache downloaded video/audio',
      default=os.path.expanduser(os.path.join('~', '.luckytubes', '')))

  (options, args) = parser.parse_args(argv)


  if not os.path.exists(options.cachedir):
    os.makedirs(options.cachedir)
    
  lt = LuckyTubes(quiet=options.quiet,
                  cachedir=options.cachedir,
                  high_quality=options.high_quality)

  terms = ' '.join(args)
  if options.url_only:
    print lt.get_watch_url(terms)
  elif options.by_url:
    lt.download(terms)
  else:
    lt.search_and_download(terms)

if __name__ == '__main__':
  if len(sys.argv) < 2:
    print "Usage: luckytubes.py <search terms>"
    print "Run with --help for options."
    sys.exit(1)
  main(sys.argv[1:])
