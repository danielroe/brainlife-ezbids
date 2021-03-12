#!/usr/bin/env python3
"""
Created on Wed Feb 17 08:32:55 2021

Deface anatomical image(s)

@author: dlevitas
"""

import os, sys
import nibabel as nib
import matplotlib.pyplot as plt
plt.style.use('dark_background')
from math import floor

os.environ[ 'MPLCONFIGDIR' ] = '/tmp/'

root = sys.argv[1]
anat_orig = sys.argv[2]
br_type = sys.argv[3]
sub = sys.argv[4]
ses = sys.argv[5]

anat_mask = anat_orig.split('.nii.gz')[0] + '_mask.nii.gz'
anat_defaced = anat_orig.split('.nii.gz')[0] + '_defaced.nii.gz'

# Skull strip and deface
print('Performing defacing on {}'.format(anat_orig), file = sys.stdout)
os.system('runROBEX.sh {} {}'.format(anat_orig, anat_mask))
os.system('quickshear {} {} {}'.format(anat_orig, anat_mask, anat_defaced))
print('Defaced anatomical file is {}'.format(anat_defaced), file = sys.stdout)

# Create PNG file of defaced image
for anat in [anat_orig, anat_defaced]:
    image = nib.load(anat)
    object_img_array = image.dataobj[:]

    slice_x = object_img_array[floor(object_img_array.shape[0]/2), :, :]
    slice_y = object_img_array[:, floor(object_img_array.shape[1]/2), :]
    slice_z = object_img_array[:, :, floor(object_img_array.shape[2]/2)]

    fig, axes = plt.subplots(1,3, figsize=(9,3))
    for i, slice in enumerate([slice_x, slice_y, slice_z]):
        axes[i].imshow(slice.T, cmap="gray", origin="lower", aspect='auto')
        axes[i].axis('off')
    plt.subplots_adjust(wspace=0, hspace=0)
    defaced_thumb = anat_defaced.split(root)[-1].split('.nii.gz')[0] + '.png'
    plt.savefig(defaced_thumb, bbox_inches='tight')

if ses == 'N/A':
    dic = {'id': 'sub-{}'.format(sub), 'defaced': anat_defaced[1:], 'defaced_thumb': defaced_thumb}
else:
    dic = {'id': 'sub-{}/ses-{}'.format(sub, ses), 'defaced': anat_defaced[1:], 'defaced_thumb': defaced_thumb}

print('defaced file is: {}'.format(anat_defaced))
print('defaced png file is: {}'.format(defaced_thumb))
    
file = open('{}/deface.out'.format(root), 'a')
file.write(repr(dic) + "\n")
file.close()
print("thumbnail {}".format(dic))




