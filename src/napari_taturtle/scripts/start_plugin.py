from pathlib import Path
import napari

from napari_taturtle import ProcessWidgetWrapper

# create a Viewer
viewer = napari.Viewer()

# add napari-n2v plugin
viewer.window.add_dock_widget(ProcessWidgetWrapper(viewer))

# load yout image
#path = Path('path/to/your/image.tif')
#data = titfffile.imread(path)

# add image to napari
#viewer.add_image(data[0][0], name=data[0][1]['name'])

# start UI
napari.run()