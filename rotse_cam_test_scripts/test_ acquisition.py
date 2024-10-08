from atcore import *  # import the python wrapper for the driver
import math
import numpy as np
import time
from matplotlib import pyplot as plt


def _binning_string_to_tuple(bin):
    """
    Convert a binning string of the format 'axb' into a tuple (a, b) where a and b are integers.

    Parameters:
    bin (str): A string representing dimensions in the format 'axb', where a and b are integers.

    Returns:
    tuple: A tuple (a, b) where a and b are integers extracted from the input string.
    """
    # Split the string by 'x'
    a, b = bin.split("x")
    # Convert the split strings to integers and return as a tuple
    return int(a), int(b)


# initialise Andor SDK3
print("Intialising Andor's SDK3")
andor_driver = ATCore()

# connect to camera ...
zyla_camera = andor_driver.open(0)

# get the camera to say hi and introduce itself :)
print(
    f'Connected to camera {andor_driver.get_string(zyla_camera, "CameraModel")} with serial number: {andor_driver.get_string(zyla_camera, "SerialNumber")}'
)


def print_all():
    full_frame = (
        0,
        0,
        andor_driver.get_int(zyla_camera, "SensorWidth"),
        andor_driver.get_int(zyla_camera, "SensorHeight"),
    )

    window = (
        andor_driver.get_int(zyla_camera, "AOILeft") - 1,
        andor_driver.get_int(zyla_camera, "AOITop") - 1,
        andor_driver.get_int(zyla_camera, "AOIWidth"),
        andor_driver.get_int(zyla_camera, "AOIHeight"),
    )

    binning = _binning_string_to_tuple(
        andor_driver.get_enum_string(zyla_camera, "AOIBinning")
    )

    print(f"full frame: {full_frame}")
    print(f"window: {window}")
    print(f"binning {binning}")


print("CURRENT CAMERA SETTINGS:")
print_all()

window = (0, 0, 200, 200)
binning = 8
open_shutter = True
exposure_time = 0.001
cooling = 0
cool_down_time = 60

width = int(math.floor(window[2]) / binning)
height = int(math.floor(window[3]) / binning)

print(
    f"Set window to {window[2]}x{window[3]} (binned {width}x{height}) at {window[0]},{window[1]}."
)

andor_driver.set_enum_string(zyla_camera, "AOIBinning", f"{binning}x{binning}")
andor_driver.set_int(zyla_camera, "AOIWidth", width)
andor_driver.set_int(zyla_camera, "AOIHeight", height)
andor_driver.set_int(zyla_camera, "AOILeft", window[0] + 1)
andor_driver.set_int(zyla_camera, "AOITop", window[1] + 1)


print("SET CAMERA SETTINGS:")
print_all()


if open_shutter:
    andor_driver.set_enum_string(zyla_camera, "ShutterMode", "Open")
else:
    andor_driver.set_enum_string(zyla_camera, "ShutterMode", "Closed")

andor_driver.set_bool(zyla_camera, "SensorCooling", cooling)

if cooling == 1:
    print(f"Cooling sensor for {cool_down_time} seconds ...")
    time.sleep(cool_down_time)

exposure_temp = andor_driver.get_float(zyla_camera, "SensorTemperature")

print(
    f'Starting exposure with {"open" if open_shutter else "closed"} shutter for {exposure_time} seconds...'
)

# set encoding, exposure time etc ...
andor_driver.set_enum_string(zyla_camera, "PixelEncoding", "Mono16")
imageSizeBytes = andor_driver.get_int(zyla_camera, "ImageSizeBytes")

buf = np.empty((imageSizeBytes,), dtype="B")
andor_driver.queue_buffer(zyla_camera, buf.ctypes.data, imageSizeBytes)
buf2 = np.empty((imageSizeBytes,), dtype="B")
andor_driver.queue_buffer(zyla_camera, buf2.ctypes.data, imageSizeBytes)


still_aq = True
andor_driver.set_float(zyla_camera, "ExposureTime", exposure_time)
andor_driver.command(zyla_camera, "AcquisitionStart")

print(f"Exposing sensor ...")


while True:
    time.sleep(0.1)
    try:
        andor_driver.wait_buffer(zyla_camera, timeout=0)
        andor_driver.command(zyla_camera, "AcquisitionStop")
        break
    except:
        pass

print("Exposure complete, reading out...")

aoistride = andor_driver.get_int(zyla_camera, "AOIStride")

np_arr = buf[0 : height * aoistride]
np_d = np_arr.view(dtype=np.uint16)
np_d = np_d.reshape(height, round(np_d.size / height))
formatted_img = np_d[0:height, 0:width]

plt.imsave(
    f"zyla_test_cooling:{bool(cooling)}_temp:{exposure_temp}_exposure:{exposure_time}.png",
    np.log(formatted_img),
)

print("Disabling cooling and disconnecting camera ...")
andor_driver.set_enum_string(zyla_camera, "ShutterMode", "Closed")
andor_driver.set_bool(zyla_camera, "SensorCooling", False)
andor_driver.close(zyla_camera)
