# !/usr/bin/python
# coding=utf-8
import sys, os
import importlib
import inspect

import numpy as np
from PySide2 import QtCore, QtWidgets
from PIL import Image
from PIL.ImageChops import invert

from pythontk import Img, File, Json
from uitk.switchboard import Switchboard
from uitk.widgets import rwidgets


__package__ = 'map-compositor'
__version__ = '0.5.5'


class Map_compositor():
	'''
	'''
	removeNormalMap = True
	renameMixedAOMap = True
	total_len = 0
	total_progress = 0
	masks=[]

	def compositeImages(self, sorted_images, output_dir, name='', callback=print):
		'''
		'''
		failed={}
		for typ, images in sorted_images.items():

			filepath0 = images[0][0]
			first_image = images[0][1]
			second_image = images[1][1] if len(images)>1 else first_image
			remaining_images = images[1:]
			width, height = first_image.size
			mode = first_image.mode
			ext = File.formatPath(filepath0, 'ext')

			key = Img.getImageTypeFromFilename(typ) #get key from type value in mapTypes dict. ie. 'Base_Color' from '_BC' value.
			bitDepth = Img.bitDepth[Img.mapModes[key]]

			if mode=='I': #unable to create mode I 32bit. use rgb until a fix is found. 
				first_image = first_image.convert('RGB')

			map_background = Img.getBackground(first_image, 'RGBA') #get the image background in RGBA format.
			map_background2 = Img.getBackground(second_image, 'RGBA') #get the image background in RGBA format.

			if not (map_background and map_background==map_background2): #if not a uniform background, or the background of map1 is not equal to map2:
				failed[typ] = images
				continue

			else:
				if not self.masks and map_background[3]==0:
					callback('<i><br>Attempting to create masks using source <b>{}</b> ..</i>'.format(typ))
					images = [i[1] for i in images] #get the images from the (filepath, image) list of tuples.
					self.masks = Img.createMask(images, map_background); #debug: [self.saveImageFile(i, name=output_dir+'/'+str(n)+'_mask.png') for n, i in enumerate(self.masks)]

			length = len(remaining_images) if len(remaining_images)>1 else 1

			callback('<u><br><b>{} {} {}bit {}</b> {}x{}:</u>'.format(typ.rstrip('_'), Img.mapModes[key], bitDepth, ext.upper(), width, height))
			self.total_progress+=1
			callback(File.formatPath(filepath0, 'file'), (1/length) *100, (self.total_progress/self.total_len) *100) #first_image self.total_progress.


			composited_image = first_image.convert('RGBA')
			for n, (file, im) in enumerate(remaining_images, 1):
				self.total_progress+=1
				callback(File.formatPath(file, 'file'), (n/length) *100, (self.total_progress/self.total_len) *100) #remaining_images self.total_progress.

				if mode=='I':
					im = im.convert('RGB')
				im = Img.replaceColor(im, from_color=map_background, mode='RGBA')

				try:
					composited_image = Image.alpha_composite(composited_image, im.convert('RGBA')) #(background, foreground)
				except ValueError as error:
					callback('<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> '+str(error)+'</hl>')

			try:
				if map_background[3]==0:
					map_background = Img.mapBackgrounds[key] #using this may not 
				mode = Img.mapModes[key]
			except KeyError as error:
				pass

			result = Image.new('RGBA', composited_image.size, map_background[:3]+(255,))
			result.paste(composited_image, mask=composited_image)
			result = result.convert(mode) if not mode=='I' else result.convert('RGB') #return im to it's original mode.

			result.save('{}/{}_{}.{}'.format(output_dir, name, typ, ext))

			#convert normal maps:
			if not Img.containsMapTypes(sorted_images, 'Normal_OpenGL'):
				try: #convert DirectX to OpenGL
					index = Img.mapTypes['Normal_DirectX'].index(typ)

					new_type = Img.mapTypes['Normal_OpenGL'][index]
					inverted_image = Img.invertChannels(result, 'g')
					inverted_image.save('{}/{}_{}.{}'.format(output_dir, name, new_type, ext))

					callback('<br><u><b>{} {} {}bit {}</b> {}x{}:</u>'.format(new_type.rstrip('_'), mode, bitDepth, ext.upper(), width, height))
					callback('Created using {}_{}.{}'.format(name, typ, ext))

				except ValueError as error:
					if not Img.containsMapTypes(sorted_images, 'Normal_DirectX'):
						try: #convert OpenGL to DirectX
							index = Img.mapTypes['Normal_OpenGL'].index(typ)

							new_type = Img.mapTypes['Normal_DirectX'][index]
							inverted_image = Img.invertChannels(result, 'g')
							inverted_image.save('{}/{}_{}.{}'.format(output_dir, name, new_type, ext))

							callback('<br><u><b>{} {} {}bit {}</b> {}x{}:</u>'.format(new_type.rstrip('_'), mode, bitDepth, ext.upper(), width, height))
							callback('Created using {}_{}.{}'.format(name, typ, ext))

						except ValueError as error:
							continue
		return failed


	def retryFailed(self, failed, name, callback):
		'''
		'''
		failed_images={}
		for typ, images in failed.items():

			for n, (filepath, image) in enumerate(images):

				try:
					mask = self.masks[n]
				except IndexError as error:
					callback('<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Composite failed: <b>{}_{}: {}</b></hl>'.format(name, typ, filepath))
					continue

				key = Img.getImageTypeFromFilename(typ) #

				try:
					background = Img.mapBackgrounds[key]
					im = self.fillMaskedArea(image, background, mask)
					mode = Img.mapModes[key]
					im = im.convert(mode)

				except KeyError as error:
					background = Img.getBackground(image, 'RGBA', average=True) #get the averaged background color.
					im = self.fillMaskedArea(image, background, mask)

				try:
					failed_images[typ].append((filepath, im))
				except KeyError as error:
					failed_images[typ] = [(filepath, im)]

		return failed_images



class Map_compositor_slots(Map_compositor):

	msg_intro = '''<u>Required Substance Painter Export Settings:</u><br>Padding: <b>Dilation + transparent</b> or <b>Dilation + default backgound color</b>.
		<br><br><u>Works best with map filenames (case insensitive) ending in:</u>'''
	msg_error_maskCreation = '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Unable to create masks from the source images.<br>To create a mask, at least one set of source maps need to a transparent or have a solid single color backround,<br>alternatively a set of mask maps can be added to the source folder. ex. &lt;map_name&gt;_mask.png</hl>'
	msg_operation_successful = '<br><hl style="color:rgb(0, 255, 255);"><b>COMPLETED.</b></hl>'

	for k, v in Img.mapTypes.items(): #format msg_intro using the mapTypes in imtools.
		line = '<br><b>{}:</b>  {}'.format(k, v)
		msg_intro+=line

	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		'''Slot classes defined in a switchboard instance inherit an `sb` (switchboard) attribute by default.
		'''
		path = '{}/map_compositor.json'.format(self.sb.defaultDir)
		Json.setJsonFile(path) #set json file name

		#load any saved info:
		try:
			prev_input_dirs = [i for i in Json.getJson('prev_input_dirs') if not i=='/']
			self.sb.ui.cmb000.addItems_(prev_input_dirs[-10:], '/')
		except TypeError as error:
			pass
		try:
			prev_output_dirs = [i for i in Json.getJson('prev_output_dirs') if not i=='/']
			self.sb.ui.cmb001.addItems_(prev_output_dirs[-10:], '/', ascending=True)
		except TypeError as error:
			pass
		try:
			prev_map_names = [i for i in Json.getJson('prev_map_names') if not i=='/']
			self.sb.ui.cmb002.addItems_(prev_map_names[-10:], '/', ascending=True)
		except TypeError as error:
			pass

		self.orig_toolTip_txt000 = self.sb.ui.txt000.toolTip()
		self.orig_toolTip_txt001 = self.sb.ui.txt001.toolTip()

		self.sb.ui.txt000.setText(Json.getJson('input_dir'))
		self.sb.ui.txt001.setText(Json.getJson('output_dir'))
		self.sb.ui.txt002.setText(Json.getJson('map_name'))
		self.sb.ui.txt003.setText(self.msg_intro)

		#disable the browser open buttons if there isn't a directory.
		if not self.sb.ui.txt000.text():
			self.sb.ui.b003.setDisabled(True)
		if not self.sb.ui.txt001.text():
			self.sb.ui.b004.setDisabled(True)


	@property
	def input_dir(self) -> str:
		'''Get the source directory from the user input text field.

		:Return:
			(str) directory path.
		'''
		return self.sb.ui.txt000.text()


	@property
	def output_dir(self) -> str:
		'''Get the export directory from the user input text field.

		:Return:
			(str) directory path.
		'''
		return self.sb.ui.txt001.text()


	@property
	def map_name(self) -> str:
		'''Get the map name from the user input text field.

		:Return:
			(str)
		'''
		return self.sb.ui.txt002.text()


	def cmb000(self, index):
		'''
		'''
		cmb = self.sb.ui.cmb000
		txt = self.sb.ui.txt000

		if index>0:
			text = cmb.itemText(index)
			txt.setText(text)
			cmb.setCurrentIndex(0)


	def cmb001(self, index):
		'''
		'''
		cmb = self.sb.ui.cmb001
		txt = self.sb.ui.txt001

		if index>0:
			text = cmb.itemText(index)
			txt.setText(text)
			cmb.setCurrentIndex(0)


	def cmb002(self, index):
		'''
		'''
		cmb = self.sb.ui.cmb002
		txt = self.sb.ui.txt002

		if index>0:
			text = cmb.itemText(index)
			txt.setText(text)
			cmb.setCurrentIndex(0)


	def txt000(self, text=None):
		'''
		'''
		cmb = self.sb.ui.cmb000
		txt = self.sb.ui.txt000
		text = txt.text()

		if text:
			curItems = cmb.items[1:]
			if not text in curItems and File.isValidPath(text): #add value to json dict.
				cmb.addItems_(curItems+[text], '/', ascending=True)
				Json.setJson('prev_input_dirs', cmb.items)

			self.sb.ui.b003.setDisabled(False)
			txt.setToolTip(text)
		else:
			self.sb.ui.b003.setDisabled(True)
			txt.setToolTip(self.orig_toolTip_txt000)

		Json.setJson('input_dir', text)


	def txt001(self, text=None):
		'''
		'''
		cmb = self.sb.ui.cmb001
		txt = self.sb.ui.txt001
		text = txt.text()

		if text:
			curItems = cmb.items[1:]
			if not text in curItems and File.isValidPath(text): #add value to json dict.
				cmb.addItems_(curItems+[text], '/', ascending=True)
				Json.setJson('prev_output_dirs', cmb.items)

			self.sb.ui.b004.setDisabled(False)
			txt.setToolTip(text)
		else:
			self.sb.ui.b004.setDisabled(True)
			txt.setToolTip(self.orig_toolTip_txt001)

		Json.setJson('output_dir', text)


	def txt002(self, text=None):
		'''
		'''
		cmb = self.sb.ui.cmb002
		txt = self.sb.ui.txt002
		text = txt.text()

		if text:
			curItems = cmb.items[1:]
			if not text in cmb.items: #add value to json dict.
				cmb.addItems_(curItems+[text], '/', ascending=True)
				Json.setJson('prev_map_names', cmb.items)

		Json.setJson('map_name', text)


	def b000(self):
		'''
		'''
		input_dir = Img.getImageDirectory()
		if input_dir:
			self.sb.ui.txt000.setText(input_dir)
			self.txt000(input_dir) #set the text AND enable the 'open' button if disabled.


	def b001(self):
		'''
		'''
		output_dir = Img.getImageDirectory()
		if output_dir:
			self.sb.ui.txt001.setText(output_dir)
			self.txt001(output_dir) #set the text AND enable the 'open' button if disabled.


	def b002(self):
		'''
		'''
		self.sb.ui.txt003.clear()

		images = Img.getImages(self.input_dir)
		self.process(images, self.input_dir, self.output_dir, self.map_name, self.callback)


	def b003(self):
		'''
		'''
		try:
			os.startfile(self.input_dir)
		except (FileNotFoundError, TypeError) as error:
			pass


	def b004(self):
		'''
		'''
		try:
			os.startfile(self.output_dir)
		except (FileNotFoundError, TypeError) as error:
			pass


	def process(self, images, input_dir, output_dir, map_name=None, callback=print):
		'''
		'''
		self.callback('<i>Loading maps ..</i>', clear=True)

		if not (input_dir and output_dir):
			self.sb.ui.txt003.clear() if not 'Error:' in self.sb.ui.txt003.toPlainText() else None
			self.sb.ui.txt003.append('<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> You must specify a source and destination directory.</hl>')
			return
		elif not File.isValidPath(input_dir):
			self.sb.ui.txt003.clear() if not 'Error:' in self.sb.ui.txt003.toPlainText() else None
			self.sb.ui.txt003.append('<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Directory is invalid: <b>{}</b>.</hl>'.format(input_dir))
			return
		elif not File.isValidPath(output_dir):
			self.sb.ui.txt003.clear() if not 'Error:' in self.sb.ui.txt003.toPlainText() else None
			self.sb.ui.txt003.append('<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Directory is invalid: <b>{}</b>.</hl>'.format(output_dir))
			return

		#save the current lineEdit values to the json file.
		self.txt000()
		self.txt001()
		self.txt002()

		if not map_name:
			map_name = File.formatPath(input_dir, 'dir')

		sorted_images = Img.sortImagesByType(images)
		total_maps = 1 if Img.containsMapTypes(sorted_images, 'Normal_DirectX|Normal_OpenGL') else None #account for an additional converted normal map.

		if self.removeNormalMap:
			if Img.containsMapTypes(sorted_images, ['Normal_DirectX', 'Normal_OpenGL']):
				normal = next((i for i in sorted_images.keys() #delete the standard normal map from the output.
					if Img.getImageTypeFromFilename(i)=='Normal'), False)
				if normal:
					del sorted_images[normal]

		if self.renameMixedAOMap:
			if 'Mixed_AO' in sorted_images and not 'AmbientOcclusion' in sorted_images:
				sorted_images['AmbientOcclusion'] = sorted_images.pop('Mixed_AO')

		self.total_maps = len(sorted_images) + total_maps
		self.total_len = sum([len(i) for i in sorted_images.values()])

		callback('<i>Sorting <b>{}</b> images, into <b>{}</b> maps ..</i>'.format(self.total_len, self.total_maps))

		try:
			failed = self.compositeImages(sorted_images, output_dir, map_name, callback)
			if failed:
				callback('<i><br>Processing additional maps that require a mask ..</i>')
				failed_images = self.retryFailed(failed, map_name, callback)
				if failed_images:
					self.compositeImages(failed_images, output_dir, map_name, callback)
					callback(self.msg_operation_successful)
				else:
					callback(self.msg_error_maskCreation)
			else:
				callback(self.msg_operation_successful)

		except Exception as error:
			callback('<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Operation encountered the following error:<br>{}</hl>'.format(error))
			raise error


	def callback(self, string, progress=None, total_progress=None, clear=False):
		'''
		'''
		if clear:
			self.sb.ui.txt003.clear()
		self.sb.ui.txt003.append(string)

		if progress is not None:
			self.sb.ui.progressBar.setValue(progress)

		if total_progress is not None:
			self.sb.ui.progressBar_total.setValue(total_progress)

			QtWidgets.QApplication.processEvents()



class Map_compositor_main(QtWidgets.QMainWindow):
	'''Constructs the main ui window for `Map_compositor` class.
	'''
	app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv) #return the existing QApplication object, or create a new one if none exists.

	def __init__(self, parent=None):
		super().__init__(parent)

		self.sb = Switchboard(self, widgetLoc=rwidgets, slotLoc=Map_compositor_slots)
		self.sb.map_compositor.alias = 'ui'

		self.setCentralWidget(self.sb.ui)
		self.sb.setStyle(self.sb.ui.widgets)

		try:
			self.sb.ui.connected = True
		except Exception as error:
			print (f'# Error: {__file__} in Map_compositor_main\n#\tCould not establish slot connections for `{self.sb.ui.name}`\n#\t{error}')
		self.sb.ui.isInitialized = True
		self.activateWindow()


# -----------------------------------------------------------------------------









# -----------------------------------------------------------------------------

if __name__ == "__main__":

	main = Map_compositor_main()
	main.show()

	sys.exit(main.app.exec_()) # run app, show window, wait for input, then terminate program with a status code returned from app.

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------



# Deprecated ---------------------










#module name
# print (__name__)
# ======================================================================
# Notes
# ======================================================================