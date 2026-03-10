# napari-taturtle-plugin

A napari plugin for FIB-SEM image alignment and preprocessing, powered by the `taturtle` package.

## Features
- **Autocrop**: Automatically remove black borders from aligned stacks.
- **Registration**: High-precision image registration using template matching.
- **Thickness Correction**: Resample stacks based on measured slice thickness.
- **Qt Interface**: A responsive UI with background processing and progress feedback.

## Installation

### 1. Create the Conda Environment
Using the provided `environment.yml` file:

```bash
conda env create -f environment.yml
conda activate napari-taturtle-env
```

### 2. Install the Plugin in Editable Mode
From the root of this project directory:

```bash
pip install -e .
```

*Note: This will also ensure `taturtle` is linked correctly if you followed the environment setup above.*

## Usage

1. Launch napari:
   ```bash
   napari
   ```
2. Open the plugin via the menu: `Plugins > Taturtle: Registration`.
3. Select your input folder containing TIF images.
4. Draw a rectangle ROI on a `Shapes` layer to define the registration area.
5. (Optional) Select an output folder. If left blank, results will be saved in the parent directory of your input images.
6. Click **Process**.

## License
Distributed under the terms of the BSD-3 license.
