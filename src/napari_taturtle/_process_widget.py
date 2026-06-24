
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
    QFormLayout,
    QMessageBox,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox
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


import os
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
from napari_taturtle.utils.visualization import plot_displacements


import tifffile

logger = logging.getLogger(__name__)

SAMPLE = 'Sample data'


@thread_worker
def _process_worker(min_x, max_x, min_y, max_y, image_folder_path, 
                    image_ref, crop, thickness_correction, alpha,
                    search_window, nr_cpu, slice_thickness, output_base_path,
                    enable_amst2=False, amst2_settings=None,
                    enable_taturtle_alignment=True,
                    save_as_stack=False):
    import shutil
    generated_files = []
    import tempfile
    from squirrel.workflows.elastix import (
        make_elastix_default_parameter_file_workflow,
        apply_multi_step_stack_alignment_workflow
    )
    from squirrel.library.io import load_data_handle
    from squirrel.library.data import norm_z_range
    from squirrel.library.elastix import register_with_elastix, ElastixStack
    from squirrel.workflows.amst import _z_smooth
    import multiprocessing as mp
    from multiprocessing.pool import ThreadPool
    import sys
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

    if enable_taturtle_alignment:
        output_folder_path.mkdir(parents=True, exist_ok=True)
        thickness_corr_folder_path.mkdir(parents=True, exist_ok=True)
        cropped_folder_path.mkdir(parents=True, exist_ok=True)

    start = time.time()

    n_images = len(list(image_folder_path.glob('*.tif*')))
    yield {UpdateType.N_IMAGES: n_images}
    displacements = []

    if enable_taturtle_alignment:
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
                displacements.append(
                    f"Slice {i + 1} ({template.tiff_files[i].name}): "
                    f"Shift X={shift_x}, Shift Y={shift_y}"
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
            yield {UpdateType.N_IMAGES: len_slices}
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
                displacements.append(
                    f"Slice {i + 1} ({template.tiff_files[i].name}): "
                    f"Shift X={shift_x2}, Shift Y={shift_y2}"
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
                    if dest.suffix.lower() in ('.tif', '.tiff'):
                        generated_files.append(dest)
            output_folder_path.rmdir()

        for subfolder in [cropped_folder_path, thickness_corr_folder_path]:
            if subfolder.exists():
                shutil.rmtree(subfolder)

        # Save displacement report
        if displacements:
            report_path = output_base_path / "displacements.txt"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("Taturtle Alignment Report\n")
                f.write("=" * 25 + "\n")
                f.write(f"Reference Image: {image_ref.name}\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("\n".join(displacements))
                f.write("\n")

    final_results_path = output_base_path
    if enable_amst2 and amst2_settings:
        yield {UpdateType.AMST2: (0, "AMST Phase 1: Generating parameters...")}
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_params_path = tmp.name
        
        try:
            make_elastix_default_parameter_file_workflow(
                tmp_params_path,
                transform=amst2_settings['transform'],
                elastix_parameters=amst2_settings['elx_params']
            )
            
            yield {UpdateType.AMST2: "AMST Phase 2: Running refinement..."}
            amst_transform_path = output_base_path / "amst_transforms.json"
            
            # Replicating amst_workflow logic to provide progress reporting
            yield {UpdateType.AMST2: (0, "AMST: Loading stack...")}
            # Use output_base_path if Taturtle was run, otherwise read from original image_folder_path
            input_for_amst = output_base_path if enable_taturtle_alignment else image_folder_path
            handle, stack_shape = load_data_handle(str(input_for_amst))
            
            yield {UpdateType.AMST2: (0, "AMST: Computing median template...")}
            # Compute median smoothed template (mst)
            radius = amst2_settings['radius']
            # We load the full stack into memory for smoothing (same as amst_workflow)
            stack_data = handle[:]
            mst = _z_smooth(stack_data, median_radius=radius, method='median')
            
            yield {UpdateType.AMST2: (0, "AMST: Starting slice registration...")}
            
            # Setup registration tasks
            transform_type = amst2_settings['transform']
            sigma = amst2_settings['sigma']
            
            tasks = []
            pool = ThreadPool(nr_cpu)
            
            for zidx in range(len(stack_data)):
                tasks.append(pool.apply_async(
                    register_with_elastix,
                    (mst[zidx], stack_data[zidx]),
                    dict(
                        transform=transform_type,
                        automatic_transform_initialization=False,
                        parameter_map=tmp_params_path,
                        gaussian_sigma=sigma,
                        normalize_images=False,
                        n_workers=1,
                        verbose=False
                    )
                ))
                
            pool.close()
            
            result_stack = []
            for i, task in enumerate(tasks):
                result_stack.append(task.get())
                perc = int(100 * (i + 1) / len(tasks))
                yield {UpdateType.AMST2: (perc, f"AMST: Registering slice {i+1}/{len(tasks)}")}
            
            pool.join()
            
            # Package into appropriate stack type
            if transform_type in ['bspline', 'BSplineTransform']:
                from squirrel.library.elastix import ElastixStack
                result_transforms = ElastixStack()
                for res in result_stack:
                    result_transforms.append(res[0])
            else:
                from squirrel.library.affine_matrices import AffineStack
                result_transforms = AffineStack(is_sequenced=True, pivot=[0., 0.])
                for res in result_stack:
                    result_transforms.append(res[0])
            
            # Save final results
            result_transforms.to_file(str(amst_transform_path))
            
            yield {UpdateType.AMST2: "AMST Phase 3: Plotting displacements..."}
            plot_path = output_base_path / "amst_displacements.png"
            plot_displacements(str(amst_transform_path), str(plot_path))
            
            yield {UpdateType.AMST2: "AMST Phase 4: Applying alignment..."}
            refinement_folder = output_base_path / "refinement"
            refinement_folder.mkdir(parents=True, exist_ok=True)
            apply_multi_step_stack_alignment_workflow(
                image_stack=str(input_for_amst),
                transform_paths=[str(amst_transform_path)],
                out_filepath=str(refinement_folder),
                auto_pad=False,
                n_workers=nr_cpu,
                write_result=True
            )
            final_results_path = refinement_folder
            # Copy refined images back to the main output folder for easy access
            if refinement_folder.exists():
                generated_files = []  # Reset generated_files because AMST refined files replace the previous ones!
                for f in refinement_folder.iterdir():
                    if f.is_file():
                        dest = output_base_path / f.name
                        if dest.exists():
                            dest.unlink()
                        shutil.move(str(f), str(dest))
                        if dest.suffix.lower() in ('.tif', '.tiff'):
                            generated_files.append(dest)
                # Optionally keep refinement folder for reference
                # shutil.rmtree(refinement_folder)  # Uncomment to clean up
        finally:
            if os.path.exists(tmp_params_path):
                try:
                    os.remove(tmp_params_path)
                except:
                    pass

    if save_as_stack and generated_files:
        yield {UpdateType.AMST2: (0, "Saving as TIFF stack...")}
        stack_file_path = output_base_path / f"{image_folder_path.name}_registered_stack.tif"
        if stack_file_path.exists():
            try:
                stack_file_path.unlink()
            except Exception as e:
                logger.warning(f"Could not delete existing stack file {stack_file_path}: {e}")
        
        # Sort generated files so they are added to the stack in order
        generated_files = sorted(generated_files, key=lambda p: p.name)
        
        with tifffile.TiffWriter(stack_file_path) as stack:
            for idx, f in enumerate(generated_files):
                img = tifffile.imread(f)
                stack.write(img, metadata={'axes': 'ZYX'}, contiguous=True)
                perc = int(100 * (idx + 1) / len(generated_files))
                yield {UpdateType.AMST2: (perc, f"Saving stack: slice {idx+1}/{len(generated_files)}")}
        
        # Delete the individual files we just stacked
        for f in generated_files:
            try:
                f.unlink()
            except Exception as e:
                logger.warning(f"Could not delete individual file {f}: {e}")
        final_results_path = stack_file_path
    else:
        final_results_path = output_base_path

    elapsed_time = time.time() - start
    yield {UpdateType.DONE}
    return elapsed_time, final_results_path
    



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

        ###############################
        # add banner
        self.layout().addWidget(BannerWidget('Taturtle - Registration',
                                             ICON_TATURTLE,
                                             'A toolbox to align SEM images',
                                             'https://github.com/vib-bic-code/napari-taturtle',
                                             'https://github.com/vib-bic-code/napari-taturtle/issues'))

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
        self.images_folder = FolderWidget('Choose')
        tab_disk.layout().addWidget(self.images_folder)

        # add to main layout
        self.layout().addWidget(self.tabs)
        

        ###############################
        self._build_params_widgets()

        # place holders
        self.worker = None
        self.sample_image = None
        self.n_im = 1
        self.load_from_disk = False
        self.image_files = []
        self.image_reference_index = 0

        # update image layer
        self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]

        # Update shapes layer
        self._layer_combo.choices = [y for y in self.viewer.layers if type(y) is napari.layers.Shapes]

        # actions
        self._set_actions()

    def _on_insert_layer(self, event=None):
        """Bind the update of layer choices in dropdowns to the renaming of inserted layers."""
        self._layer_combo.choices = [y for y in self.viewer.layers if type(y) is napari.layers.Shapes]
        self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]

    

    def _build_params_widgets(self):
        """Builds the parameter widgets for the custom widget."""
        # Create widgets for parameters        
        self.training_param_group = QGroupBox()
        self.training_param_group.setTitle("Parameters")
        self.training_param_group.setMinimumWidth(100)

        self._layer_combo = create_widget(annotation=napari.layers.Shapes)
        self._enable_taturtle_alignment = create_widget(annotation=bool, value=True)
        self._enable_crop = create_widget(annotation=bool)
        self._enable_thickness_correction = create_widget(annotation=bool)
        self._search_windows  = create_widget(annotation=int, widget_type='SpinBox', value=100, label='Search Window')
        self._slice_thickness  = create_widget(annotation=int, widget_type='FloatSpinBox', value=1.0, label='Slice Thickness')
        self._nr_cpu  = create_widget(annotation=int, widget_type='SpinBox', value=max(1, os.cpu_count() - 4), label='Nr CPU')
        self._output_folder = FolderWidget('Choose Output')
        self._save_as_stack = QCheckBox("Save as TIFF stack")

        # Navigation buttons
        self._prev_button = QPushButton('⏴')
        self._next_button = QPushButton('⏵')
        self._prev_button.setEnabled(False)
        self._next_button.setEnabled(False)
        
        self._slice_spinbox = QSpinBox()
        self._slice_spinbox.setMinimum(1)
        self._slice_spinbox.setEnabled(False)
        
        self._slice_label_total = QLabel('/ -')
        self._slice_label_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self._prev_button)
        
        slice_label = QLabel('Slice:')
        slice_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        nav_layout.addWidget(slice_label)
        nav_layout.addWidget(self._slice_spinbox)
        nav_layout.addWidget(self._slice_label_total)
        nav_layout.addWidget(self._next_button)

        self._params_form = QFormLayout()
        # magicgui widgets hold the Qt widget at `widget.native`
        self._params_form.addRow('Images Folder', self.images_folder)
        self._params_form.addRow('Rectangle Layer', self._layer_combo.native)
        self._params_form.addRow('', nav_layout)
        self._params_form.addRow('Output Folder', self._output_folder)
        self._params_form.addRow('', self._save_as_stack)
        self._params_form.addRow('Run Taturtle Alignment', self._enable_taturtle_alignment.native)
        self._params_form.addRow('Crop', self._enable_crop.native)
        self._params_form.addRow('Thickness correction', self._enable_thickness_correction.native)
        self._params_form.addRow('Slice Thickness', self._slice_thickness.native)
        self._params_form.addRow('Search Window', self._search_windows.native)
        self._params_form.addRow('Nr CPU', self._nr_cpu.native)

        # AMST2 Refinement
        self._enable_amst2 = QCheckBox("Add AMST Refinement")
        self._amst2_panel = QGroupBox("AMST Parameters")
        amst2_form = QFormLayout()
        
        self._amst2_transform = QLineEdit("bspline")
        self._amst2_elx_params = QLineEdit("FinalGridSpacingInPhysicalUnits:128 GridSpacingSchedule:2.0,1.4,1.2,1.0")
        self._amst2_gaussian_sigma = QDoubleSpinBox()
        self._amst2_gaussian_sigma.setValue(2.0)
        self._amst2_median_radius = QSpinBox()
        self._amst2_median_radius.setValue(7)
        
        amst2_form.addRow("Transform", self._amst2_transform)
        amst2_form.addRow("Elastix Params", self._amst2_elx_params)
        amst2_form.addRow("Gaussian Sigma", self._amst2_gaussian_sigma)
        amst2_form.addRow("Median Radius", self._amst2_median_radius)
        self._amst2_panel.setLayout(amst2_form)
        self._amst2_panel.setVisible(False)
        
        self._enable_amst2.toggled.connect(self._amst2_panel.setVisible)
        
        self._params_form.addRow('', self._enable_amst2)
        self._params_form.addRow('', self._amst2_panel)

        hlayout = QVBoxLayout()
        hlayout.addLayout(self._params_form)

        self.training_param_group.setLayout(hlayout)
        self.training_param_group.layout().setContentsMargins(5, 20, 5, 10)
        self.layout().addWidget(self.training_param_group)


        # process button        
        self.process_group = QGroupBox()
        self.process_group.setTitle("Process")
        self.process_group.setMinimumWidth(80)
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
        self._prev_button.clicked.connect(self._prev_slice)
        self._next_button.clicked.connect(self._next_slice)
        self._slice_spinbox.valueChanged.connect(self._on_spinbox_changed)
        self._enable_taturtle_alignment.changed.connect(self._update_taturtle_visibility)
        self._enable_thickness_correction.changed.connect(self._update_thickness_visibility)
        # Sync initial state
        self._update_taturtle_visibility()
        self._update_thickness_visibility()

    def _update_taturtle_visibility(self, event=None):
        visible = self._enable_taturtle_alignment.value
        self._enable_crop.native.setVisible(visible)
        self._enable_thickness_correction.native.setVisible(visible)
        self._search_windows.native.setVisible(visible)
        
        # update labels
        for widget in [self._enable_crop.native, self._enable_thickness_correction.native, self._search_windows.native]:
            label = self._params_form.labelForField(widget)
            if label:
                label.setVisible(visible)
        
        self._update_thickness_visibility()

    def _update_thickness_visibility(self, event=None):
        visible = self._enable_thickness_correction.value and self._enable_taturtle_alignment.value
        self._slice_thickness.native.setVisible(visible)
        label = self._params_form.labelForField(self._slice_thickness.native)
        if label:
            label.setVisible(visible)

    def _on_spinbox_changed(self, value):
        if self.image_files:
            new_index = value - 1
            if new_index != self.image_reference_index:
                self.image_reference_index = new_index
                self._display_current_slice()

    def _update_image(self):
        path = self.images_folder.get_folder()

        if path and path != '':
            folder_path = Path(path)
            self.image_files = sorted([f for f in folder_path.glob('*.tif*')])
            self.image_reference_index = 0
            self._display_current_slice()
        else:
            self.image_files = []
            self._update_nav_controls()

    def _update_nav_controls(self):
        n_files = len(self.image_files)
        if n_files > 0:
            self._slice_spinbox.blockSignals(True)
            self._slice_spinbox.setEnabled(True)
            self._slice_spinbox.setMaximum(n_files)
            self._slice_spinbox.setValue(self.image_reference_index + 1)
            self._slice_spinbox.blockSignals(False)
            
            self._slice_label_total.setText(f'/ {n_files}')
            self._prev_button.setEnabled(self.image_reference_index > 0)
            self._next_button.setEnabled(self.image_reference_index < n_files - 1)
        else:
            self._slice_spinbox.setEnabled(False)
            self._slice_label_total.setText('/ -')
            self._prev_button.setEnabled(False)
            self._next_button.setEnabled(False)

    def _next_slice(self):
        if self.image_files and self.image_reference_index < len(self.image_files) - 1:
            self.image_reference_index += 1
            self._display_current_slice()

    def _prev_slice(self):
        if self.image_files and self.image_reference_index > 0:
            self.image_reference_index -= 1
            self._display_current_slice()

    def _display_current_slice(self):
        if not self.image_files:
            return

        path = self.image_files[self.image_reference_index]
        
        def update_viewer(widget, image):
            if image is not None:
                if SAMPLE in widget.viewer.layers:
                    widget.viewer.layers[SAMPLE].data = image
                else:
                    widget.viewer.add_image(image, name=SAMPLE, visible=True)
                
                # Check if any Shapes layer exists
                shapes_layer = None
                for layer in widget.viewer.layers:
                    if isinstance(layer, Shapes):
                        shapes_layer = layer
                        break

                # If no Shapes layer found, create a new one
                if shapes_layer is None:
                    widget.viewer.add_shapes(
                        data=[],  # Start with empty shapes
                        shape_type='polygon',  # or 'rectangle', 'line', etc.
                        edge_color='blue',
                        face_color='transparent',
                        name='Select Fiducial Mark'
                    )
                widget._update_nav_controls()

        load_worker = loading_worker.loading_worker(path)
        load_worker.yielded.connect(lambda x: update_viewer(self, x))
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

        # AMST2 params
        enable_amst2 = self._enable_amst2.isChecked()
        amst2_settings = {
            'transform': self._amst2_transform.text(),
            'elx_params': self._amst2_elx_params.text().split(),
            'sigma': self._amst2_gaussian_sigma.value(),
            'radius': self._amst2_median_radius.value()
        }

        enable_taturtle_alignment = self._enable_taturtle_alignment.value

        if not enable_taturtle_alignment and not enable_amst2:
            ntf.show_info("Please enable at least Taturtle Alignment or AMST Refinement.")
            return

        layer_shape= self._layer_combo.value

        if enable_taturtle_alignment and (layer_shape.data is None or len(layer_shape.data) != 1):
            ntf.show_info("Please select a shape layer with 1 rectangle shape to define the region.")
            return
        
        if enable_taturtle_alignment:
            coordinate_region = layer_shape.data[0]

            min_y, min_x = coordinate_region.min(axis=0)  # napari is (y, x)
            max_y, max_x = coordinate_region.max(axis=0)

            min_y = int(min_y)
            min_x = int(min_x)
            max_y = int(max_y)
            max_x = int(max_x)
        else:
            min_y, min_x, max_y, max_x = 0, 0, 0, 0

        image_folder_path = Path(self.images_folder.get_folder())
        if not self.image_files:
            self.image_files = sorted([f for f in image_folder_path.glob('*.tif*')])
        
        if not self.image_files:
             ntf.show_info("No TIFF images found in selected folder.")
             return

        image_reference_path = self.image_files[self.image_reference_index]
        # image_ref = image_reference_path#.name

        # Output folder
        output_folder_val = self._output_folder.get_folder()
        if output_folder_val and output_folder_val != '':
            output_base_path = Path(output_folder_val)
        else:
            output_base_path = image_folder_path.parent

        save_as_stack = self._save_as_stack.isChecked()

        self.worker = _process_worker(
            min_x, max_x, min_y, max_y, image_folder_path, 
            image_reference_path, crop, thickness_correction, alpha,
            search_window, nr_cpu, slice_thickness, output_base_path,
            enable_amst2=enable_amst2, amst2_settings=amst2_settings,
            enable_taturtle_alignment=enable_taturtle_alignment,
            save_as_stack=save_as_stack
        )
        
        self.worker.yielded.connect(lambda x: self._update(x))
        self.worker.returned.connect(self._done)

        self.worker.start()

    def _add_image(self, image):
        if SAMPLE in self.viewer.layers:
            self.viewer.layers.remove(SAMPLE)

        if image is not None:
            self.viewer.add_image(image, name=SAMPLE, visible=True)
            self.sample_image = image

            # update the axes widget
            self.axes_widget.update_axes_number(len(image.shape))
            self.axes_widget.set_text_field(self.axes_widget.get_default_text())
    
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

        if UpdateType.AMST2 in updates:
            raw_val = updates[UpdateType.AMST2]
            if isinstance(raw_val, tuple):
                perc, text = raw_val
                self.pb_processing.setValue(perc)
                self.pb_processing.setFormat(text)
            else:
                self.pb_processing.setValue(100)
                self.pb_processing.setFormat(str(raw_val))

        if UpdateType.DONE in updates:
            self.pb_processing.setValue(100)
            self.pb_processing.setFormat(f'Processing done')
    
    def _done(self, result):
        self.state = State.IDLE
        self.process_button.setText('Process again')
        
        if isinstance(result, tuple):
            elapsed_time, results_path = result
        else:
            elapsed_time = result
            results_path = None

        # Format time
        seconds = int(elapsed_time)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        QMessageBox.information(
            self,
            "Process Finished",
            f"Registration completed successfully!\n\nTotal elapsed time: {time_str}"
        )

        if results_path and results_path.exists():
            load_results = QMessageBox.question(
                self,
                "Load Results",
                "Would you like to open the processed dataset as a stack in Napari?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if load_results == QMessageBox.Yes:
                if results_path.is_file():
                    self.viewer.open(str(results_path))
                else:
                    files = [str(f) for f in sorted(results_path.glob("*.tif*"))]
                    if files:
                        self.viewer.open(files, stack=True)
                    else:
                        ntf.show_info("No result images found in the output folder.")

    def set_layer(self, layer):
        self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]
        if layer in self.images.choices:
            self.images.native.value = layer

if __name__ == "__main__":
    # create a Viewer
    viewer = napari.Viewer()
    napari.run()
