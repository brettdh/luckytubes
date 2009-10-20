# Create your views here.
from django.http import HttpResponse, HttpResponseRedirect, Http404

from lturl.yturl.models import Search

import luckytubes

import urlparse

lt = luckytubes.LuckyTubes(quiet=True, cachedir='/home/swolchok/.lturl',
                           high_quality=False)

# Mitigate funny business slightly.
lt.download = lt.search_and_download = None


def search(request):
  search_terms = request.path[1:].lower()
  search_terms = search_terms.replace('_', ' ').replace('-', ' ').split()
  normalized_search_string = ' '.join(search_terms)
  
  try:
    result = Search.objects.get(keywords=normalized_search_string)
  except Search.DoesNotExist:
    try:
      watch_url = lt.get_watch_url(normalized_search_string)
    except luckytubes.SearchFailedError:
      raise Http404
    result = Search(keywords=normalized_search_string,
                    watch_url=watch_url)
    result.save()

  return HttpResponseRedirect(result.watch_url)
