#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Ricardo Garcia Gonzalez
# Author: Danny Colligan
# Author: Benjamin Johnson
# License: Public domain code
import htmlentitydefs
import httplib
import locale
import math
import netrc
import os
import os.path
import re
import socket
import string
import subprocess
import sys
import time
import urllib
import urllib2

# parse_qs was moved from the cgi module to the urlparse module recently.
try:
	from urlparse import parse_qs
except ImportError:
	from cgi import parse_qs

std_headers = {
	'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.2) Gecko/20100115 Firefox/3.6',
	'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
	'Accept': 'text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5',
	'Accept-Language': 'en-us,en;q=0.5',
}

simple_title_chars = string.ascii_letters.decode('ascii') + string.digits.decode('ascii')

def preferredencoding():
	"""Get preferred encoding.

	Returns the best encoding scheme for the system, based on
	locale.getpreferredencoding() and some further tweaks.
	"""
	def yield_preferredencoding():
		try:
			pref = locale.getpreferredencoding()
			u'TEST'.encode(pref)
		except:
			pref = 'UTF-8'
		while True:
			yield pref
	return yield_preferredencoding().next()

def htmlentity_transform(matchobj):
	"""Transforms an HTML entity to a Unicode character.
	
	This function receives a match object and is intended to be used with
	the re.sub() function.
	"""
	entity = matchobj.group(1)

	# Known non-numeric HTML entity
	if entity in htmlentitydefs.name2codepoint:
		return unichr(htmlentitydefs.name2codepoint[entity])

	# Unicode character
	mobj = re.match(ur'(?u)#(x?\d+)', entity)
	if mobj is not None:
		numstr = mobj.group(1)
		if numstr.startswith(u'x'):
			base = 16
			numstr = u'0%s' % numstr
		else:
			base = 10
		return unichr(long(numstr, base))

	# Unknown entity in name, return its literal representation
	return (u'&%s;' % entity)

def sanitize_title(utitle):
	"""Sanitizes a video title so it could be used as part of a filename."""
	utitle = re.sub(ur'(?u)&(.+?);', htmlentity_transform, utitle)
	return utitle.replace(unicode(os.sep), u'%')

def sanitize_open(filename, open_mode):
	"""Try to open the given filename, and slightly tweak it if this fails.

	Attempts to open the given filename. If this fails, it tries to change
	the filename slightly, step by step, until it's either able to open it
	or it fails and raises a final exception, like the standard open()
	function.

	It returns the tuple (stream, definitive_file_name).
	"""
	try:
		if filename == u'-':
			return (sys.stdout, filename)
		stream = open(filename, open_mode)
		return (stream, filename)
	except (IOError, OSError), err:
		# In case of error, try to remove win32 forbidden chars
		filename = re.sub(ur'[<>:"\|\?\*]', u'#', filename)

		# An exception here should be caught in the caller
		stream = open(filename, open_mode)
		return (stream, filename)


class DownloadError(Exception):
	"""Download Error exception.
	
	This exception may be thrown by FileDownloader objects if they are not
	configured to continue on errors. They will contain the appropriate
	error message.
	"""
	pass

class SameFileError(Exception):
	"""Same File exception.

	This exception will be thrown by FileDownloader objects if they detect
	multiple files would have to be downloaded to the same file on disk.
	"""
	pass

class PostProcessingError(Exception):
	"""Post Processing exception.

	This exception may be raised by PostProcessor's .run() method to
	indicate an error in the postprocessing task.
	"""
	pass

class UnavailableFormatError(Exception):
	"""Unavailable Format exception.

	This exception will be thrown when a video is requested
	in a format that is not available for that video.
	"""
	pass

class ContentTooShortError(Exception):
	"""Content Too Short exception.

	This exception may be raised by FileDownloader objects when a file they
	download is too small for what the server announced first, indicating
	the connection was probably interrupted.
	"""
	# Both in bytes
	downloaded = None
	expected = None

	def __init__(self, downloaded, expected):
		self.downloaded = downloaded
		self.expected = expected

class FileDownloader(object):
	"""File Downloader class.

	File downloader objects are the ones responsible of downloading the
	actual video file and writing it to disk if the user has requested
	it, among some other tasks. In most cases there should be one per
	program. As, given a video URL, the downloader doesn't know how to
	extract all the needed information, task that InfoExtractors do, it
	has to pass the URL to one of them.

	For this, file downloader objects have a method that allows
	InfoExtractors to be registered in a given order. When it is passed
	a URL, the file downloader handles it to the first InfoExtractor it
	finds that reports being able to handle it. The InfoExtractor extracts
	all the information about the video or videos the URL refers to, and
	asks the FileDownloader to process the video information, possibly
	downloading the video.

	File downloaders accept a lot of parameters. In order not to saturate
	the object constructor with arguments, it receives a dictionary of
	options instead. These options are available through the params
	attribute for the InfoExtractors to use. The FileDownloader also
	registers itself as the downloader in charge for the InfoExtractors
	that are added to it, so this is a "mutual registration".

	Available options:

	username:	Username for authentication purposes.
	password:	Password for authentication purposes.
	usenetrc:	Use netrc for authentication instead.
	quiet:		Do not print messages to stdout.
	forceurl:	Force printing final URL.
	forcetitle:	Force printing title.
	simulate:	Do not download the video files.
	format:		Video format code.
	outtmpl:	Template for output names.
	ignoreerrors:	Do not stop on download errors.
	ratelimit:	Download speed limit, in bytes/sec.
	nooverwrites:	Prevent overwriting files.
	continuedl:	Try to continue downloads if possible.
	noprogress:	Do not print the progress bar.
	"""

	params = None
	_ies = []
	_pps = []
	_download_retcode = None
	_num_downloads = None

	def __init__(self, params):
		"""Create a FileDownloader object with the given options."""
		self._ies = []
		self._pps = []
		self._download_retcode = 0
		self._num_downloads = 0
		self.params = params
	
	@staticmethod
	def pmkdir(filename):
		"""Create directory components in filename. Similar to Unix "mkdir -p"."""
		components = filename.split(os.sep)
		aggregate = [os.sep.join(components[0:x]) for x in xrange(1, len(components))]
		aggregate = ['%s%s' % (x, os.sep) for x in aggregate] # Finish names with separator
		for dir in aggregate:
			if not os.path.exists(dir):
				os.mkdir(dir)
	
	@staticmethod
	def format_bytes(bytes):
		if bytes is None:
			return 'N/A'
		if type(bytes) is str:
			bytes = float(bytes)
		if bytes == 0.0:
			exponent = 0
		else:
			exponent = long(math.log(bytes, 1024.0))
		suffix = 'bkMGTPEZY'[exponent]
		converted = float(bytes) / float(1024**exponent)
		return '%.2f%s' % (converted, suffix)

	@staticmethod
	def calc_percent(byte_counter, data_len):
		if data_len is None:
			return '---.-%'
		return '%6s' % ('%3.1f%%' % (float(byte_counter) / float(data_len) * 100.0))

	@staticmethod
	def calc_eta(start, now, total, current):
		if total is None:
			return '--:--'
		dif = now - start
		if current == 0 or dif < 0.001: # One millisecond
			return '--:--'
		rate = float(current) / dif
		eta = long((float(total) - float(current)) / rate)
		(eta_mins, eta_secs) = divmod(eta, 60)
		if eta_mins > 99:
			return '--:--'
		return '%02d:%02d' % (eta_mins, eta_secs)

	@staticmethod
	def calc_speed(start, now, bytes):
		dif = now - start
		if bytes == 0 or dif < 0.001: # One millisecond
			return '%10s' % '---b/s'
		return '%10s' % ('%s/s' % FileDownloader.format_bytes(float(bytes) / dif))

	@staticmethod
	def best_block_size(elapsed_time, bytes):
		new_min = max(bytes / 2.0, 1.0)
		new_max = min(max(bytes * 2.0, 1.0), 4194304) # Do not surpass 4 MB
		if elapsed_time < 0.001:
			return long(new_max)
		rate = bytes / elapsed_time
		if rate > new_max:
			return long(new_max)
		if rate < new_min:
			return long(new_min)
		return long(rate)

	@staticmethod
	def parse_bytes(bytestr):
		"""Parse a string indicating a byte quantity into a long integer."""
		matchobj = re.match(r'(?i)^(\d+(?:\.\d+)?)([kMGTPEZY]?)$', bytestr)
		if matchobj is None:
			return None
		number = float(matchobj.group(1))
		multiplier = 1024.0 ** 'bkmgtpezy'.index(matchobj.group(2).lower())
		return long(round(number * multiplier))

	@staticmethod
	def verify_url(url):
		"""Verify a URL is valid and data could be downloaded. Return real data URL."""
		request = urllib2.Request(url, None, std_headers)
		data = urllib2.urlopen(request)
		data.read(1)
		url = data.geturl()
		data.close()
		return url

	def add_info_extractor(self, ie):
		"""Add an InfoExtractor object to the end of the list."""
		self._ies.append(ie)
		ie.set_downloader(self)
	
	def add_post_processor(self, pp):
		"""Add a PostProcessor object to the end of the chain."""
		self._pps.append(pp)
		pp.set_downloader(self)
	
	def to_stdout(self, message, skip_eol=False, ignore_encoding_errors=False):
		"""Print message to stdout if not in quiet mode."""
		try:
			if not self.params.get('quiet', False):
				print (u'%s%s' % (message, [u'\n', u''][skip_eol])).encode(preferredencoding()),
			sys.stdout.flush()
		except (UnicodeEncodeError), err:
			if not ignore_encoding_errors:
				raise
	
	def to_stderr(self, message):
		"""Print message to stderr."""
		print >>sys.stderr, message.encode(preferredencoding())
	
	def fixed_template(self):
		"""Checks if the output template is fixed."""
		return (re.search(ur'(?u)%\(.+?\)s', self.params['outtmpl']) is None)

	def trouble(self, message=None):
		"""Determine action to take when a download problem appears.

		Depending on if the downloader has been configured to ignore
		download errors or not, this method may throw an exception or
		not when errors are found, after printing the message.
		"""
		if message is not None:
			self.to_stderr(message)
		if not self.params.get('ignoreerrors', False):
			raise DownloadError(message)
		self._download_retcode = 1

	def slow_down(self, start_time, byte_counter):
		"""Sleep if the download speed is over the rate limit."""
		rate_limit = self.params.get('ratelimit', None)
		if rate_limit is None or byte_counter == 0:
			return
		now = time.time()
		elapsed = now - start_time
		if elapsed <= 0.0:
			return
		speed = float(byte_counter) / elapsed
		if speed > rate_limit:
			time.sleep((byte_counter - rate_limit * (now - start_time)) / rate_limit)

	def report_destination(self, filename):
		"""Report destination filename."""
		self.to_stdout(u'[download] Destination: %s' % filename, ignore_encoding_errors=True)
	
	def report_progress(self, percent_str, data_len_str, speed_str, eta_str):
		"""Report download progress."""
		if self.params.get('noprogress', False):
			return
		self.to_stdout(u'\r[download] %s of %s at %s ETA %s' %
				(percent_str, data_len_str, speed_str, eta_str), skip_eol=True)

	def report_resuming_byte(self, resume_len):
		"""Report attemtp to resume at given byte."""
		self.to_stdout(u'[download] Resuming download at byte %s' % resume_len)
	
	def report_file_already_downloaded(self, file_name):
		"""Report file has already been fully downloaded."""
		try:
			self.to_stdout(u'[download] %s has already been downloaded' % file_name)
		except (UnicodeEncodeError), err:
			self.to_stdout(u'[download] The file has already been downloaded')
	
	def report_unable_to_resume(self):
		"""Report it was impossible to resume download."""
		self.to_stdout(u'[download] Unable to resume')
	
	def report_finish(self):
		"""Report download finished."""
		if self.params.get('noprogress', False):
			self.to_stdout(u'[download] Download completed')
		else:
			self.to_stdout(u'')

	def process_info(self, info_dict):
		"""Process a single dictionary returned by an InfoExtractor."""
		# Do nothing else if in simulate mode
		if self.params.get('simulate', False):
			# Verify URL if it's an HTTP one
			if info_dict['url'].startswith('http'):
				try:
					self.verify_url(info_dict['url'].encode('utf-8')).decode('utf-8')
				except (OSError, IOError, urllib2.URLError, httplib.HTTPException, socket.error), err:
					raise UnavailableFormatError

			# Forced printings
			if self.params.get('forcetitle', False):
				print info_dict['title'].encode(preferredencoding(), 'xmlcharrefreplace')
			if self.params.get('forceurl', False):
				print info_dict['url'].encode(preferredencoding(), 'xmlcharrefreplace')
			if self.params.get('forcethumbnail', False) and 'thumbnail' in info_dict:
				print info_dict['thumbnail'].encode(preferredencoding(), 'xmlcharrefreplace')
			if self.params.get('forcedescription', False) and 'description' in info_dict:
				print info_dict['description'].encode(preferredencoding(), 'xmlcharrefreplace')

			return
			
		try:
			template_dict = dict(info_dict)
			template_dict['epoch'] = unicode(long(time.time()))
			template_dict['ord'] = unicode('%05d' % self._num_downloads)
			filename = self.params['outtmpl'] % template_dict
		except (ValueError, KeyError), err:
			self.trouble('ERROR: invalid output template or system charset: %s' % str(err))
		if self.params.get('nooverwrites', False) and os.path.exists(filename):
			self.to_stderr(u'WARNING: file exists: %s; skipping' % filename)
			return

		try:
			self.pmkdir(filename)
		except (OSError, IOError), err:
			self.trouble('ERROR: unable to create directories: %s' % str(err))
			return

		try:
			success = self._do_download(filename, info_dict['url'].encode('utf-8'))
		except (OSError, IOError), err:
			raise UnavailableFormatError
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self.trouble('ERROR: unable to download video data: %s' % str(err))
			return
		except (ContentTooShortError, ), err:
			self.trouble('ERROR: content too short (expected %s bytes and served %s)' % (err.expected, err.downloaded))
			return

		if success:
			try:
				self.post_process(filename, info_dict)
			except (PostProcessingError), err:
				self.trouble('ERROR: postprocessing: %s' % str(err))
				return

	def download(self, url_list):
		"""Download a given list of URLs."""
		if len(url_list) > 1 and self.fixed_template():
			raise SameFileError(self.params['outtmpl'])

		for url in url_list:
			suitable_found = False
			for ie in self._ies:
				# Go to next InfoExtractor if not suitable
				if not ie.suitable(url):
					continue

				# Suitable InfoExtractor found
				suitable_found = True

				# Extract information from URL and process it
				ie.extract(url)

				# Suitable InfoExtractor had been found; go to next URL
				break

			if not suitable_found:
				self.trouble('ERROR: no suitable InfoExtractor: %s' % url)

		return self._download_retcode

	def post_process(self, filename, ie_info):
		"""Run the postprocessing chain on the given file."""
		info = dict(ie_info)
		info['filepath'] = filename
		for pp in self._pps:
			info = pp.run(info)
			if info is None:
				break
	
	def _download_with_rtmpdump(self, filename, url):
		self.report_destination(filename)

		# Check for rtmpdump first
		try:
			subprocess.call(['rtmpdump', '-h'], stdout=(file(os.path.devnull, 'w')), stderr=subprocess.STDOUT)
		except (OSError, IOError):
			self.trouble(u'ERROR: RTMP download detected but "rtmpdump" could not be run')
			return False

		# Download using rtmpdump. rtmpdump returns exit code 2 when
		# the connection was interrumpted and resuming appears to be
		# possible. This is part of rtmpdump's normal usage, AFAIK.
		basic_args = ['rtmpdump', '-q', '-r', url, '-o', filename]
		retval = subprocess.call(basic_args + [[], ['-e', '-k', '1']][self.params.get('continuedl', False)])
		while retval == 2 or retval == 1:
			self.to_stdout(u'\r[rtmpdump] %s bytes' % os.path.getsize(filename), skip_eol=True)
			time.sleep(2.0) # This seems to be needed
			retval = subprocess.call(basic_args + ['-e'] + [[], ['-k', '1']][retval == 1])
		if retval == 0:
			self.to_stdout(u'\r[rtmpdump] %s bytes' % os.path.getsize(filename))
			return True
		else:
			self.trouble('\nERROR: rtmpdump exited with code %d' % retval)
			return False

	def _do_download(self, filename, url):
		# Attempt to download using rtmpdump
		if url.startswith('rtmp'):
			return self._download_with_rtmpdump(filename, url)

		stream = None
		open_mode = 'wb'
		basic_request = urllib2.Request(url, None, std_headers)
		request = urllib2.Request(url, None, std_headers)

		# Establish possible resume length
		if os.path.isfile(filename):
			resume_len = os.path.getsize(filename)
		else:
			resume_len = 0

		# Request parameters in case of being able to resume
		if self.params.get('continuedl', False) and resume_len != 0:
			self.report_resuming_byte(resume_len)
			request.add_header('Range','bytes=%d-' % resume_len)
			open_mode = 'ab'

		# Establish connection
		try:
			data = urllib2.urlopen(request)
		except (urllib2.HTTPError, ), err:
			if err.code != 416: #  416 is 'Requested range not satisfiable'
				raise
			# Unable to resume
			data = urllib2.urlopen(basic_request)
			content_length = data.info()['Content-Length']

			if content_length is not None and long(content_length) == resume_len:
				# Because the file had already been fully downloaded
				self.report_file_already_downloaded(filename)
				return True
			else:
				# Because the server didn't let us
				self.report_unable_to_resume()
				open_mode = 'wb'

		data_len = data.info().get('Content-length', None)
		data_len_str = self.format_bytes(data_len)
		byte_counter = 0
		block_size = 1024
		start = time.time()
		while True:
			# Download and write
			before = time.time()
			data_block = data.read(block_size)
			after = time.time()
			data_block_len = len(data_block)
			if data_block_len == 0:
				break
			byte_counter += data_block_len

			# Open file just in time
			if stream is None:
				try:
					(stream, filename) = sanitize_open(filename, open_mode)
					self.report_destination(filename)
					self._num_downloads += 1
				except (OSError, IOError), err:
					self.trouble('ERROR: unable to open for writing: %s' % str(err))
					return False
			stream.write(data_block)
			block_size = self.best_block_size(after - before, data_block_len)

			# Progress message
			percent_str = self.calc_percent(byte_counter, data_len)
			eta_str = self.calc_eta(start, time.time(), data_len, byte_counter)
			speed_str = self.calc_speed(start, time.time(), byte_counter)
			self.report_progress(percent_str, data_len_str, speed_str, eta_str)

			# Apply rate limit
			self.slow_down(start, byte_counter)

		self.report_finish()
		if data_len is not None and str(byte_counter) != data_len:
			raise ContentTooShortError(byte_counter, long(data_len))
		return True

class InfoExtractor(object):
	"""Information Extractor class.

	Information extractors are the classes that, given a URL, extract
	information from the video (or videos) the URL refers to. This
	information includes the real video URL, the video title and simplified
	title, author and others. The information is stored in a dictionary
	which is then passed to the FileDownloader. The FileDownloader
	processes this information possibly downloading the video to the file
	system, among other possible outcomes. The dictionaries must include
	the following fields:

	id:		Video identifier.
	url:		Final video URL.
	uploader:	Nickname of the video uploader.
	title:		Literal title.
	stitle:		Simplified title.
	ext:		Video filename extension.
	format:		Video format.

	The following fields are optional. Their primary purpose is to allow
	youtube-dl to serve as the backend for a video search function, such
	as the one in youtube2mp3.  They are only used when their respective
	forced printing functions are called:

	thumbnail:	Full URL to a video thumbnail image.
	description:	One-line video description.

	Subclasses of this one should re-define the _real_initialize() and
	_real_extract() methods, as well as the suitable() static method.
	Probably, they should also be instantiated and added to the main
	downloader.
	"""

	_ready = False
	_downloader = None

	def __init__(self, downloader=None):
		"""Constructor. Receives an optional downloader."""
		self._ready = False
		self.set_downloader(downloader)

	@staticmethod
	def suitable(url):
		"""Receives a URL and returns True if suitable for this IE."""
		return False

	def initialize(self):
		"""Initializes an instance (authentication, etc)."""
		if not self._ready:
			self._real_initialize()
			self._ready = True

	def extract(self, url):
		"""Extracts URL information and returns it in list of dicts."""
		self.initialize()
		return self._real_extract(url)

	def set_downloader(self, downloader):
		"""Sets the downloader for this IE."""
		self._downloader = downloader
	
	def _real_initialize(self):
		"""Real initialization process. Redefine in subclasses."""
		pass

	def _real_extract(self, url):
		"""Real extraction process. Redefine in subclasses."""
		pass

class YoutubeIE(InfoExtractor):
	"""Information extractor for youtube.com."""

	_VALID_URL = r'^((?:http://)?(?:\w+\.)?youtube\.com/(?:(?:v/)|(?:(?:watch(?:\.php)?)?[\?#](?:.+&)?v=)))?([0-9A-Za-z_-]+)(?(1).+)?$'
	_LANG_URL = r'http://uk.youtube.com/?hl=en&persist_hl=1&gl=US&persist_gl=1&opt_out_ackd=1'
	_LOGIN_URL = 'http://www.youtube.com/signup?next=/&gl=US&hl=en'
	_AGE_URL = 'http://www.youtube.com/verify_age?next_url=/&gl=US&hl=en'
	_NETRC_MACHINE = 'youtube'
	_available_formats = ['37', '22', '35', '18', '34', '5', '17', '13', None] # listed in order of priority for -b flag
	_video_extensions = {
		'13': '3gp',
		'17': 'mp4',
		'18': 'mp4',
		'22': 'mp4',
		'37': 'mp4',
	}

	@staticmethod
	def suitable(url):
		return (re.match(YoutubeIE._VALID_URL, url) is not None)

	def report_lang(self):
		"""Report attempt to set language."""
		self._downloader.to_stdout(u'[youtube] Setting language')

	def report_login(self):
		"""Report attempt to log in."""
		self._downloader.to_stdout(u'[youtube] Logging in')
	
	def report_age_confirmation(self):
		"""Report attempt to confirm age."""
		self._downloader.to_stdout(u'[youtube] Confirming age')
	
	def report_video_info_webpage_download(self, video_id):
		"""Report attempt to download video info webpage."""
		self._downloader.to_stdout(u'[youtube] %s: Downloading video info webpage' % video_id)
	
	def report_information_extraction(self, video_id):
		"""Report attempt to extract video information."""
		self._downloader.to_stdout(u'[youtube] %s: Extracting video information' % video_id)
	
	def report_unavailable_format(self, video_id, format):
		"""Report extracted video URL."""
		self._downloader.to_stdout(u'[youtube] %s: Format %s not available' % (video_id, format))
	
	def report_rtmp_download(self):
		"""Indicate the download will use the RTMP protocol."""
		self._downloader.to_stdout(u'[youtube] RTMP download detected')
	
	def _real_initialize(self):
		if self._downloader is None:
			return

		username = None
		password = None
		downloader_params = self._downloader.params

		# Attempt to use provided username and password or .netrc data
		if downloader_params.get('username', None) is not None:
			username = downloader_params['username']
			password = downloader_params['password']
		elif downloader_params.get('usenetrc', False):
			try:
				info = netrc.netrc().authenticators(self._NETRC_MACHINE)
				if info is not None:
					username = info[0]
					password = info[2]
				else:
					raise netrc.NetrcParseError('No authenticators for %s' % self._NETRC_MACHINE)
			except (IOError, netrc.NetrcParseError), err:
				self._downloader.to_stderr(u'WARNING: parsing .netrc: %s' % str(err))
				return

		# Set language
		request = urllib2.Request(self._LANG_URL, None, std_headers)
		try:
			self.report_lang()
			urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.to_stderr(u'WARNING: unable to set language: %s' % str(err))
			return

		# No authentication to be performed
		if username is None:
			return

		# Log in
		login_form = {
				'current_form': 'loginForm',
				'next':		'/',
				'action_login':	'Log In',
				'username':	username,
				'password':	password,
				}
		request = urllib2.Request(self._LOGIN_URL, urllib.urlencode(login_form), std_headers)
		try:
			self.report_login()
			login_results = urllib2.urlopen(request).read()
			if re.search(r'(?i)<form[^>]* name="loginForm"', login_results) is not None:
				self._downloader.to_stderr(u'WARNING: unable to log in: bad username or password')
				return
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.to_stderr(u'WARNING: unable to log in: %s' % str(err))
			return
	
		# Confirm age
		age_form = {
				'next_url':		'/',
				'action_confirm':	'Confirm',
				}
		request = urllib2.Request(self._AGE_URL, urllib.urlencode(age_form), std_headers)
		try:
			self.report_age_confirmation()
			age_results = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: unable to confirm age: %s' % str(err))
			return

	def _real_extract(self, url):
		# Extract video id from URL
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid URL: %s' % url)
			return
		video_id = mobj.group(2)

		# Downloader parameters
		best_quality = False
		all_formats = False
		format_param = None
		quality_index = 0
		if self._downloader is not None:
			params = self._downloader.params
			format_param = params.get('format', None)
			if format_param == '0':
				format_param = self._available_formats[quality_index]
				best_quality = True
			elif format_param == '-1':
				format_param = self._available_formats[quality_index]
				all_formats = True

		while True:
			# Extension
			video_extension = self._video_extensions.get(format_param, 'flv')

			# Get video info
			self.report_video_info_webpage_download(video_id)
			for el_type in ['embedded', 'detailpage', 'vevo']:
				video_info_url = ('http://www.youtube.com/get_video_info?&video_id=%s&el=%s&ps=default&eurl=&gl=US&hl=en'
						   % (video_id, el_type))
				request = urllib2.Request(video_info_url, None, std_headers)
				try:
					video_info_webpage = urllib2.urlopen(request).read()
					video_info = parse_qs(video_info_webpage)
					if 'token' in video_info:
						break
				except (urllib2.URLError, httplib.HTTPException, socket.error), err:
					self._downloader.trouble(u'ERROR: unable to download video info webpage: %s' % str(err))
					return
			self.report_information_extraction(video_id)

			# "t" param
			if 'token' not in video_info:
				# Attempt to see if YouTube has issued an error message
				if 'reason' not in video_info:
					self._downloader.trouble(u'ERROR: unable to extract "t" parameter for unknown reason')
					stream = open('reportme-ydl-%s.dat' % time.time(), 'wb')
					stream.write(video_info_webpage)
					stream.close()
				else:
					reason = urllib.unquote_plus(video_info['reason'][0])
					self._downloader.trouble(u'ERROR: YouTube said: %s' % reason.decode('utf-8'))
				return
			token = urllib.unquote_plus(video_info['token'][0])
			video_real_url = 'http://www.youtube.com/get_video?video_id=%s&t=%s&eurl=&el=detailpage&ps=default&gl=US&hl=en' % (video_id, token)
			if format_param is not None:
				video_real_url = '%s&fmt=%s' % (video_real_url, format_param)

			# Check possible RTMP download
			if 'conn' in video_info and video_info['conn'][0].startswith('rtmp'):
				self.report_rtmp_download()
				video_real_url = video_info['conn'][0]

			# uploader
			if 'author' not in video_info:
				self._downloader.trouble(u'ERROR: unable to extract uploader nickname')
				return
			video_uploader = urllib.unquote_plus(video_info['author'][0])

			# title
			if 'title' not in video_info:
				self._downloader.trouble(u'ERROR: unable to extract video title')
				return
			video_title = urllib.unquote_plus(video_info['title'][0])
			video_title = video_title.decode('utf-8')
			video_title = sanitize_title(video_title)

			# simplified title
			simple_title = re.sub(ur'(?u)([^%s]+)' % simple_title_chars, ur'_', video_title)
			simple_title = simple_title.strip(ur'_')

			# thumbnail image
			if 'thumbnail_url' not in video_info:
				self._downloader.trouble(u'WARNING: unable to extract video thumbnail')
				video_thumbnail = ''
			else:	# don't panic if we can't find it
				video_thumbnail = urllib.unquote_plus(video_info['thumbnail_url'][0])

			# get video description
			video_description = 'No description available.'    # we need something to pass to self._downloader
			# this requires an additional HTTP request and a little
			# more time, so don't do it unless absolutely necessary
			if self._downloader.params.get('forcedescription', False):
				video_page_url = 'http://www.youtube.com/watch?v=' + video_id
				request = urllib2.Request(video_page_url, None, std_headers)
				try:
					video_page_webpage = urllib2.urlopen(request).read()
					mobj = re.search(r'<meta name="description" content="(.*)"(?:\s*/)?>', video_page_webpage)
					if mobj is not None:
						video_description = mobj.group(1)
				except (urllib2.URLError, httplib.HTTPException, socket.error), err:
					pass    # don't panic if we can't find it

			try:
				# Process video information
				self._downloader.process_info({
					'id':		video_id.decode('utf-8'),
					'url':		video_real_url.decode('utf-8'),
					'uploader':	video_uploader.decode('utf-8'),
					'title':	video_title,
					'stitle':	simple_title,
					'ext':		video_extension.decode('utf-8'),
					'format':	(format_param is None and u'NA' or format_param.decode('utf-8')),
					'thumbnail':	video_thumbnail.decode('utf-8'),
					'description':	video_description.decode('utf-8'),
				})

				if all_formats:
					if quality_index == len(self._available_formats) - 1:
						# None left to get
						return
					else:
						quality_index += 1
						format_param = self._available_formats[quality_index]
						if format_param == None:
							return
						continue

				return

			except UnavailableFormatError, err:
				if best_quality or all_formats:
					if quality_index == len(self._available_formats) - 1:
						# I don't ever expect this to happen
						if not all_formats:
							self._downloader.trouble(u'ERROR: no known formats available for video')
						return
					else:
						self.report_unavailable_format(video_id, format_param)
						quality_index += 1
						format_param = self._available_formats[quality_index]
						if format_param == None:
							return
						continue
				else: 
					self._downloader.trouble('ERROR: format not available for video')
					return


class MetacafeIE(InfoExtractor):
	"""Information Extractor for metacafe.com."""

	_VALID_URL = r'(?:http://)?(?:www\.)?metacafe\.com/watch/([^/]+)/([^/]+)/.*'
	_DISCLAIMER = 'http://www.metacafe.com/family_filter/'
	_FILTER_POST = 'http://www.metacafe.com/f/index.php?inputType=filter&controllerGroup=user'
	_youtube_ie = None

	def __init__(self, youtube_ie, downloader=None):
		InfoExtractor.__init__(self, downloader)
		self._youtube_ie = youtube_ie

	@staticmethod
	def suitable(url):
		return (re.match(MetacafeIE._VALID_URL, url) is not None)

	def report_disclaimer(self):
		"""Report disclaimer retrieval."""
		self._downloader.to_stdout(u'[metacafe] Retrieving disclaimer')

	def report_age_confirmation(self):
		"""Report attempt to confirm age."""
		self._downloader.to_stdout(u'[metacafe] Confirming age')
	
	def report_download_webpage(self, video_id):
		"""Report webpage download."""
		self._downloader.to_stdout(u'[metacafe] %s: Downloading webpage' % video_id)
	
	def report_extraction(self, video_id):
		"""Report information extraction."""
		self._downloader.to_stdout(u'[metacafe] %s: Extracting information' % video_id)

	def _real_initialize(self):
		# Retrieve disclaimer
		request = urllib2.Request(self._DISCLAIMER, None, std_headers)
		try:
			self.report_disclaimer()
			disclaimer = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: unable to retrieve disclaimer: %s' % str(err))
			return

		# Confirm age
		disclaimer_form = {
			'filters': '0',
			'submit': "Continue - I'm over 18",
			}
		request = urllib2.Request(self._FILTER_POST, urllib.urlencode(disclaimer_form), std_headers)
		try:
			self.report_age_confirmation()
			disclaimer = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: unable to confirm age: %s' % str(err))
			return
	
	def _real_extract(self, url):
		# Extract id and simplified title from URL
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid URL: %s' % url)
			return

		video_id = mobj.group(1)

		# Check if video comes from YouTube
		mobj2 = re.match(r'^yt-(.*)$', video_id)
		if mobj2 is not None:
			self._youtube_ie.extract('http://www.youtube.com/watch?v=%s' % mobj2.group(1))
			return

		simple_title = mobj.group(2).decode('utf-8')
		video_extension = 'flv'

		# Retrieve video webpage to extract further information
		request = urllib2.Request('http://www.metacafe.com/watch/%s/' % video_id)
		try:
			self.report_download_webpage(video_id)
			webpage = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: unable retrieve video webpage: %s' % str(err))
			return

		# Extract URL, uploader and title from webpage
		self.report_extraction(video_id)
		mobj = re.search(r'(?m)&mediaURL=([^&]+)', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract media URL')
			return
		mediaURL = urllib.unquote(mobj.group(1))

		#mobj = re.search(r'(?m)&gdaKey=(.*?)&', webpage)
		#if mobj is None:
		#	self._downloader.trouble(u'ERROR: unable to extract gdaKey')
		#	return
		#gdaKey = mobj.group(1)
		#
		#video_url = '%s?__gda__=%s' % (mediaURL, gdaKey)

		video_url = mediaURL

		mobj = re.search(r'(?im)<title>(.*) - Video</title>', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract title')
			return
		video_title = mobj.group(1).decode('utf-8')
		video_title = sanitize_title(video_title)

		mobj = re.search(r'(?ms)By:\s*<a .*?>(.+?)<', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract uploader nickname')
			return
		video_uploader = mobj.group(1)

		try:
			# Process video information
			self._downloader.process_info({
				'id':		video_id.decode('utf-8'),
				'url':		video_url.decode('utf-8'),
				'uploader':	video_uploader.decode('utf-8'),
				'title':	video_title,
				'stitle':	simple_title,
				'ext':		video_extension.decode('utf-8'),
				'format':	u'NA',
			})
		except UnavailableFormatError:
			self._downloader.trouble(u'ERROR: format not available for video')


class GoogleIE(InfoExtractor):
	"""Information extractor for video.google.com."""

	_VALID_URL = r'(?:http://)?video\.google\.(?:com(?:\.au)?|co\.(?:uk|jp|kr|cr)|ca|de|es|fr|it|nl|pl)/videoplay\?docid=([^\&]+).*'

	def __init__(self, downloader=None):
		InfoExtractor.__init__(self, downloader)

	@staticmethod
	def suitable(url):
		return (re.match(GoogleIE._VALID_URL, url) is not None)

	def report_download_webpage(self, video_id):
		"""Report webpage download."""
		self._downloader.to_stdout(u'[video.google] %s: Downloading webpage' % video_id)

	def report_extraction(self, video_id):
		"""Report information extraction."""
		self._downloader.to_stdout(u'[video.google] %s: Extracting information' % video_id)

	def _real_initialize(self):
		return

	def _real_extract(self, url):
		# Extract id from URL
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: Invalid URL: %s' % url)
			return

		video_id = mobj.group(1)

		video_extension = 'mp4'

		# Retrieve video webpage to extract further information
		request = urllib2.Request('http://video.google.com/videoplay?docid=%s&hl=en&oe=utf-8' % video_id)
		try:
			self.report_download_webpage(video_id)
			webpage = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
			return

		# Extract URL, uploader, and title from webpage
		self.report_extraction(video_id)
		mobj = re.search(r"download_url:'([^']+)'", webpage)
		if mobj is None:
			video_extension = 'flv'
			mobj = re.search(r"(?i)videoUrl\\x3d(.+?)\\x26", webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract media URL')
			return
		mediaURL = urllib.unquote(mobj.group(1))
		mediaURL = mediaURL.replace('\\x3d', '\x3d')
		mediaURL = mediaURL.replace('\\x26', '\x26')

		video_url = mediaURL

		mobj = re.search(r'<title>(.*)</title>', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract title')
			return
		video_title = mobj.group(1).decode('utf-8')
		video_title = sanitize_title(video_title)
		simple_title = re.sub(ur'(?u)([^%s]+)' % simple_title_chars, ur'_', video_title)

		# Extract video description
		mobj = re.search(r'<span id=short-desc-content>([^<]*)</span>', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video description')
			return
		video_description = mobj.group(1).decode('utf-8')
		if not video_description:
			video_description = 'No description available.'

		# Extract video thumbnail
		if self._downloader.params.get('forcethumbnail', False):
			request = urllib2.Request('http://video.google.com/videosearch?q=%s+site:video.google.com&hl=en' % abs(int(video_id)))
			try:
				webpage = urllib2.urlopen(request).read()
			except (urllib2.URLError, httplib.HTTPException, socket.error), err:
				self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
				return
			mobj = re.search(r'<img class=thumbnail-img (?:.* )?src=(http.*)>', webpage)
			if mobj is None:
				self._downloader.trouble(u'ERROR: unable to extract video thumbnail')
				return
			video_thumbnail = mobj.group(1)
		else:	# we need something to pass to process_info
			video_thumbnail = ''


		try:
			# Process video information
			self._downloader.process_info({
				'id':		video_id.decode('utf-8'),
				'url':		video_url.decode('utf-8'),
				'uploader':	u'NA',
				'title':	video_title,
				'stitle':	simple_title,
				'ext':		video_extension.decode('utf-8'),
				'format':	u'NA',
			})
		except UnavailableFormatError:
			self._downloader.trouble(u'ERROR: format not available for video')


class PhotobucketIE(InfoExtractor):
	"""Information extractor for photobucket.com."""

	_VALID_URL = r'(?:http://)?(?:[a-z0-9]+\.)?photobucket\.com/.*[\?\&]current=(.*\.flv)'

	def __init__(self, downloader=None):
		InfoExtractor.__init__(self, downloader)

	@staticmethod
	def suitable(url):
		return (re.match(PhotobucketIE._VALID_URL, url) is not None)

	def report_download_webpage(self, video_id):
		"""Report webpage download."""
		self._downloader.to_stdout(u'[photobucket] %s: Downloading webpage' % video_id)

	def report_extraction(self, video_id):
		"""Report information extraction."""
		self._downloader.to_stdout(u'[photobucket] %s: Extracting information' % video_id)

	def _real_initialize(self):
		return

	def _real_extract(self, url):
		# Extract id from URL
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: Invalid URL: %s' % url)
			return

		video_id = mobj.group(1)

		video_extension = 'flv'

		# Retrieve video webpage to extract further information
		request = urllib2.Request(url)
		try:
			self.report_download_webpage(video_id)
			webpage = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
			return

		# Extract URL, uploader, and title from webpage
		self.report_extraction(video_id)
		mobj = re.search(r'<link rel="video_src" href=".*\?file=([^"]+)" />', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract media URL')
			return
		mediaURL = urllib.unquote(mobj.group(1))

		video_url = mediaURL

		mobj = re.search(r'<title>(.*) video by (.*) - Photobucket</title>', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract title')
			return
		video_title = mobj.group(1).decode('utf-8')
		video_title = sanitize_title(video_title)
		simple_title = re.sub(ur'(?u)([^%s]+)' % simple_title_chars, ur'_', video_title)

		video_uploader = mobj.group(2).decode('utf-8')

		try:
			# Process video information
			self._downloader.process_info({
				'id':		video_id.decode('utf-8'),
				'url':		video_url.decode('utf-8'),
				'uploader':	video_uploader,
				'title':	video_title,
				'stitle':	simple_title,
				'ext':		video_extension.decode('utf-8'),
				'format':	u'NA',
			})
		except UnavailableFormatError:
			self._downloader.trouble(u'ERROR: format not available for video')


class YahooIE(InfoExtractor):
	"""Information extractor for video.yahoo.com."""

	# _VALID_URL matches all Yahoo! Video URLs
	# _VPAGE_URL matches only the extractable '/watch/' URLs
	_VALID_URL = r'(?:http://)?(?:[a-z]+\.)?video\.yahoo\.com/(?:watch|network)/([0-9]+)(?:/|\?v=)([0-9]+)(?:[#\?].*)?'
	_VPAGE_URL = r'(?:http://)?video\.yahoo\.com/watch/([0-9]+)/([0-9]+)(?:[#\?].*)?'

	def __init__(self, downloader=None):
		InfoExtractor.__init__(self, downloader)

	@staticmethod
	def suitable(url):
		return (re.match(YahooIE._VALID_URL, url) is not None)

	def report_download_webpage(self, video_id):
		"""Report webpage download."""
		self._downloader.to_stdout(u'[video.yahoo] %s: Downloading webpage' % video_id)

	def report_extraction(self, video_id):
		"""Report information extraction."""
		self._downloader.to_stdout(u'[video.yahoo] %s: Extracting information' % video_id)

	def _real_initialize(self):
		return

	def _real_extract(self, url):
		# Extract ID from URL
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: Invalid URL: %s' % url)
			return

		video_id = mobj.group(2)
		video_extension = 'flv'

		# Rewrite valid but non-extractable URLs as
		# extractable English language /watch/ URLs
		if re.match(self._VPAGE_URL, url) is None:
			request = urllib2.Request(url)
			try:
				webpage = urllib2.urlopen(request).read()
			except (urllib2.URLError, httplib.HTTPException, socket.error), err:
				self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
				return

			mobj = re.search(r'\("id", "([0-9]+)"\);', webpage)
			if mobj is None:
				self._downloader.trouble(u'ERROR: Unable to extract id field')
				return
			yahoo_id = mobj.group(1)

			mobj = re.search(r'\("vid", "([0-9]+)"\);', webpage)
			if mobj is None:
				self._downloader.trouble(u'ERROR: Unable to extract vid field')
				return
			yahoo_vid = mobj.group(1)

			url = 'http://video.yahoo.com/watch/%s/%s' % (yahoo_vid, yahoo_id)
			return self._real_extract(url)

		# Retrieve video webpage to extract further information
		request = urllib2.Request(url)
		try:
			self.report_download_webpage(video_id)
			webpage = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
			return

		# Extract uploader and title from webpage
		self.report_extraction(video_id)
		mobj = re.search(r'<meta name="title" content="(.*)" />', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video title')
			return
		video_title = mobj.group(1).decode('utf-8')
		simple_title = re.sub(ur'(?u)([^%s]+)' % simple_title_chars, ur'_', video_title)

		mobj = re.search(r'<h2 class="ti-5"><a href="http://video\.yahoo\.com/(people|profile)/[0-9]+" beacon=".*">(.*)</a></h2>', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video uploader')
			return
		video_uploader = mobj.group(1).decode('utf-8')

		# Extract video thumbnail
		mobj = re.search(r'<link rel="image_src" href="(.*)" />', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video thumbnail')
			return
		video_thumbnail = mobj.group(1).decode('utf-8')

		# Extract video description
		mobj = re.search(r'<meta name="description" content="(.*)" />', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video description')
			return
		video_description = mobj.group(1).decode('utf-8')
		if not video_description: video_description = 'No description available.'

		# Extract video height and width
		mobj = re.search(r'<meta name="video_height" content="([0-9]+)" />', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video height')
			return
		yv_video_height = mobj.group(1)

		mobj = re.search(r'<meta name="video_width" content="([0-9]+)" />', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract video width')
			return
		yv_video_width = mobj.group(1)

		# Retrieve video playlist to extract media URL
		# I'm not completely sure what all these options are, but we
		# seem to need most of them, otherwise the server sends a 401.
		yv_lg = 'R0xx6idZnW2zlrKP8xxAIR'  # not sure what this represents
		yv_bitrate = '700'  # according to Wikipedia this is hard-coded
		request = urllib2.Request('http://cosmos.bcst.yahoo.com/up/yep/process/getPlaylistFOP.php?node_id=' + video_id +
				          '&tech=flash&mode=playlist&lg=' + yv_lg + '&bitrate=' + yv_bitrate + '&vidH=' + yv_video_height +
					  '&vidW=' + yv_video_width + '&swf=as3&rd=video.yahoo.com&tk=null&adsupported=v1,v2,&eventid=1301797')
		try:
			self.report_download_webpage(video_id)
			webpage = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
			return

		# Extract media URL from playlist XML
		mobj = re.search(r'<STREAM APP="(http://.*)" FULLPATH="/?(/.*\.flv\?[^"]*)"', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: Unable to extract media URL')
			return
		video_url = urllib.unquote(mobj.group(1) + mobj.group(2)).decode('utf-8')
		video_url = re.sub(r'(?u)&(.+?);', htmlentity_transform, video_url)

		try:
			# Process video information
			self._downloader.process_info({
				'id':		video_id.decode('utf-8'),
				'url':		video_url,
				'uploader':	video_uploader,
				'title':	video_title,
				'stitle':	simple_title,
				'ext':		video_extension.decode('utf-8'),
				'thumbnail':	video_thumbnail.decode('utf-8'),
				'description':	video_description,
				'thumbnail':	video_thumbnail,
				'description':	video_description,
			})
		except UnavailableFormatError:
			self._downloader.trouble(u'ERROR: format not available for video')


class GenericIE(InfoExtractor):
	"""Generic last-resort information extractor."""

	def __init__(self, downloader=None):
		InfoExtractor.__init__(self, downloader)

	@staticmethod
	def suitable(url):
		return True

	def report_download_webpage(self, video_id):
		"""Report webpage download."""
		self._downloader.to_stdout(u'WARNING: Falling back on generic information extractor.')
		self._downloader.to_stdout(u'[generic] %s: Downloading webpage' % video_id)

	def report_extraction(self, video_id):
		"""Report information extraction."""
		self._downloader.to_stdout(u'[generic] %s: Extracting information' % video_id)

	def _real_initialize(self):
		return

	def _real_extract(self, url):
		video_id = url.split('/')[-1]
		request = urllib2.Request(url)
		try:
			self.report_download_webpage(video_id)
			webpage = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: Unable to retrieve video webpage: %s' % str(err))
			return
		except ValueError, err:
			# since this is the last-resort InfoExtractor, if
			# this error is thrown, it'll be thrown here
			self._downloader.trouble(u'ERROR: Invalid URL: %s' % url)
			return

		# Start with something easy: JW Player in SWFObject
		mobj = re.search(r'flashvars: [\'"](?:.*&)?file=(http[^\'"&]*)', webpage)
		if mobj is None:
			# Broaden the search a little bit
			mobj = re.search(r'[^A-Za-z0-9]?(?:file|source)=(http[^\'"&]*)', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: Invalid URL: %s' % url)
			return

		# It's possible that one of the regexes
		# matched, but returned an empty group:
		if mobj.group(1) is None:
			self._downloader.trouble(u'ERROR: Invalid URL: %s' % url)
			return

		video_url = urllib.unquote(mobj.group(1))
		video_id  = os.path.basename(video_url)

		# here's a fun little line of code for you:
		video_extension = os.path.splitext(video_id)[1][1:]
		video_id        = os.path.splitext(video_id)[0]

		# it's tempting to parse this further, but you would
		# have to take into account all the variations like
		#   Video Title - Site Name
		#   Site Name | Video Title
		#   Video Title - Tagline | Site Name
		# and so on and so forth; it's just not practical
		mobj = re.search(r'<title>(.*)</title>', webpage)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract title')
			return
		video_title = mobj.group(1).decode('utf-8')
		video_title = sanitize_title(video_title)
		simple_title = re.sub(ur'(?u)([^%s]+)' % simple_title_chars, ur'_', video_title)

		# video uploader is domain name
		mobj = re.match(r'(?:https?://)?([^/]*)/.*', url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: unable to extract title')
			return
		video_uploader = mobj.group(1).decode('utf-8')

		try:
			# Process video information
			self._downloader.process_info({
				'id':		video_id.decode('utf-8'),
				'url':		video_url.decode('utf-8'),
				'uploader':	video_uploader,
				'title':	video_title,
				'stitle':	simple_title,
				'ext':		video_extension.decode('utf-8'),
				'format':	u'NA',
			})
		except UnavailableFormatError:
			self._downloader.trouble(u'ERROR: format not available for video')


class YoutubeSearchIE(InfoExtractor):
	"""Information Extractor for YouTube search queries."""
	_VALID_QUERY = r'ytsearch(\d+|all)?:[\s\S]+'
	_TEMPLATE_URL = 'http://www.youtube.com/results?search_query=%s&page=%s&gl=US&hl=en'
	_VIDEO_INDICATOR = r'href="/watch\?v=.+?"'
	_MORE_PAGES_INDICATOR = r'(?m)>\s*Next\s*</a>'
	_youtube_ie = None
	_max_youtube_results = 1000

	def __init__(self, youtube_ie, downloader=None):
		InfoExtractor.__init__(self, downloader)
		self._youtube_ie = youtube_ie
	
	@staticmethod
	def suitable(url):
		return (re.match(YoutubeSearchIE._VALID_QUERY, url) is not None)

	def report_download_page(self, query, pagenum):
		"""Report attempt to download playlist page with given number."""
		query = query.decode(preferredencoding())
		self._downloader.to_stdout(u'[youtube] query "%s": Downloading page %s' % (query, pagenum))

	def _real_initialize(self):
		self._youtube_ie.initialize()
	
	def _real_extract(self, query):
		mobj = re.match(self._VALID_QUERY, query)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid search query "%s"' % query)
			return

		prefix, query = query.split(':')
		prefix = prefix[8:]
		query  = query.encode('utf-8')
		if prefix == '':
			self._download_n_results(query, 1)
			return
		elif prefix == 'all':
			self._download_n_results(query, self._max_youtube_results)
			return
		else:
			try:
				n = long(prefix)
				if n <= 0:
					self._downloader.trouble(u'ERROR: invalid download number %s for query "%s"' % (n, query))
					return
				elif n > self._max_youtube_results:
					self._downloader.to_stderr(u'WARNING: ytsearch returns max %i results (you requested %i)'  % (self._max_youtube_results, n))
					n = self._max_youtube_results
				self._download_n_results(query, n)
				return
			except ValueError: # parsing prefix as integer fails
				self._download_n_results(query, 1)
				return

	def _download_n_results(self, query, n):
		"""Downloads a specified number of results for a query"""

		video_ids = []
		already_seen = set()
		pagenum = 1

		while True:
			self.report_download_page(query, pagenum)
			result_url = self._TEMPLATE_URL % (urllib.quote_plus(query), pagenum)
			request = urllib2.Request(result_url, None, std_headers)
			try:
				page = urllib2.urlopen(request).read()
			except (urllib2.URLError, httplib.HTTPException, socket.error), err:
				self._downloader.trouble(u'ERROR: unable to download webpage: %s' % str(err))
				return

			# Extract video identifiers
			for mobj in re.finditer(self._VIDEO_INDICATOR, page):
				video_id = page[mobj.span()[0]:mobj.span()[1]].split('=')[2][:-1]
				if video_id not in already_seen:
					video_ids.append(video_id)
					already_seen.add(video_id)
					if len(video_ids) == n:
						# Specified n videos reached
						for id in video_ids:
							self._youtube_ie.extract('http://www.youtube.com/watch?v=%s' % id)
						return

			if re.search(self._MORE_PAGES_INDICATOR, page) is None:
				for id in video_ids:
					self._youtube_ie.extract('http://www.youtube.com/watch?v=%s' % id)
				return

			pagenum = pagenum + 1

class GoogleSearchIE(InfoExtractor):
	"""Information Extractor for Google Video search queries."""
	_VALID_QUERY = r'gvsearch(\d+|all)?:[\s\S]+'
	_TEMPLATE_URL = 'http://video.google.com/videosearch?q=%s+site:video.google.com&start=%s&hl=en'
	_VIDEO_INDICATOR = r'videoplay\?docid=([^\&>]+)\&'
	_MORE_PAGES_INDICATOR = r'<span>Next</span>'
	_google_ie = None
	_max_google_results = 1000

	def __init__(self, google_ie, downloader=None):
		InfoExtractor.__init__(self, downloader)
		self._google_ie = google_ie
	
	@staticmethod
	def suitable(url):
		return (re.match(GoogleSearchIE._VALID_QUERY, url) is not None)

	def report_download_page(self, query, pagenum):
		"""Report attempt to download playlist page with given number."""
		query = query.decode(preferredencoding())
		self._downloader.to_stdout(u'[video.google] query "%s": Downloading page %s' % (query, pagenum))

	def _real_initialize(self):
		self._google_ie.initialize()
	
	def _real_extract(self, query):
		mobj = re.match(self._VALID_QUERY, query)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid search query "%s"' % query)
			return

		prefix, query = query.split(':')
		prefix = prefix[8:]
		query  = query.encode('utf-8')
		if prefix == '':
			self._download_n_results(query, 1)
			return
		elif prefix == 'all':
			self._download_n_results(query, self._max_google_results)
			return
		else:
			try:
				n = long(prefix)
				if n <= 0:
					self._downloader.trouble(u'ERROR: invalid download number %s for query "%s"' % (n, query))
					return
				elif n > self._max_google_results:
					self._downloader.to_stderr(u'WARNING: gvsearch returns max %i results (you requested %i)'  % (self._max_google_results, n))
					n = self._max_google_results
				self._download_n_results(query, n)
				return
			except ValueError: # parsing prefix as integer fails
				self._download_n_results(query, 1)
				return

	def _download_n_results(self, query, n):
		"""Downloads a specified number of results for a query"""

		video_ids = []
		already_seen = set()
		pagenum = 1

		while True:
			self.report_download_page(query, pagenum)
			result_url = self._TEMPLATE_URL % (urllib.quote_plus(query), pagenum)
			request = urllib2.Request(result_url, None, std_headers)
			try:
				page = urllib2.urlopen(request).read()
			except (urllib2.URLError, httplib.HTTPException, socket.error), err:
				self._downloader.trouble(u'ERROR: unable to download webpage: %s' % str(err))
				return

			# Extract video identifiers
			for mobj in re.finditer(self._VIDEO_INDICATOR, page):
				video_id = mobj.group(1)
				if video_id not in already_seen:
					video_ids.append(video_id)
					already_seen.add(video_id)
					if len(video_ids) == n:
						# Specified n videos reached
						for id in video_ids:
							self._google_ie.extract('http://video.google.com/videoplay?docid=%s' % id)
						return

			if re.search(self._MORE_PAGES_INDICATOR, page) is None:
				for id in video_ids:
					self._google_ie.extract('http://video.google.com/videoplay?docid=%s' % id)
				return

			pagenum = pagenum + 1

class YahooSearchIE(InfoExtractor):
	"""Information Extractor for Yahoo! Video search queries."""
	_VALID_QUERY = r'yvsearch(\d+|all)?:[\s\S]+'
	_TEMPLATE_URL = 'http://video.yahoo.com/search/?p=%s&o=%s'
	_VIDEO_INDICATOR = r'href="http://video\.yahoo\.com/watch/([0-9]+/[0-9]+)"'
	_MORE_PAGES_INDICATOR = r'\s*Next'
	_yahoo_ie = None
	_max_yahoo_results = 1000

	def __init__(self, yahoo_ie, downloader=None):
		InfoExtractor.__init__(self, downloader)
		self._yahoo_ie = yahoo_ie
	
	@staticmethod
	def suitable(url):
		return (re.match(YahooSearchIE._VALID_QUERY, url) is not None)

	def report_download_page(self, query, pagenum):
		"""Report attempt to download playlist page with given number."""
		query = query.decode(preferredencoding())
		self._downloader.to_stdout(u'[video.yahoo] query "%s": Downloading page %s' % (query, pagenum))

	def _real_initialize(self):
		self._yahoo_ie.initialize()
	
	def _real_extract(self, query):
		mobj = re.match(self._VALID_QUERY, query)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid search query "%s"' % query)
			return

		prefix, query = query.split(':')
		prefix = prefix[8:]
		query  = query.encode('utf-8')
		if prefix == '':
			self._download_n_results(query, 1)
			return
		elif prefix == 'all':
			self._download_n_results(query, self._max_yahoo_results)
			return
		else:
			try:
				n = long(prefix)
				if n <= 0:
					self._downloader.trouble(u'ERROR: invalid download number %s for query "%s"' % (n, query))
					return
				elif n > self._max_yahoo_results:
					self._downloader.to_stderr(u'WARNING: yvsearch returns max %i results (you requested %i)'  % (self._max_yahoo_results, n))
					n = self._max_yahoo_results
				self._download_n_results(query, n)
				return
			except ValueError: # parsing prefix as integer fails
				self._download_n_results(query, 1)
				return

	def _download_n_results(self, query, n):
		"""Downloads a specified number of results for a query"""

		video_ids = []
		already_seen = set()
		pagenum = 1

		while True:
			self.report_download_page(query, pagenum)
			result_url = self._TEMPLATE_URL % (urllib.quote_plus(query), pagenum)
			request = urllib2.Request(result_url, None, std_headers)
			try:
				page = urllib2.urlopen(request).read()
			except (urllib2.URLError, httplib.HTTPException, socket.error), err:
				self._downloader.trouble(u'ERROR: unable to download webpage: %s' % str(err))
				return

			# Extract video identifiers
			for mobj in re.finditer(self._VIDEO_INDICATOR, page):
				video_id = mobj.group(1)
				if video_id not in already_seen:
					video_ids.append(video_id)
					already_seen.add(video_id)
					if len(video_ids) == n:
						# Specified n videos reached
						for id in video_ids:
							self._yahoo_ie.extract('http://video.yahoo.com/watch/%s' % id)
						return

			if re.search(self._MORE_PAGES_INDICATOR, page) is None:
				for id in video_ids:
					self._yahoo_ie.extract('http://video.yahoo.com/watch/%s' % id)
				return

			pagenum = pagenum + 1

class YoutubePlaylistIE(InfoExtractor):
	"""Information Extractor for YouTube playlists."""

	_VALID_URL = r'(?:http://)?(?:\w+\.)?youtube.com/(?:(?:view_play_list|my_playlists)\?.*?p=|user/.*?/user/)([^&]+).*'
	_TEMPLATE_URL = 'http://www.youtube.com/view_play_list?p=%s&page=%s&gl=US&hl=en'
	_VIDEO_INDICATOR = r'/watch\?v=(.+?)&'
	_MORE_PAGES_INDICATOR = r'(?m)>\s*Next\s*</a>'
	_youtube_ie = None

	def __init__(self, youtube_ie, downloader=None):
		InfoExtractor.__init__(self, downloader)
		self._youtube_ie = youtube_ie
	
	@staticmethod
	def suitable(url):
		return (re.match(YoutubePlaylistIE._VALID_URL, url) is not None)

	def report_download_page(self, playlist_id, pagenum):
		"""Report attempt to download playlist page with given number."""
		self._downloader.to_stdout(u'[youtube] PL %s: Downloading page #%s' % (playlist_id, pagenum))

	def _real_initialize(self):
		self._youtube_ie.initialize()
	
	def _real_extract(self, url):
		# Extract playlist id
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid url: %s' % url)
			return

		# Download playlist pages
		playlist_id = mobj.group(1)
		video_ids = []
		pagenum = 1

		while True:
			self.report_download_page(playlist_id, pagenum)
			request = urllib2.Request(self._TEMPLATE_URL % (playlist_id, pagenum), None, std_headers)
			try:
				page = urllib2.urlopen(request).read()
			except (urllib2.URLError, httplib.HTTPException, socket.error), err:
				self._downloader.trouble(u'ERROR: unable to download webpage: %s' % str(err))
				return

			# Extract video identifiers
			ids_in_page = []
			for mobj in re.finditer(self._VIDEO_INDICATOR, page):
				if mobj.group(1) not in ids_in_page:
					ids_in_page.append(mobj.group(1))
			video_ids.extend(ids_in_page)

			if re.search(self._MORE_PAGES_INDICATOR, page) is None:
				break
			pagenum = pagenum + 1

		for id in video_ids:
			self._youtube_ie.extract('http://www.youtube.com/watch?v=%s' % id)
		return

class YoutubeUserIE(InfoExtractor):
	"""Information Extractor for YouTube users."""

	_VALID_URL = r'(?:http://)?(?:\w+\.)?youtube.com/user/(.*)'
	_TEMPLATE_URL = 'http://gdata.youtube.com/feeds/api/users/%s'
	_VIDEO_INDICATOR = r'http://gdata.youtube.com/feeds/api/videos/(.*)' # XXX Fix this.
	_youtube_ie = None

	def __init__(self, youtube_ie, downloader=None):
		InfoExtractor.__init__(self, downloader)
		self._youtube_ie = youtube_ie
	
	@staticmethod
	def suitable(url):
		return (re.match(YoutubeUserIE._VALID_URL, url) is not None)

	def report_download_page(self, username):
		"""Report attempt to download user page."""
		self._downloader.to_stdout(u'[youtube] user %s: Downloading page ' % (username))

	def _real_initialize(self):
		self._youtube_ie.initialize()
	
	def _real_extract(self, url):
		# Extract username
		mobj = re.match(self._VALID_URL, url)
		if mobj is None:
			self._downloader.trouble(u'ERROR: invalid url: %s' % url)
			return

		# Download user page
		username = mobj.group(1)
		video_ids = []
		pagenum = 1

		self.report_download_page(username)
		request = urllib2.Request(self._TEMPLATE_URL % (username), None, std_headers)
		try:
			page = urllib2.urlopen(request).read()
		except (urllib2.URLError, httplib.HTTPException, socket.error), err:
			self._downloader.trouble(u'ERROR: unable to download webpage: %s' % str(err))
			return

		# Extract video identifiers
		ids_in_page = []

		for mobj in re.finditer(self._VIDEO_INDICATOR, page):
			if mobj.group(1) not in ids_in_page:
				ids_in_page.append(mobj.group(1))
		video_ids.extend(ids_in_page)

		for id in video_ids:
			self._youtube_ie.extract('http://www.youtube.com/watch?v=%s' % id)
		return

class PostProcessor(object):
	"""Post Processor class.

	PostProcessor objects can be added to downloaders with their
	add_post_processor() method. When the downloader has finished a
	successful download, it will take its internal chain of PostProcessors
	and start calling the run() method on each one of them, first with
	an initial argument and then with the returned value of the previous
	PostProcessor.

	The chain will be stopped if one of them ever returns None or the end
	of the chain is reached.

	PostProcessor objects follow a "mutual registration" process similar
	to InfoExtractor objects.
	"""

	_downloader = None

	def __init__(self, downloader=None):
		self._downloader = downloader

	def set_downloader(self, downloader):
		"""Sets the downloader for this PP."""
		self._downloader = downloader
	
	def run(self, information):
		"""Run the PostProcessor.

		The "information" argument is a dictionary like the ones
		composed by InfoExtractors. The only difference is that this
		one has an extra field called "filepath" that points to the
		downloaded file.

		When this method returns None, the postprocessing chain is
		stopped. However, this method may return an information
		dictionary that will be passed to the next postprocessing
		object in the chain. It can be the one it received after
		changing some fields.

		In addition, this method may raise a PostProcessingError
		exception that will be taken into account by the downloader
		it was called from.
		"""
		return information # by default, do nothing
	
### MAIN PROGRAM ###
def main(argv):
	try:
		# Modules needed only when running the main program
		import getpass
		import optparse

		# Function to update the program file with the latest version from bitbucket.org
		def update_self(downloader, filename):
			# Note: downloader only used for options
			if not os.access (filename, os.W_OK):
				sys.exit('ERROR: no write permissions on %s' % filename)

			downloader.to_stdout('Updating to latest stable version...')
			latest_url = 'http://bitbucket.org/rg3/youtube-dl/raw/tip/LATEST_VERSION'
			latest_version = urllib.urlopen(latest_url).read().strip()
			prog_url = 'http://bitbucket.org/rg3/youtube-dl/raw/%s/youtube-dl' % latest_version
			newcontent = urllib.urlopen(prog_url).read()
			stream = open(filename, 'w')
			stream.write(newcontent)
			stream.close()
			downloader.to_stdout('Updated to version %s' % latest_version)

		# General configuration
		urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
		urllib2.install_opener(urllib2.build_opener(urllib2.HTTPCookieProcessor()))
		socket.setdefaulttimeout(300) # 5 minutes should be enough (famous last words)

		# Parse command line
		parser = optparse.OptionParser(
			usage='Usage: %prog [options] url...',
			version='2010.04.04',
			conflict_handler='resolve',
		)

		parser.add_option('-h', '--help',
				action='help', help='print this help text and exit')
		parser.add_option('-v', '--version',
				action='version', help='print program version and exit')
		parser.add_option('-U', '--update',
				action='store_true', dest='update_self', help='update this program to latest stable version')
		parser.add_option('-i', '--ignore-errors',
				action='store_true', dest='ignoreerrors', help='continue on download errors', default=False)
		parser.add_option('-r', '--rate-limit',
				dest='ratelimit', metavar='L', help='download rate limit (e.g. 50k or 44.6m)')

		authentication = optparse.OptionGroup(parser, 'Authentication Options')
		authentication.add_option('-u', '--username',
				dest='username', metavar='UN', help='account username')
		authentication.add_option('-p', '--password',
				dest='password', metavar='PW', help='account password')
		authentication.add_option('-n', '--netrc',
				action='store_true', dest='usenetrc', help='use .netrc authentication data', default=False)
		parser.add_option_group(authentication)

		video_format = optparse.OptionGroup(parser, 'Video Format Options')
		video_format.add_option('-f', '--format',
				action='store', dest='format', metavar='FMT', help='video format code')
		video_format.add_option('-b', '--best-quality',
				action='store_const', dest='format', help='download the best quality video possible', const='0')
		video_format.add_option('-m', '--mobile-version',
				action='store_const', dest='format', help='alias for -f 17', const='17')
		video_format.add_option('-d', '--high-def',
				action='store_const', dest='format', help='alias for -f 22', const='22')
		video_format.add_option('--all-formats',
				action='store_const', dest='format', help='download all available video formats', const='-1')
		parser.add_option_group(video_format)

		verbosity = optparse.OptionGroup(parser, 'Verbosity / Simulation Options')
		verbosity.add_option('-q', '--quiet',
				action='store_true', dest='quiet', help='activates quiet mode', default=False)
		verbosity.add_option('-s', '--simulate',
				action='store_true', dest='simulate', help='do not download video', default=False)
		verbosity.add_option('-g', '--get-url',
				action='store_true', dest='geturl', help='simulate, quiet but print URL', default=False)
		verbosity.add_option('-e', '--get-title',
				action='store_true', dest='gettitle', help='simulate, quiet but print title', default=False)
		verbosity.add_option('--get-thumbnail',
				action='store_true', dest='getthumbnail', help='simulate, quiet but print thumbnail URL', default=False)
		verbosity.add_option('--get-description',
				action='store_true', dest='getdescription', help='simulate, quiet but print video description', default=False)
		verbosity.add_option('--no-progress',
				action='store_true', dest='noprogress', help='do not print progress bar', default=False)
		parser.add_option_group(verbosity)

		filesystem = optparse.OptionGroup(parser, 'Filesystem Options')
		filesystem.add_option('-t', '--title',
				action='store_true', dest='usetitle', help='use title in file name', default=False)
		filesystem.add_option('-l', '--literal',
				action='store_true', dest='useliteral', help='use literal title in file name', default=False)
		filesystem.add_option('-o', '--output',
				dest='outtmpl', metavar='TPL', help='output filename template')
		filesystem.add_option('-a', '--batch-file',
				dest='batchfile', metavar='F', help='file containing URLs to download')
		filesystem.add_option('-w', '--no-overwrites',
				action='store_true', dest='nooverwrites', help='do not overwrite files', default=False)
		filesystem.add_option('-c', '--continue',
				action='store_true', dest='continue_dl', help='resume partially downloaded files', default=False)
		parser.add_option_group(filesystem)

		(opts, args) = parser.parse_args(argv)
        
		# Batch file verification
		batchurls = []
		if opts.batchfile is not None:
			try:
				batchurls = open(opts.batchfile, 'r').readlines()
				batchurls = [x.strip() for x in batchurls]
				batchurls = [x for x in batchurls if len(x) > 0]
			except IOError:
				sys.exit(u'ERROR: batch file could not be read')
		all_urls = batchurls + args

		# Conflicting, missing and erroneous options
		if opts.usenetrc and (opts.username is not None or opts.password is not None):
			parser.error(u'using .netrc conflicts with giving username/password')
		if opts.password is not None and opts.username is None:
			parser.error(u'account username missing')
		if opts.outtmpl is not None and (opts.useliteral or opts.usetitle):
			parser.error(u'using output template conflicts with using title or literal title')
		if opts.usetitle and opts.useliteral:
			parser.error(u'using title conflicts with using literal title')
		if opts.username is not None and opts.password is None:
			opts.password = getpass.getpass(u'Type account password and press return:')
		if opts.ratelimit is not None:
			numeric_limit = FileDownloader.parse_bytes(opts.ratelimit)
			if numeric_limit is None:
				parser.error(u'invalid rate limit specified')
			opts.ratelimit = numeric_limit

		# Information extractors
		youtube_ie = YoutubeIE()
		metacafe_ie = MetacafeIE(youtube_ie)
		youtube_pl_ie = YoutubePlaylistIE(youtube_ie)
		youtube_user_ie = YoutubeUserIE(youtube_ie)
		youtube_search_ie = YoutubeSearchIE(youtube_ie)
		google_ie = GoogleIE()
		google_search_ie = GoogleSearchIE(google_ie)
		photobucket_ie = PhotobucketIE()
		yahoo_ie = YahooIE()
		yahoo_search_ie = YahooSearchIE(yahoo_ie)
		generic_ie = GenericIE()

		# File downloader
		fd = FileDownloader({
			'usenetrc': opts.usenetrc,
			'username': opts.username,
			'password': opts.password,
			'quiet': (opts.quiet or opts.geturl or opts.gettitle or opts.getthumbnail or opts.getdescription),
			'forceurl': opts.geturl,
			'forcetitle': opts.gettitle,
			'forcethumbnail': opts.getthumbnail,
			'forcedescription': opts.getdescription,
			'simulate': (opts.simulate or opts.geturl or opts.gettitle or opts.getthumbnail or opts.getdescription),
			'format': opts.format,
			'outtmpl': ((opts.outtmpl is not None and opts.outtmpl.decode(preferredencoding()))
				or (opts.format == '-1' and opts.usetitle and u'%(stitle)s-%(id)s-%(format)s.%(ext)s')
				or (opts.format == '-1' and opts.useliteral and u'%(title)s-%(id)s-%(format)s.%(ext)s')
				or (opts.format == '-1' and u'%(id)s-%(format)s.%(ext)s')
				or (opts.usetitle and u'%(stitle)s-%(id)s.%(ext)s')
				or (opts.useliteral and u'%(title)s-%(id)s.%(ext)s')
				or u'%(id)s.%(ext)s'),
			'ignoreerrors': opts.ignoreerrors,
			'ratelimit': opts.ratelimit,
			'nooverwrites': opts.nooverwrites,
			'continuedl': opts.continue_dl,
			'noprogress': opts.noprogress,
			})
		fd.add_info_extractor(youtube_search_ie)
		fd.add_info_extractor(youtube_pl_ie)
		fd.add_info_extractor(youtube_user_ie)
		fd.add_info_extractor(metacafe_ie)
		fd.add_info_extractor(youtube_ie)
		fd.add_info_extractor(google_ie)
		fd.add_info_extractor(google_search_ie)
		fd.add_info_extractor(photobucket_ie)
		fd.add_info_extractor(yahoo_ie)
		fd.add_info_extractor(yahoo_search_ie)

		# This must come last since it's the
		# fallback if none of the others work
		fd.add_info_extractor(generic_ie)

		# Update version
		if opts.update_self:
			update_self(fd, sys.argv[0])

		# Maybe do nothing
		if len(all_urls) < 1:
			if not opts.update_self:
				parser.error(u'you must provide at least one URL')
			else:
				sys.exit()
		retcode = fd.download(all_urls)
		return retcode

	except DownloadError:
		sys.exit(1)
	except SameFileError:
		sys.exit(u'ERROR: fixed output name but more than one file to download')
	except KeyboardInterrupt:
		sys.exit(u'\nERROR: Interrupted by user')

if __name__ == '__main__':
        main(sys.argv[1:])
