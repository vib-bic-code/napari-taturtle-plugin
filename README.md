# napari-taturtle-plugin

A napari plugin for FIB-SEM image alignment and preprocessing, powered by the `taturtle` package.

<img width="1918" height="1029" alt="image" src="https://github.com/user-attachments/assets/64501395-6cf8-4893-9ce7-08a8488fcc7b" />


## Features
- **Autocrop**: Automatically remove black borders from aligned stacks.
- **Registration**: High-precision image registration using template matching.
- **Thickness Correction**: Resample stacks based on measured slice thickness.
- **Qt Interface**: A responsive UI with background processing and progress feedback.

## Installation

### 0. Install Conda
Install conda like with [miniforge](https://github.com/conda-forge/miniforge) or others

### 1. Clone the project

```bash
git clone https://github.com/vib-bic-code/napari-taturtle-plugin.git
cd napari-taturtle-plugin
```

### 2. Create the Conda Environment
Using the provided `environment.yml` file:

```bash
conda env create -f environment.yml
conda activate napari-taturtle-env
```

### 3. Install the Plugin in Editable Mode
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

## Extra:

You can now perform extra filtering using squirrel, those could be addded to the plugin:

Her is how it's working with squirrel:

1. Create a parameter file that defines the filter sequence, here a quite detailed example that I used on some cryoFIB-SEM data:
 ```bash
echo '[
    ["vsnr", {"is_gpu": false, "maxit": 20, "keep_zeros": true,
"filters": [{"name": "Gabor", "sigma": [2, 35], "theta": 0,
"noise_level": 0.5}]}],
    ["vsnr", {"is_gpu": false, "maxit": 20, "keep_zeros": true,
"filters": [{"name": "Gabor", "sigma": [2, 35], "theta": 90,
"noise_level": 0.5}]}],
    ["median", {"radius": [5, 200], "filter_mode": "subtract",
"cast_dtype": "uint16", "sample_footprint": 200, "elliptical_footprint":
true, "keep_zeros": true}],
    ["median", {"radius": [300, 5], "filter_mode": "subtract",
"cast_dtype": "uint16", "sample_footprint": 200, "elliptical_footprint":
true, "keep_zeros": true}],
    ["clahe", {"tile_grid_in_pixels": true, "tile_grid_size": [127, 127], "clip_limit": 40, "keep_zeros": true}] ]' >> filters.json
 ```
 
2. Run for a test slice:
```bash 
sq-image-filter_2d_workflow image.tif output.tif -ff filters.json
```
 
3. Run for the full dataset:
```bash 
sq-stack-filter_2d_workflow dataset_dir/ output_dir/ -ff filters.json --batch_size 16 --n_workers 16
``` 
 
Also check out the `-h` output of the `sq-stack-filter_2d_workflow` function.
 
 
If you only want to de-stripe the horizontal stripes, you could simply use:
```bash 
echo '[
    ["vsnr", {"is_gpu": false, "maxit": 20, "keep_zeros": true,
"filters": [{"name": "Gabor", "sigma": [2, 35], "theta": 0,
"noise_level": 0.5}]}]
]' >> filters.json
sq-stack-filter_2d_workflow dataset_dir/ output_dir/ -ff filters.json
--batch_size 16 --n_workers 16
```
It could be that you can improve results with adjusting, `theta` (the
angle of the stripes, 0 means exactly vertical), `sigma` or
`noise_level`. More theory on the VSNR algorithm here: https://github.com/CEA-MetroCarac/pyvsnr
 
Note: the "keep_zeros" parameters is available for any filter and makes
sure that pixels that are zero in the input image will be zero in the
output as well (it's usually good to keep the background).
