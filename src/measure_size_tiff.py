import os
import csv
import tifffile

folder = "C:\\Users\\u0094799\\Documents\\PROJECTS\\Ghent\\Anneke\\2025_10_EM_registration\\2025_10_17_EM397_3945_YB7_run2"
output_csv = os.path.join(folder, "image_dimensions.csv")

rows = []

for fname in os.listdir(folder):
    if fname.lower().endswith((".tif", ".tiff")):
        path = os.path.join(folder, fname)
        try:
            with tifffile.TiffFile(path) as tif:
                arr = tif.asarray()
                rows.append([fname, arr.shape, str(arr.dtype)])
        except Exception as e:
            rows.append([fname, "Error", str(e)])

# Write to CSV
with open(output_csv, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Filename", "Shape", "Dtype"])
    writer.writerows(rows)

print(f"✅ Results saved to {output_csv}")