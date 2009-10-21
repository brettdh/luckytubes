# Create your views here.
from django.http import HttpResponse, HttpResponseRedirect, Http404

from django.core.cache import cache

import luckytubes

import re
import urlparse

lt = luckytubes.LuckyTubes(quiet=True, cachedir='/home/swolchok/.lturl',
                           high_quality=False)

# Mitigate funny business slightly.
lt.download = lt.search_and_download = None

# Don't let those pesky jokers on the Internet shove too much crap in the cache.
MAX_SEARCH_STRING_LENGTH = 230

MEMCACHED_BAD_CHARS = re.compile('[^a-zA-Z0-9_:-]')

def search(request):
  search_terms = request.path[1:].lower()
  search_terms = search_terms.replace('_', ' ').replace('-', ' ').split()
  normalized_search_string = ' '.join(search_terms)[:MAX_SEARCH_STRING_LENGTH]
  
  cache_key = MEMCACHED_BAD_CHARS.sub('_', ('lturl:%s' % normalized_search_string))
  print cache_key
  watch_url = cache.get(cache_key)
  if watch_url is None:
    try:
      watch_url = lt.get_watch_url(normalized_search_string)
      cache.set(cache_key, watch_url)
    except luckytubes.SearchFailedError:
      raise Http404

  return HttpResponseRedirect(watch_url)
