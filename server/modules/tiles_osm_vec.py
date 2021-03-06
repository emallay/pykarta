# pykarta/server/modules/tiles_osm_vec.py
# Produce GeoJSON tiles from OSM data stored in a Spatialite database
# Last modified: 25 May 2018

# References:
# https://docs.python.org/2/library/sqlite3.html
# http://www.gaia-gis.it/gaia-sins/spatialite-sql-4.2.0.html
# http://false.ekta.is/2011/04/pyspatialite-spatial-queries-in-python-built-on-sqlite3/
#
# https://github.com/TileStache/TileStache/blob/master/TileStache/Goodies/VecTiles/server.py
# http://northredoubt.com/n/2012/01/18/spatialite-and-spatial-indexes/

from __future__ import print_function
import os, json, re, gzip, io
from pykarta.geometry.projection import unproject_from_tilespace
from pykarta.server.dbopen import dbopen

# Sets of map layers for use together
map_layer_sets = {
	"osm-vector": [
			"osm-vector-landuse",
			"osm-vector-waterways",
			"osm-vector-water",
			"osm-vector-buildings",
			"osm-vector-roads",
			"osm-vector-admin-borders",
			"osm-vector-road-labels",
			"osm-vector-places",
			"osm-vector-pois",
			]
	}

# Map layers
layers = {
	'osm-vector-landuse': {
		'table': 'multipolygons',
		'columns': ('name', 'landuse'),
		'zoom_min': 10,
		'where_expressions': [
			'landuse IS NOT NULL AND Area(Geometry) > {a_speck}'
			]
		},
	'osm-vector-roads': {
		'table': 'lines',
		'columns': ('highway', 'z_order', 'railway', 'aeroway'),
		'other_tags': ('bridge', 'tunnel'),
		'zoom_min': 6,
		'where_expressions': [
			"highway = 'motorway'",	# z6
			"highway = 'motorway'",	# z7
			"highway IN ('motorway','motorway_link','trunk','trunk_link','primary')",	# z8
			"highway IN ('motorway','motorway_link','trunk','trunk_link','primary')",	# z9
			"highway IN ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary')",	# z10
			"highway IN ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary')",	# z11
			"highway IN ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential') OR ( highway IS NULL AND railway IS NOT NULL ) OR aeroway IS NOT NULL",	# z12
			"highway IN ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential') OR ( highway IS NULL AND railway IS NOT NULL ) OR aeroway IS NOT NULL",	# z13
			"highway IS NOT NULL or railway IS NOT NULL OR aeroway IS NOT NULL",	# z14 and higher
			],
		},
	'osm-vector-road-labels': {
		'table': 'lines',
		'columns': ('name', 'highway'),
		'other_tags': ('ref',),
		'zoom_min': 10,
		'where_expressions': [
			"highway IN ('motorway')",	# z10
			"highway IN ('motorway','trunk','primary')",	# z11
			"highway IN ('motorway','trunk','primary','secondary')",	# z12
			"highway IN ('motorway','trunk','primary','secondary','tertiary')",	# z13
			"highway IN ('motorway','trunk','primary','secondary','tertiary','unclassified','residential')",	# z14
			],
		'simplification': 5.0,
		'simplify-until': 99,
		'clip': False,
		},
	'osm-vector-admin-borders': {
		'table': 'lines',
		'columns': ('name', 'boundary', 'admin_level'),
		'zoom_min': 6,
		'where_expressions': [
			"boundary = 'administrative' and admin_level <= 4",		# z6 state
			"boundary = 'administrative' and admin_level <= 4",		# z7
			"boundary = 'administrative' and admin_level <= 4",		# z8
			"boundary = 'administrative' and admin_level <= 6",		# z9
			"boundary = 'administrative' and admin_level <= 6",		# z10 county
			"boundary = 'administrative' and admin_level <= 6", 	# z11
			"boundary = 'administrative' and admin_level <= 8",		# z12 town
			"boundary = 'administrative' and admin_level <= 8",		# z13
			"boundary = 'administrative' and admin_level <= 9", 	# z14 neighborhood
			],
		},
	'osm-vector-buildings': {
		'table': 'multipolygons',
		'columns': ('name',),
		'other_tags': ('addr:housenumber', 'addr:street'),
		'zoom_min': 13,
		'where_expressions': [
			"building IS NOT NULL and Area(Geometry) > {a_speck}",	# z13
			"building IS NOT NULL and Area(Geometry) > {a_speck}",	# z14
			"building IS NOT NULL and Area(Geometry) > {a_speck}",	# z15
			"building IS NOT NULL"
			],
		'clip': False,
		},
	'osm-vector-waterways': {
		'table': 'lines',
		'columns': ('name', 'waterway'),
		'zoom_min': 11,
		'where_expressions': [
			"waterway IN ('river')",		# z11
			"waterway IN ('river')",		# z12
			"waterway IS NOT NULL"			# z13
			]
		},
	'osm-vector-water': {
		'table': 'multipolygons',
		'columns': ('name',),
		'zoom_min': 4,
		'where_expressions': [
			"natural = 'water' and Area(Geometry) > {a_speck}"
			]
		},
	'osm-vector-places': {
		'table': 'points',
		'columns': ('name', 'place'),
		'other_tags': ('population',),
		'zoom_min': 6,
		'where_expressions': [
            "place IN ('state')",					# z6
            "place IN ('state','city')",			# z7
            "place IN ('state','city','county')",	# z8
            "place IN ('state','city','county')",	# z9
            "place IN ('county','city','town')",	# z10
            "place IN ('city','town','village')",	# z11
            "place IN ('city','town','village')",	# z12
            "place IN ('city','town','village','hamlet','suburb','locality')", # z13
			],
		'clip': False,		# unnecessary
		'simplification': None,
		'pad-bbox': False,
		},
	'osm-vector-pois': {
		'table': 'points',
		'columns': ('name', 'amenity'),
		'zoom_min': 15,
		'where_expressions': [
			"amenity IS NOT NULL"
			],
		},
		'clip': False,		# unnecessary
		'simplification': None,
		'pad-bbox': False,
	}

def get_tile(stderr, cursor, layer_name, small_bbox, large_bbox, zoom):
	layer = layers.get(layer_name)
	assert layer is not None

	bbox = large_bbox if layer.get('pad-bbox',True) else small_bbox

	geometry = "__geometry__"
	if layer.get('clip',True):
		geometry = "Intersection(%s,%s)" % (geometry, bbox)
	simplification = layer.get('simplification',1.0)		# one pixel
	if simplification is not None and zoom < layer.get('simplify-until',16):
		simplification = 360.0 / (2.0 ** zoom) / 256.0 * simplification
		geometry = "SimplifyPreserveTopology(%s,%f)" % (geometry, simplification)

	columns = layer['columns']
	if 'other_tags' in layer:
		columns = list(columns)
		columns.append('other_tags')

	# Build the part of the WHERE clause unique to this layer
	where_expressions = layer['where_expressions']
	where_index = (zoom - layer.get('zoom_min',0))
	if where_index < 0:
		return None
	where = where_expressions[where_index if where_index < len(where_expressions) else -1]
	pixel_in_degrees = 360.0 / (2.0 ** zoom) / 256.0
	a_speck = (pixel_in_degrees * pixel_in_degrees) * 10.0	
	where = where.replace("{a_speck}", str(a_speck))
	stderr.write("where: %s\n" % where)

	# In Spatialite we must join the spatial index table explicitly.
	spatial_test = "ROWID IN ( SELECT ROWID FROM SpatialIndex WHERE f_table_name = '{table}' AND search_frame = {bbox} )""".format(
		table=layer['table'],
		bbox=bbox
		)

	# Query to find what we want and do preliminary filtering using the spatial index.
	query = "SELECT ogc_fid as __id__, Geometry as __geometry__, {columns} FROM {table} WHERE ( {where} ) AND {spatial_test}".format(
		columns=(",".join(columns)),
		table=layer['table'],
		where=where,
		spatial_test=spatial_test,
		)

	# Enclose above query in another query which does more precision spatial
	# filtering and converts the geometry to GeoJSON.
	stderr.write("query: %s\n" % query)
	query = """SELECT AsGeoJSON({geometry}) as __geometry__, *
				FROM ( {query} ) AS q
				WHERE Intersects({bbox}, q.__geometry__)
			""".format(query=query,bbox=bbox, spatial_test=spatial_test, geometry=geometry)
	#stderr.write("query: %s\n" % query)

	cursor.execute(query)

	features = []
	for row in cursor:
		if row['__geometry__'] is None:
			stderr.write("invalid geometry: %s\n" % str(list(row)))
			continue

		row = dict(row)
		id = row.pop('__id__')
		geometry = json.loads(row.pop("__geometry__"))
		properties = {}

		if 'other_tags' in layer:
			other_tags = row.pop('other_tags')
			if other_tags is None:
				other_tags = dict()
			else:
				try:
					#other_tags = dict(map(lambda item: re.match(r'^"?([^"]+)"=>"([^"]*)"?$', item).groups(), other_tags.split('","')))
					other_tags = json.loads("{%s}" % other_tags.replace('"=>"','":"'))
					for tag in layer['other_tags']:
						value = other_tags.get(tag)	
						if value is not None:
							properties[tag] = value
				except AttributeError:
					stderr.write("Failed to parse other_tags: %s\n" % other_tags)

		for name, value in row.items():
			if value is not None:
				properties[name] = value

		if 'highway' in properties:
			m = re.match(r'^(.+)_link$', properties['highway'])
			if m:
				properties['highway'] = m.group(1)
				properties['is_link'] = 'yes'

		feature = {
			'type': 'Feature',
			'id': id,
			'geometry': geometry,
			'properties': properties,
			}
		features.append(feature)
	stderr.write("Found %d feature(s)\n" % len(features))

	geojson = {
		'type': 'FeatureCollection',
		'features': features,
		}

	return geojson

def application(environ, start_response):
	stderr = environ['wsgi.errors']

	m = re.match(r'^/([^/]+)/(\d+)/(\d+)/(\d+)\.geojson$', environ['PATH_INFO'])
	assert m, environ['PATH_INFO']
	layer_name = m.group(1)
	zoom = int(m.group(2))
	x = int(m.group(3))
	y = int(m.group(4))
	stderr.write("%s tile (%d, %d) at zoom %d...\n" % (layer_name, x, y, zoom))
	assert zoom <= 16

	cursor, response_headers = dbopen(environ, "osm_map.sqlite")
	if cursor is None:
		start_response("304 Not Modified", response_headers)
		return []

	p1 = unproject_from_tilespace(x, y, zoom)
	p2 = unproject_from_tilespace(x + 1.0, y + 1.0, zoom)
	small_bbox = 'BuildMBR(%f,%f,%f,%f,4326)' % (p1[1], p1[0], p2[1], p2[0])

	p1 = unproject_from_tilespace(x - 0.05, y - 0.05, zoom)
	p2 = unproject_from_tilespace(x + 1.05, y + 1.05, zoom)
	large_bbox = 'BuildMBR(%f,%f,%f,%f,4326)' % (p1[1], p1[0], p2[1], p2[0])

	if layer_name in map_layer_sets:
		layer_names = map_layer_sets[layer_name]
		geojson = {}
		for layer_name in layer_names:
			tile_geojson = get_tile(stderr, cursor, layer_name, small_bbox, large_bbox, zoom)
			if tile_geojson is not None:
				geojson[layer_name.replace("osm-vector-","")] = tile_geojson
	else:
		geojson = get_tile(stderr, cursor, layer_name, small_bbox, large_bbox, zoom)

	# Convert Python objects to JSON and compress
	out = io.BytesIO()
	with gzip.GzipFile(fileobj=out, mode='w') as fo:
		json.dump(geojson, fo)
	geojson = out.getvalue()

	start_response("200 OK", response_headers + [
		('Content-Type', 'application/json'),
		('Content-Encoding', 'gzip'),
		])
	return [geojson]

if __name__ == "__main__":
	import sys
	def dummy_start_response(code, headers):
		print(code, headers)
	application({
		'PATH_INFO': "/osm-vector-roads/16/19528/24304.geojson",
		'wsgi.errors': sys.stderr,
		}, dummy_start_response)
 
