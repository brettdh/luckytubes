#!/usr/bin/python
"""LuckyTubes -- play music off YouTube by feeling lucky!"""

import os
import os.path
import sys
import urllib
import youtubedl

import gdata.youtube.service

CACHE=os.path.join(os.environ["HOME"],".luckytubes")
VIDEO_SEARCH_URL="http://gdata.youtube.com/feeds/api/videos?q=%s&max-results=10&v=2"

# TODO: Package the code into a class instead of icky globals
service = gdata.youtube.service.YouTubeService()
ex = youtubedl.YoutubeIE()

# Debugging code from YouTube API site for playing with the feed.
def PrintEntryDetails(entry):
  print dir(entry.media)
  print 'Video title: %s' % entry.media.title.text
  print 'Video published on: %s ' % entry.published.text
  print 'Video description: %s' % entry.media.description.text
  print 'Video category: %s' % entry.media.category[0].text
  print 'Video tags: %s' % entry.media.keywords.text
  print 'Video watch page: %s' % entry.media.player.url
  print 'Video flash player URL: %s' % entry.GetSwfUrl()
  content_urls = [x.url for x in entry.media.content if x.medium == 'video']
  print 'Video Content: %s' % content_urls
  print 'Video duration: %s' % entry.media.duration.seconds

  # non entry.media attributes
  print 'Video view count: %s' % entry.statistics.view_count
  print 'Video rating: %s' % entry.rating.average

  # show alternate formats
  for alternate_format in entry.media.content:
    if 'isDefault' not in alternate_format.extension_attributes:
      print 'Alternate format: %s | url: %s ' % (alternate_format.type,
                                                 alternate_format.url)

  # show thumbnails
  for thumbnail in entry.media.thumbnail:
    print 'Thumbnail url: %s' % thumbnail.url

def search(vidname):
    query = gdata.youtube.service.YouTubeVideoQuery()
    query.vq = vidname
    query.orderby = 'relevance'
    query.racy = 'include'
    feed = service.YouTubeQuery(query)
    info = ex.extract(feed.entry[0].media.player.url)[0]
    url = info['url']
    id = info['id']
    simpletitle = info['stitle']
    ext = info['ext']

    print "Video URL: " + feed.entry[0].media.player.url
    basename = "%s%s_%s." % (CACHE,simpletitle,id)
    filename = basename+ext
    finalname = basename+"mp3"
#    print [x.url for x in feed.entry[0].media.content if 'rtsp' in x.url]
#    return
    finalOK = True
    if not os.path.exists(finalname):
      # TODO: check if it actually finished downloading
      # (Firefox-like file.part + mv file.part file should do)
      if not os.path.exists(filename):
        print "Downloading " + filename
        # TODO: optional backgrounding
        pid = os.fork()
        if pid > 0:
          sys.exit(0)
        print "PID: %d" % os.getpid()
        urllib.urlretrieve(url, filename)[0]

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
  # TODO: options
  search(' '.join(sys.argv[1:]))
