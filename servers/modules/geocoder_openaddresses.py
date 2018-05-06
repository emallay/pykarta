# pykarta/servers/modules/geocoder_openaddresses.py
# Geocoder gets addresses from the MassGIS assessor's parcel map
# Last modified: 5 May 2018

import os, urllib, json, time, re
from pyspatialite import dbapi2 as db
import threading

thread_data = threading.local()

def application(environ, start_response):
	stderr = environ['wsgi.errors']

	cursor = getattr(thread_data, 'cursor', None)
	if cursor is None:
		db_filename = environ["DATADIR"] + "/openaddresses.sqlite"
		conn = db.connect(db_filename)
		cursor = conn.cursor()
		thread_data.cursor = cursor

	query_string = urllib.unquote_plus(environ['QUERY_STRING'])
	house_number, apartment_number, street, town, state, postal_code = json.loads(query_string)

	# Build the query template
	query_template = "SELECT longitude, latitude FROM addresses where {house} and street=? and town=? and state=?"
	address_base = [
		street,
		town,
		state
		]
	if postal_code is not None and postal_code != "":
		query_template += " and (postal_code=? or postal_code is null)"
		address_base.append(postal_code)

	# Result of SQL queries go here.
	row = None

	# If the apartment number is specified in the address, try a search with the exact house number and apartment number.
	if apartment_number:
		cursor.execute(query_template.replace("{house}", "apartment_number=? and house_number=?"), [apartment_number, house_number] + address_base)
		row = cursor.fetchone()

	# If the previous search was not performed or did not produce anything, try without the apartment number.
	if row is None:
		# Try for an exact match 
		#start_time = time.time()
		cursor.execute(query_template.replace("{house}", "house_number=?"), [house_number] + address_base)
		#stderr.write("elapsed: %f\n" % (time.time() - start_time))
		row = cursor.fetchone()

	# If nothing found, look for an entry which gives a range of house numbers which includes this one.
	if row is None and re.match(r'^\d+$', house_number):
		house_number = int(house_number)
		address = [house_number, house_number] + address[1:]
		cursor.execute(query_template.replace("{house}", "house_number_start <= ? and house_number_end >= ?"), [house_number, house_number] + address_base)
		row = cursor.fetchone()

	# If we got a match, insert the latitude and longitude into a GeoJSON point object.
	if row:
		feature = {
			'type':'Feature',
			'geometry':{'type':'Point', 'coordinates':[row[0], row[1]]},
			'properties':{'precision':'ROOF'}
			}	
	else:
		feature = None

	start_response("200 OK", [('Content-Type', 'application/json')])
	stderr.write("Result: %s\n" % str(feature))
	return [json.dumps(feature)]

