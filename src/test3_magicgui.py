import napari
from qtpy.QtWidgets import QVBoxLayout, QWidget

from magicgui.widgets import create_widget, Container, Widget
from magicgui import magic_factory

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
from napari_taturtle.resources import ICON_TATURTLE


class CustomWidget(QWidget):
    """A custom widget class."""

    #@magic_factory(auto_call=True, do_crop={'label': ' ', 'widget_type': 'Checkbox', 'visible': True})
    #def enable_crop(do_crop: bool = False) -> bool:
    #    return do_crop
    

    def __init__(self) -> None:
        super().__init__()
        self.setLayout(QVBoxLayout())
        
        self.setMinimumWidth(200)
        self.setMaximumHeight(720)

        ###############################
        # add banner
        self.layout().addWidget(BannerWidget('Tortuga - Registration',
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
        self.lazy_loading = QCheckBox('Lazy loading')
        tab_disk.layout().addWidget(self.lazy_loading)
        self.images_folder = FolderWidget('Choose')
        tab_disk.layout().addWidget(self.images_folder)

        # add to main layout
        self.layout().addWidget(self.tabs)

        
        #self.images.choices = [x for x in self.viewer.layers if type(x) is napari.layers.Image]
        
        self._build_params_widgets()

        '''
        # change annotation to napari.layers.Image (e.g) to restrict to just Images
        #self._layer_combo = create_widget(annotation=napari.layers.Layer)
        self._layer_combo = create_widget(annotation=napari.layers.Shapes)
        self._enable_crop = create_widget(annotation=bool)
        self._search_windows  = create_widget(annotation=int, widget_type='SpinBox', value=100, label='Search Window')
        self._slice_thickness  = create_widget(annotation=int, widget_type='FloatSpinBox', value=1.0, label='Slice Thickness')
        self._nr_cpu  = create_widget(annotation=int, widget_type='SpinBox', value=2, label='Nr CPU')


        formLayout = QFormLayout()
        # magicgui widgets hold the Qt widget at `widget.native`
        formLayout.addRow('Rectangle Layer', self._layer_combo.native)
        formLayout.addRow('Crop', self._enable_crop.native)
        formLayout.addRow('Search Window', self._search_windows.native)
        formLayout.addRow('Slice Thickness', self._slice_thickness.native)
        formLayout.addRow('Nr CPU', self._nr_cpu.native)
        self.layout().addLayout(formLayout)
        '''

        '''
        self.layout().addWidget(self._layer_combo.native)
        self.layout().addWidget(self._enable_crop.native)
        self.layout().addWidget(self._search_windows.native)
        self.layout().addWidget(self.slice_thickness.native)
        self.layout().addWidget(self._nr_cpu.native)
        '''
    def _build_params_widgets(self):
        """Builds the parameter widgets for the custom widget."""
        # Create widgets for parameters
        # change annotation to napari.layers.Image (e.g) to restrict to just Images
        #self._layer_combo = create_widget(annotation=napari.layers.Layer)


        
        self.training_param_group = QGroupBox()
        self.training_param_group.setTitle("Parameters")
        self.training_param_group.setMinimumWidth(100)

        self._shapes_combo = create_widget(annotation=napari.layers.Shapes)
        self._enable_crop = create_widget(annotation=bool)
        self._search_windows  = create_widget(annotation=int, widget_type='SpinBox', value=100, label='Search Window')
        self._slice_thickness  = create_widget(annotation=int, widget_type='FloatSpinBox', value=1.0, label='Slice Thickness')
        self._nr_cpu  = create_widget(annotation=int, widget_type='SpinBox', value=2, label='Nr CPU')

        formLayout = QFormLayout()
        # magicgui widgets hold the Qt widget at `widget.native`
        formLayout.addRow('Rectangle Layer', self._shapes_combo.native)
        formLayout.addRow('Crop', self._enable_crop.native)
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
        self.process_group.setLayout(QVBoxLayout())
        process_buttons = QWidget()
        process_buttons.setLayout(QHBoxLayout())
        self.process_button = QPushButton('Process', self)
        process_buttons.layout().addWidget(QLabel(''))
        process_buttons.layout().addWidget(self.process_button)
        self.process_group.layout().addWidget(process_buttons)

        self.layout().addWidget(self.process_group)



viewer = napari.Viewer()
#viewer.add_points()
#viewer.add_points()
viewer.add_shapes(name='Shapes', shape_type='rectangle')

my_widget = CustomWidget()
viewer.window.add_dock_widget(my_widget)

# when my_widget is a magicgui.Widget, it will detect that it has been added
# to a viewer, and automatically update the choices.  Otherwise, you need to
# trigger this yourself:
#my_widget._layer_combo.reset_choices()
#viewer.layers.events.inserted.connect(my_widget._layer_combo.reset_choices)
#viewer.layers.events.removed.connect(my_widget._layer_combo.reset_choices)

napari.run()