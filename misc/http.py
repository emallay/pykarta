# pykarta/misc/http.py
# Copyright 2013--2018 Trinity College
# Last modified: 15 May 2018

import os
import re
try:
	import httplib
except ImportError:
	import http.client as httplib
import time

# Quick and dirty function to extract the hostname (possibly with port)
# and path (including query string) from a URL. 
def simple_url_split(url):
	m = re.match('^(https?)://([^/]+)(.*)$', url, re.IGNORECASE)
	assert m
	return (m.groups())

# Retrieve a file using httplib. Return a handle.
# For use in cases where urllib2.openurl() would be overkill.
# NOTE: this does not support redirects
def simple_urlopen(url, extra_headers={}):
	method, hostname, path = simple_url_split(url)
	if method == "https":
		conn = httplib.HTTPSConnection(hostname, timeout=30)
	else:
		conn = httplib.HTTPConnection(hostname, timeout=30)
	#print "GET %s" % path
	conn.request("GET", path, None, extra_headers)
	response = conn.getresponse()
	if response.status != 200 and response.status != 304:
		raise AssertionError("Failed to fetch \"%s\": %d %s" % (url, response.status, response.reason))
	return response

# Convert a Unix time to the format for an HTTP If-Modified-Since header.
http_weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
http_months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
def http_date(epoch_date):
	tm = time.gmtime(epoch_date)
	return "%s, %02d %s %04d %02d:%02d:%02d GMT" % (
		http_weekdays[tm.tm_wday],
		tm.tm_mday, http_months[tm.tm_mon - 1], tm.tm_year,
		tm.tm_hour, tm.tm_min, tm.tm_sec
		)

