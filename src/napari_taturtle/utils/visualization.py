import os
import numpy as np
import matplotlib.pyplot as plt
import SimpleITK as sitk
import logging

logger = logging.getLogger(__name__)

def plot_displacements(transforms_dir, output_plot_path):
    """
    Plot the mean absolute displacement from Elastix transform files.
    
    Parameters
    ----------
    transforms_dir : str
        Path to the directory containing the .txt transform files.
    output_plot_path : str
        Path where the generated plot (.png) should be saved.
    """
    logger.info(f"Plotting displacements from {transforms_dir}...")
    
    if not os.path.isdir(transforms_dir):
        logger.error(f"Error: {transforms_dir} is not a directory.")
        return

    # Filter and sort transform files (e.g., transform_00000.txt)
    transform_files = sorted([f for f in os.listdir(transforms_dir) if f.endswith('.txt')])
    if not transform_files:
        logger.warning("No transform files found in the directory.")
        return

    slice_indices = []
    mean_dx = []
    mean_dy = []

    for idx, filename in enumerate(transform_files):
        filepath = os.path.join(transforms_dir, filename)
        
        try:
            # SimpleITK ReadParameterFile is robust for these .txt files
            p_map = sitk.ReadParameterFile(filepath)
            
            if 'TransformParameters' in p_map:
                params = [float(x) for x in p_map['TransformParameters']]
                num_params = len(params)
                
                # BSpline transforms typically have [x_params, y_params]
                # Translation/Affine follow similar logic in their parameter lists
                dx = params[:num_params//2]
                dy = params[num_params//2:]
                
                slice_indices.append(idx)
                mean_dx.append(np.mean(np.abs(dx)))
                mean_dy.append(np.mean(np.abs(dy)))
        except Exception as e:
            logger.debug(f"Could not read {filename} displacement: {e}")

    if slice_indices:
        plt.figure(figsize=(10, 6))
        plt.plot(slice_indices, mean_dx, label='Mean |dx| (pixels)', marker='o', markersize=2)
        plt.plot(slice_indices, mean_dy, label='Mean |dy| (pixels)', marker='x', markersize=2, alpha=0.7)
        plt.xlabel('Slice Index')
        plt.ylabel('Mean Absolute Displacement')
        plt.title('AMST Refinement Displacements')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.savefig(output_plot_path)
        plt.close() # Clean up to avoid memory issues in a long-running plugin
        logger.info(f"Displacement plot saved to: {output_plot_path}")
    else:
        logger.warning("No valid displacement data found to plot.")
