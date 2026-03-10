from pathlib import Path
from tifffile import imread

from napari.qt.threading import thread_worker


@thread_worker(start_thread=False)
def loading_worker(path):
    images_path = Path(path)
    
    if images_path.is_file():
        yield imread(str(images_path))
    else:
        image_files = sorted([f for f in images_path.glob('*.tif*')])

        # load the first image
        if len(image_files) > 0:
            yield imread(str(image_files[0]))