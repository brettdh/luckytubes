import os
import sys

sys.path.append('/home/swolchok/luckytubes')
os.environ['DJANGO_SETTINGS_MODULE'] = 'lturl.settings'

import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()