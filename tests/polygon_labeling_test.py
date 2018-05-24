#! /usr/bin/python

import sys
sys.path.insert(1,"../..")
from pykarta.geometry import *

points = [
	(230.69803743588272, -12.80152180197183),
	(230.7776694044005, -6.943896176293492),
	(233.1235669333255, -0.9983627885812894),
	(242.30851015110966, 9.023812301456928),
	(236.08579413336702, 10.969468633644283),
	(231.45691363560036, 6.02480027556885),
	(229.47044465783983, 1.7477599720004946),
	(228.48070542223286, -9.256459996337071),
	(226.34700524725486, -12.80152180197183),
	(230.69803743588272, -12.80152180197183)
	]
polygon_obj = Polygon(points)

print "bbox:", polygon_obj.get_bbox()
print "area:", polygon_obj.area()
print "centroid:", polygon_obj.centroid()
print "label_center:", polygon_obj.choose_label_center()

