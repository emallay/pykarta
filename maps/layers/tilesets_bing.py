# pykarta/maps/layers/tilesets_bing.py
# Copyright 2013--2018, Trinity College
# Last modified: 26 April 2018

from tilesets_base import tilesets, MapTilesetRaster
import json
from pykarta.misc.http import simple_urlopen
from pykarta.maps.image_loaders import surface_from_file_data

#-----------------------------------------------------------------------------
# Microsoft Bing map layers
# See http://www.bingmapsportal.com/
# See http://www.microsoft.com/maps/product/terms.html
# OsmGpsMap does not document #W but implements it
# FIXME: add include=ImageryProviders to query and use result
#-----------------------------------------------------------------------------
class MapTilesetBing(MapTilesetRaster):
	def __init__(self, key, metadata_url=None, **kwargs):
		MapTilesetRaster.__init__(self, key, **kwargs)
		self.metadata_url = metadata_url
	def online_init(self):
		url = self.metadata_url.replace("{api_key}", self.api_key)
		response = simple_urlopen(url, extra_headers=self.extra_headers)
		metadata = json.load(response)
		print "Bing metadata:", json.dumps(metadata, indent=4, separators=(',', ': '))
		resource = metadata['resourceSets'][0]['resources'][0]
		url_template = resource['imageUrl'].replace("{subdomain}","{s}").replace("{culture}","en-us")
		print "Bing URL template:", url_template
		self.set_url_template(url_template)
		self.subdomains = resource['imageUrlSubdomains']
		self.zoom_min = resource['zoomMin']
		self.zoom_max = resource['zoomMax']
		#print "Bing zoom levels: %d thru %d" % (self.zoom_min, self.zoom_max)
		self.attribution = surface_from_file_data(simple_urlopen(metadata['brandLogoUri']).read())

for our_layer_key, bing_layer_key in (
	('road', 'Road'),
	('aerial', 'Aerial'),
	('aerial-with-labels', 'AerialWithLabels')
	):
	tilesets.append(MapTilesetBing('bing-%s' % our_layer_key,
		metadata_url='http://dev.virtualearth.net/REST/v1/Imagery/Metadata/%s?key={api_key}' % bing_layer_key,
		attribution="Bing",
		api_key_name="bing"
		))

