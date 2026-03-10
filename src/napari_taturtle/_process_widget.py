"""
"""

import logging
from pathlib import Path
import napari
from napari.layers import Shapes
from napari.utils import notifications as ntf

from qtpy.QtCore import Qt
from magicgui.widgets import create_widget, Container, Widget

from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QTabWidget,
    QGroupBox,
    QLabel,
    QFormLayout
)

from napari_taturtle.resources import ICON_TATURTLE
from napari_taturtle.utils import (
    State,
    loading_worker
)
from napari_taturtle.widgets import (
    FolderWidget,
    ScrollWidgetWrapper,
    BannerWidget,
    create_progressbar,
    create_int_spinbox,
    create_double_spinbox,
    layer_choice,
    enable_crop
)


import logging
import time
from pathlib import Path

from taturtle import autocrop
from taturtle.region import Region
from taturtle.template_matching import (
    init_templatematching,
    run_template_matching,
    save_shift_image,
    template_median,
    unpack_result_template_step1,
)
from taturtle.thickness_correction import run_thickness_correction
from taturtle.utils import arguments_parser

from napari.qt.threading import thread_worker

from napari_taturtle.utils.taturtle_utils import UpdateType

logger = logging.getLogger(__name__)

SAMPLE = 'Sample data'


@thread_worker
def _process_worker(min_x, max_x, min_y, max_y, image_folder_path, 
                    image_ref, crop, thickness_correction, alpha,
                    search_window, nr_cpu, slice_thickness, output_base_path):
    import shutil
    print(f"min_y: {min_y}")
    print(f"min_x: {min_x}")
    print(f"max_y: {max_y}")
    print(f"max_x: {max_x}")

    region = Region(
        col1=min_x,
        col2=max_x,
        row1=min_y,
        row2=max_y,
    )

    """Start the main program."""
    output_folder_path = output_base_path / "output"
    thickness_corr_folder_path = output_base_path / "thickness_corr"
    cropped_folder_path = output_base_path / "cropped"

    output_folder_path.mkdir(parents=True, exist_ok=True)
    thickness_corr_folder_path.mkdir(parents=True, exist_ok=True)
    cropped_folder_path.mkdir(parents=True, exist_ok=True)

    start = time.time()

    n_images = len(list(image_folder_path.glob('*.tif*')))
    yield {UpdateType.N_IMAGES: n_images}

    if crop:
        yield {UpdateType.AUTOCROP: True}
        x_shift, y_shift = autocrop.run_autocrop(image_folder_path,
            image_ref,
            cropped_folder_path
        )
        # x_shift is top margin (rows), y_shift is left margin (cols)
        region = Region(
            col1=min_x - y_shift,
            col2=max_x - y_shift,
            row1=min_y - x_shift,
            row2=max_y - x_shift,
        )

        image_folder_path = cropped_folder_path
        image_ref = image_folder_path / image_ref.name

    if not thickness_correction:
        template = init_templatematching(
            image_folder_path, 
            image_ref, 
            row_range=[region.row1, region.row2], 
            col_range=[region.col1, region.col2]
        )
        patch_prev, prev_x, prev_y, patch_list = unpack_result_template_step1(
            run_template_matching(
                image_folder_path,
                template,
                alpha,
                search_window,
                nr_cpu,
            ),
            template.patch_ref,
            len(template.tiff_files),
        )
        results2 = run_template_matching(
            image_folder_path,
            template_median(template, patch_list),
            alpha,
            search_window // 4,
            nr_cpu,
        )
        for i, (pos_x2, pos_y2, _) in enumerate(results2):
            yield {UpdateType.IMAGE: i + 1}
            shift_x, shift_y = save_shift_image(
                image_folder_path,
                output_folder_path,
                template.tiff_files[i],
                template.init_x,
                template.init_y,
                pos_x2,
                pos_y2,
            )
            logger.info(
                f"Registration displacement ({i + 1}/{len(template.tiff_files)}): "
                f"{shift_x} - {shift_y}",
            )
    else:
        yield {UpdateType.THICKNESS: True}
        len_input_files, len_slices = run_thickness_correction(
            image_folder_path,
            slice_thickness,
            thickness_corr_folder_path
        )
        logger.info(
            f"Before {len_input_files}, After {len_slices} Thickness correction passed"
        )
        image_folder_path = thickness_corr_folder_path
        image_ref = image_folder_path / f"{image_ref.stem}_0.tif"
        if not image_ref.exists():
            # Fallback to first file if _0 doesn't exist for some reason
            files = sorted(list(image_folder_path.glob('*.tif*')))
            if files:
                image_ref = files[0]
        template = init_templatematching(
            image_folder_path, 
            image_ref, 
            row_range=[region.row1, region.row2], 
            col_range=[region.col1, region.col2]
        )
        patch_prev, prev_x, prev_y, patch_list = unpack_result_template_step1(
            run_template_matching(
                image_folder_path,
                template,
                alpha,
                search_window,
                nr_cpu,
            ),
            template.patch_ref,
            len(template.tiff_files),
        )
        results2 = run_template_matching(
            image_folder_path,
            template_median(template, patch_list),
            alpha,
            search_window,
            nr_cpu,
        )
        for i, (pos_x2, pos_y2, _) in enumerate(results2):
            yield {UpdateType.IMAGE: i + 1}
            shift_x2, shift_y2 = save_shift_image(
                image_folder_path,
                output_folder_path,
                template.tiff_files[i],
                template.init_x,
                template.init_y,
                pos_x2,
                pos_y2,
            )
            logger.info(
                f"Registration displacement ({i + 1}/{len(template.tiff_files)}): "
                f"{shift_x2} - {shift_y2}"
            )

    # Cleanup: Move files from "output" to output_base_path and remove subfolders
    if output_folder_path.exists():
        for f in output_folder_path.iterdir():
            if f.is_file():
                dest = output_base_path / f.name
                if dest.exists():
                    dest.unlink()
                shutil.move(str(f), str(dest))
        output_folder_path.rmdir()

    for subfolder in [cropped_folder_path, thickness_corr_folder_path]:
        if subfolder.exists():
            shutil.rmtree(subfolder)

    yield {UpdateType.DONE}
    



class ProcessWidgetWrapper(ScrollWidgetWrapper):
    def __init__(self, napari_viewer):      
        self.widget = ProcessWidget(napari_viewer)

        super().__init__(self.widget)


class ProcessWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()

        
        self.viewer = napari_viewer

        self.setLayout(QVBoxLayout())
        
        self.setMinimumWidth(200)
        self.setMaximumHeight(720)

        ###############################
        # add banner
        self.layout().addWidget(BannerWidget('Taturtle - Registration',
                                             ICON_TATURTLE,
                                             'A toolbox to align SEM images',
                                             'https://github.com/vib-bic-code/napari-taturtle',
                                             'https://github.com/vib-bic-code/napari-taturtle/issues'))

        # add GPU button
        #gpu_button = create_gpu_label()
        #gpu_button.setAlignment(Qt.AlignmentFlag.AlignRight)
        #self.layout().addWidget(gpu_button)

        # QTabs
        self.tabs = QTabWidget()
        tab_layers = QWidget()
        tab_layers.setLayout(QVBoxLayout())

        tab_disk = QWidget()
        tab_disk.setLayout(QVBoxLayout())

        # add tabs
        self.tabs.addTab(tab_disk, 'From disk')
        self.tabs.addTab(tab_layers, 'From layers')
        self.tabs.setMaximumHeight(120)

        # image layer tab
        self.images = layer_choice(annotation=napari.layers.Image, name="Images")
        tab_layers.layout().addWidget(self.images.native)

        # disk tab
        #self.lazy_loading = QCheckBox('Lazy loading')
        #tab_disk.layout().addWidget(self.lazy_loading)
        self.images_folder = FolderWidget('Choose')
        tab_disk.layout().addWidget(self.images_folder)

        # add to main layout
        self.layout().addWidget(self.tabs)

        
        #self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]
        

        ###############################
        self._build_params_widgets()
        #self._build_processing_widgets()

        # place holders
        self.worker = None
        #self.denoi_prediction = None
        self.sample_image = None
        #self.n_im = 0
        self.load_from_disk = False
        #self.scale = None

        # actions
        '''
        self.tabs.currentChanged.connect(self._update_tab_axes)
        self.predict_button.clicked.connect(self._start_prediction)
        self.images.changed.connect(self._update_layer_axes)
        self.images_folder.text_field.textChanged.connect(self._update_disk_axes)
        self.enable_3d.stateChanged.connect(self._update_3D)
        self.tiling_cbox.stateChanged.connect(self._update_tiling)
        '''
        # update image layer
        self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]

        # Update shapes layer
        self._layer_combo.choices = [y for y in self.viewer.layers if type(y) is napari.layers.Shapes]


        # actions
        self._set_actions()

        '''
        # update axes if necessary
        self._update_layer_axes()
        '''

    def _on_insert_layer(self, event=None):
        """Bind the update of layer choices in dropdowns to the renaming of inserted layers."""
        self._layer_combo.choices = [y for y in self.viewer.layers if type(y) is napari.layers.Shapes]
        self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]

    

    def _build_params_widgets(self):
        """Builds the parameter widgets for the custom widget."""
        # Create widgets for parameters
        # change annotation to napari.layers.Image (e.g) to restrict to just Images
        #self._layer_combo = create_widget(annotation=napari.layers.Layer)


        
        self.training_param_group = QGroupBox()
        self.training_param_group.setTitle("Parameters")
        self.training_param_group.setMinimumWidth(100)

        self._layer_combo = create_widget(annotation=napari.layers.Shapes)
        self._enable_crop = create_widget(annotation=bool)
        self._enable_thickness_correction = create_widget(annotation=bool)
        self._search_windows  = create_widget(annotation=int, widget_type='SpinBox', value=100, label='Search Window')
        self._slice_thickness  = create_widget(annotation=int, widget_type='FloatSpinBox', value=1.0, label='Slice Thickness')
        self._nr_cpu  = create_widget(annotation=int, widget_type='SpinBox', value=2, label='Nr CPU')
        self._output_folder = FolderWidget('Choose Output')

        formLayout = QFormLayout()
        # magicgui widgets hold the Qt widget at `widget.native`
        formLayout.addRow('Rectangle Layer', self._layer_combo.native)
        formLayout.addRow('Output Folder', self._output_folder)
        formLayout.addRow('Crop', self._enable_crop.native)
        formLayout.addRow('Thickness correction', self._enable_thickness_correction.native)
        formLayout.addRow('Search Window', self._search_windows.native)
        formLayout.addRow('Slice Thickness', self._slice_thickness.native)
        formLayout.addRow('Nr CPU', self._nr_cpu.native)
   

        #self.layout().addLayout(formLayout)   


        hlayout = QVBoxLayout()
        hlayout.addLayout(formLayout)

        self.training_param_group.setLayout(hlayout)
        self.training_param_group.layout().setContentsMargins(5, 20, 5, 10)
        self.layout().addWidget(self.training_param_group)


        # process button        
        self.process_group = QGroupBox()
        self.process_group.setTitle("Process")
        self.process_group.setMinimumWidth(80)
        self.process_group.setMaximumHeight(100)
        self.process_group.setLayout(QVBoxLayout())
        process_buttons = QWidget()

        
        # process progress bar
        self.pb_processing = create_progressbar(text_format=f'Process ?/?')
        self.pb_processing.setToolTip('Show the progress of the process')
        
        process_buttons.setLayout(QHBoxLayout())
        self.process_button = QPushButton('Process', self)
        process_buttons.layout().addWidget(QLabel(''))
        process_buttons.layout().addWidget(self.process_button)

        
        self.process_group.layout().addWidget(self.pb_processing)
        self.process_group.layout().addWidget(process_buttons)

        self.layout().addWidget(self.process_group)

    def _build_processing_widgets(self):
        self.process_group = QGroupBox()
        self.process_group.setTitle("Processing")
        self.process_group.setLayout(QVBoxLayout())
        self.process_group.layout().setContentsMargins(20, 20, 20, 0)

        # process progress bar
        self.pb_processing = create_progressbar(text_format=f'Process ?/?')
        self.pb_processing.setToolTip('Show the progress of the process')

        # predict button
        processes = QWidget()
        processes.setLayout(QHBoxLayout())
        self.process_button = QPushButton('Process', self)
        self.process_button.setEnabled(True)
        self.process_button.setToolTip('Run the registration on the images')

        processes.layout().addWidget(QLabel(''))
        processes.layout().addWidget(self.process_button)

        # add to the group
        self.process_group.layout().addWidget(self.pb_processing)
        self.process_group.layout().addWidget(processes)
        self.layout().addWidget(self.process_group)

    def _set_actions(self):
        self.images_folder.text_field.textChanged.connect(self._update_image)       
        self.viewer.layers.events.inserted.connect(self._on_insert_layer)    
        self.viewer.layers.events.removed.connect(self._on_insert_layer)
        self.process_button.clicked.connect(self._start_process)

    def _update_image(self):
        def add_image(widget, image):
            if image is not None:
                if SAMPLE in widget.viewer.layers:
                    widget.viewer.layers.remove(SAMPLE)

                widget.viewer.add_image(image, name=SAMPLE, visible=True)

                # update the axes widget
                #widget.axes_widget.update_axes_number(len(image.shape))
                #widget.axes_widget.set_text_field(widget.axes_widget.get_default_text())

                # Check if any Shapes layer exists
                shapes_layer = None
                for layer in widget.viewer.layers:
                    if isinstance(layer, Shapes):
                        shapes_layer = layer
                        break

                # If no Shapes layer found, create a new one
                if shapes_layer is None:
                    shapes_layer = widget.viewer.add_shapes(
                        data=[],  # Start with empty shapes
                        shape_type='polygon',  # or 'rectangle', 'line', etc.
                        edge_color='blue',
                        face_color='transparent',
                        name='Select Fiducial Mark'
                    )

        



        path = self.images_folder.get_folder()

        if path is not None and path != '':
            # load one image
            load_worker = loading_worker.loading_worker(path)
            load_worker.yielded.connect(lambda x: add_image(self, x))
            load_worker.start()

        


    def _start_process(self):
        alpha = 1.0
        """
        Starts the process of registration.
        """

        ''''''
        if self._enable_crop.value:
            crop = True
        else:
            crop = False

        if self._enable_thickness_correction.value:
            thickness_correction = True 
        else:
            thickness_correction = False

        if self._search_windows.value > 0:
            search_window = self._search_windows.value
        else:
            search_window = 100

        if self._slice_thickness.value > 0:
            slice_thickness = self._slice_thickness.value
        else:
            slice_thickness = 1.0

        if self._nr_cpu.value > 0:
            nr_cpu = self._nr_cpu.value
        else:
            nr_cpu = 2

        layer_shape= self._layer_combo.value

        if layer_shape.data is None or len(layer_shape.data) != 1:
            ntf.show_info("Please select a shape layer with 1 rectangle shape to define the region.")
            return
        
        coordinate_region = layer_shape.data[0]

        min_y, min_x = coordinate_region.min(axis=0)  # napari is (y, x)
        max_y, max_x = coordinate_region.max(axis=0)

        min_y = int(min_y)
        min_x = int(min_x)
        max_y = int(max_y)
        max_x = int(max_x)

        image_folder_path = Path(self.images_folder.get_folder())
        image_files = [f for f in image_folder_path.glob('*.tif*')]

        # TODO Make it changeable with button and save the index
        image_reference_index = 0

        image_reference_path = image_files[0]
        # image_ref = image_reference_path#.name

        # Output folder
        output_folder_val = self._output_folder.get_folder()
        if output_folder_val and output_folder_val != '':
            output_base_path = Path(output_folder_val)
        else:
            output_base_path = image_folder_path.parent

        self.worker = _process_worker(
            min_x, max_x, min_y, max_y, image_folder_path, 
            image_reference_path, crop, thickness_correction, alpha,
            search_window, nr_cpu, slice_thickness, output_base_path
        )
        
        self.worker.yielded.connect(lambda x: self._update(x))
        self.worker.returned.connect(self._done)

        self.worker.start()


    '''
    def _update_tiling(self, state):
        self.tiling_spin.setEnabled(state)

    def _update_3D(self):
        self.axes_widget.update_is_3D(self.enable_3d.isChecked())
        self.axes_widget.set_text_field(self.axes_widget.get_default_text())

    def _update_layer_axes(self):
        if self.images.value is not None:
            shape = self.images.value.data.shape

            # update shape length in the axes widget
            self.axes_widget.update_axes_number(len(shape))
            self.axes_widget.set_text_field(self.axes_widget.get_default_text())
    '''
    def _add_image(self, image):
        if SAMPLE in self.viewer.layers:
            self.viewer.layers.remove(SAMPLE)

        if image is not None:
            self.viewer.add_image(image, name=SAMPLE, visible=True)
            self.sample_image = image

            # update the axes widget
            self.axes_widget.update_axes_number(len(image.shape))
            self.axes_widget.set_text_field(self.axes_widget.get_default_text())
    '''
    def _update_disk_axes(self):
        path = self.images_folder.get_folder()

        # load one image
        load_worker = loading_worker(path)
        load_worker.yielded.connect(lambda x: self._add_image(x))
        load_worker.start()

    def _update_tab_axes(self):
        """
        Updates the axes widget following the newly selected tab.

        :return:
        """
        self.load_from_disk = self.tabs.currentIndex() == 1

        if self.load_from_disk:
            self._update_disk_axes()
        else:
            self._update_layer_axes()
    '''
    
    def _update(self, updates):
        if UpdateType.N_IMAGES in updates:
            self.n_im = updates[UpdateType.N_IMAGES]
            self.pb_processing.setValue(0)
            self.pb_processing.setFormat(f'Processing 0/{self.n_im}')

        if UpdateType.AUTOCROP in updates:
            self.pb_processing.setValue(0)
            self.pb_processing.setFormat('Autocropping...')

        if UpdateType.THICKNESS in updates:
            self.pb_processing.setValue(0)
            self.pb_processing.setFormat('Thickness correction...')

        if UpdateType.IMAGE in updates:
            val = updates[UpdateType.IMAGE]
            perc = int(100 * val / self.n_im + 0.5)
            self.pb_processing.setValue(perc)
            self.pb_processing.setFormat(f'Processing {val}/{self.n_im}')
            # self.viewer.layers[DENOISING].refresh()

        if UpdateType.DONE in updates:
            self.pb_processing.setValue(100)
            self.pb_processing.setFormat(f'Processing done')
    
    def _done(self):
        self.state = State.IDLE
        self.process_button.setText('Process again')

        '''
        if self.denoi_prediction is not None:
            if self.scale is not None:
                self.viewer.add_image(
                    self.denoi_prediction,
                    name=DENOISING,
                    scale = self.scale,
                    visible=True
                )
            else:
                self.viewer.add_image(self.denoi_prediction, name=DENOISING, visible=True)
        '''
    '''
    def _start_prediction(self):
        if self.state == State.IDLE:
            if self.axes_widget.is_valid():
                if self.get_model_path().exists() and self.get_model_path().is_file():
                    self.state = State.RUNNING

                    self.predict_button.setText('Stop')

                    if DENOISING in self.viewer.layers:
                        self.viewer.layers.remove(DENOISING)

                    self.denoi_prediction = None
                    self.worker = prediction_worker(self)
                    self.worker.yielded.connect(lambda x: self._update(x))
                    self.worker.returned.connect(self._done)
                    self.worker.start()
                else:
                    # TODO: napari 0.4.16 has ntf.show_error, but napari workflows requires 0.4.15 that doesn't
                    # ntf.show_error('Select a valid model path')
                    ntf.show_info('Select a valid model path')
            else:
                # TODO: napari 0.4.16 has ntf.show_error, but napari workflows requires 0.4.15 that doesn't
                # ntf.show_error('Invalid axes')
                ntf.show_info('Invalid axes')

        elif self.state == State.RUNNING:
            self.state = State.IDLE

    
    '''

    '''
    def get_model_path(self):
        return self.load_model_button.Model.value

    def set_model_path(self, path: Path):
        self.load_model_button.Model.value = path
    '''
    def set_layer(self, layer):
        self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]
        if layer in self.images.choices:
            self.images.native.value = layer
    '''
    # TODO call these methods throughout the workers
    def get_axes(self):
        return self.axes_widget.get_axes()

    def is_tiling_checked(self):
        return self.tiling_cbox.isChecked()

    def get_n_tiles(self):
        return self.tiling_spin.value()
    '''
'''
class DemoPrediction(PredictWidgetWrapper):
    def __init__(self, napari_viewer):
        super().__init__(napari_viewer)

        # dowload demo files
        from napari_n2v._sample_data import demo_files
        ntf.show_info('Downloading data can take a few minutes.')

        # get files
        img, model = demo_files()

        # add image to viewer
        name = 'Demo image'
        napari_viewer.add_image(img[0:471, 200:671], name=name)

        # modify path
        self.widget.set_model_path(model)
        self.widget.set_layer(name)
'''

if __name__ == "__main__":
    #from napari_n2v._sample_data import n2v_2D_data, n2v_3D_data

    # create a Viewer
    viewer = napari.Viewer()

    # add our plugin
    #viewer.window.add_dock_widget(PredictWidgetWrapper(viewer))

    #data = n2v_2D_data()
    #viewer.add_image(data[0][0][-10:], name=data[0][1]['name'])
  

    napari.run()
