
from pathlib import Path
import pkgutil
import importlib
import inspect
import os
import json
import csv
import yaml
import argparse

import cv2
import numpy as np
from types import SimpleNamespace

import shutil
import math
import copy
import zipfile

from utils.load_rostypes import *
from utils.ros_msg_handlers import *

# Example usage:
# python3 post_process_vicon.py --trial_name irl3_los_walking --vicon_trial_name irl3_los_walking --map_vicon_to_uwb --no_orbslam True -c cam_target_daslab


parser = argparse.ArgumentParser(description="Stream collector")
parser.add_argument("--trial_name" , "-t", type=str)
args = parser.parse_args()

outpath = f"./export/{args.trial_name}_nuc{os.environ['USER_ID']}_raw"

out_infra1 = f'{outpath}/infra1_raw'
out_infra2 = f'{outpath}/infra2_raw'

os.makedirs(outpath, exist_ok=True)
os.makedirs(out_infra1, exist_ok=True)
os.makedirs(out_infra2, exist_ok=True)

bagpath = Path(f'./ros2/{args.trial_name}')


# Need to maintain another array that we can buffer data to before dumping one sensor per csv
topic_to_processing = {
                '/uwb_ranges': (proc_range, []),
                  '/camera/camera/imu': (proc_imu, []),
                  '/camera/camera/infra1/image_rect_raw': (proc_infra1_frame, []),
                  '/camera/camera/infra2/image_rect_raw': (proc_infra2_frame, []),
}

all_data = []
dataset_topics = [ k for k,v in topic_to_processing.items()]
gt_standalone = []


rostypes = load_rostypes()
uwb_message_count = 0
processed_uwb_message = 0
# Create reader instance and open for reading.
with AnyReader([bagpath], default_typestore=rostypes) as reader:
    connections = [x for x in reader.connections if x.topic in dataset_topics]
    for connection, timestamp, rawdata in reader.messages(connections=connections):

        try:
            msg = reader.deserialize(rawdata, connection.msgtype)
            proc, arr_ref = topic_to_processing[connection.topic]
            proc(msg, arr_ref)
        except Exception:
            print( "Exception! skipped message")
            continue  # optionally log here


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if hasattr(obj, '__dict__'):
            return vars(obj)
        return super().default(obj)

# Processors functions have now buffered their individual topics into arr_ref
# This is useful for writing the same datastream to multiple files.
# Then, lastly, we can output .json files with the raw measurements

json.dump(topic_to_processing['/uwb_ranges'][1], open(outpath+"/uwb_raw.json", 'w'), cls=NumpyEncoder, indent=1)
json.dump(topic_to_processing['/camera/camera/imu'][1], open(outpath+"/imu_raw.json", 'w'), cls=NumpyEncoder, indent=1)

### Write Infra1 frames to output directory, and provide references in all_data
for j in topic_to_processing['/camera/camera/infra1/image_rect_raw'][1]:
    cv2.imwrite(out_infra1+"/"+j["name"], j["raw"])
    j_no_image = { k:v for k,v in j.items() if not (k == "raw") }
    all_data.append(j_no_image)

### Write Infra2 frames to output directory, and provide references in all_data
for j in topic_to_processing['/camera/camera/infra2/image_rect_raw'][1]:
    cv2.imwrite(out_infra2+"/"+j["name"], j["raw"])
    j_no_image = { k:v for k,v in j.items() if not (k == "raw") }
    all_data.append(j_no_image)

# Export ROS start and end times
time = {
    'start_ns': reader.start_time,
    'end_ns': reader.end_time,
}
json.dump(time, open(outpath+"/meta.json", 'w'), cls=NumpyEncoder, indent=1)

def make_archive(source, destination):
        base = os.path.basename(destination)
        name = base.split('.')[0]
        format = base.split('.')[1]
        archive_from = os.path.dirname(source)
        archive_to = os.path.basename(source.strip(os.sep))
        shutil.make_archive(name, format, archive_from, archive_to)
        shutil.move('%s.%s'%(name,format), destination)

# make_archive('/path/to/folder', '/path/to/folder.zip')

make_archive(out_infra1, out_infra1+".zip")
make_archive(out_infra2, out_infra2+".zip")

make_archive(outpath, outpath+".zip")
if os.path.exists(outpath+".zip"):
    shutil.rmtree(outpath)