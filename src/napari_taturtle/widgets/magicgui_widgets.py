from pathlib import Path

import napari
from magicgui import magic_factory
from magicgui.widgets import create_widget, Container, Widget


def layer_choice(annotation, **kwargs) -> Widget:
    widget = create_widget(annotation=annotation, **kwargs)
    widget.reset_choices()
    viewer = napari.current_viewer()
    viewer.layers.events.inserted.connect(widget.reset_choices)
    viewer.layers.events.removed.connect(widget.reset_choices)
    viewer.layers.events.changed.connect(widget.reset_choices)
    return widget

@magic_factory(auto_call=True, do_crop={'label': ' ', 'widget_type': 'Checkbox', 'visible': True})
def enable_crop(do_crop: bool = False) -> bool:
    return do_crop

def two_layers_choice():
    """
    Returns a container with two drop-down widgets to select images and masks.
    :return:
    """
    img = layer_choice(annotation=napari.layers.Image, name="Image")
    lbl = layer_choice(annotation=napari.layers.Shapes, name="Region")

    return Container(widgets=[img, lbl])
