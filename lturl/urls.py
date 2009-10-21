from django.conf.urls.defaults import *

from django.views.generic.simple import redirect_to

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    (r'^$', redirect_to, {'url': 'http://scott.wolchok.org/lturl.html'}),
    (r'favicon\.ico|robots\.txt', handler404),
    (r'^[^/]+$', 'lturl.yturl.views.search'),

    # Uncomment the admin/doc line below and add 'django.contrib.admindocs' 
    # to INSTALLED_APPS to enable admin documentation:
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # (r'^admin/(.*)', admin.site.root),
)
