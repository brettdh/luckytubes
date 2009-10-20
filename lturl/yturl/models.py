from django.db import models

class Search(models.Model):
  keywords = models.CharField(max_length=200, primary_key=True)
  watch_url = models.CharField(max_length=200)
