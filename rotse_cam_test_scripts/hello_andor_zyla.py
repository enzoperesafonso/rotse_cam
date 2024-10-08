from atcore import *  # import the python wrapper for the driver

# initialise Andor SDK3
print("Intialising Andor's SDK3")
andor_driver = ATCore() 

# connect to camera ...
zyla_camera = andor_driver.open(0)

# is camera present ...
print(f'Is camera present: {bool(andor_driver.get_bool(zyla_camera, "CameraPresent"))}')

# get the camera to say hi and introduce itself :)
print(f'Connected to camera {andor_driver.get_string(zyla_camera, "CameraModel")} with serial number: {andor_driver.get_string(zyla_camera, "SerialNumber")}')

# how big is the sensor ...
print(f'Camera says its sensor is {andor_driver.get_int(zyla_camera,"SensorWidth")} x {andor_driver.get_int(zyla_camera,"SensorHeight")} pixels')

# try a basic read and set ...
print(f'The avaialble binning options are: {andor_driver.get_enum_string_options(zyla_camera, "AOIBinning")}')
print(f'The camera is currently set to {andor_driver.get_enum_string(zyla_camera, "AOIBinning")} binning.')
andor_driver.set_enum_string(zyla_camera, "AOIBinning", "2x2")
print(f'Just set the camera to {andor_driver.get_enum_string(zyla_camera, "AOIBinning")} binning.')

# Whats the cooling setpoint so we don't get condensation when we cool ... 
print(f'The cooling setpoint temperature is {andor_driver.get_enum_string(zyla_camera, "TemperatureControl")} degress allowed options are {andor_driver.get_enum_string_options(zyla_camera, "TemperatureControl")}')

# lets see what the cameras current cooling status is 
print(f'Current cooling status is {andor_driver.get_enum_string(zyla_camera, "TemperatureStatus")}.')
print('turning on cooler...')
andor_driver.set_bool(zyla_camera, "SensorCooling", 1)

#print(f'Max Cooling Power Used: {andor_driver.get_float(zyla_camera, "CoolerPower")} %')
print(f'Current cooling status is {andor_driver.get_enum_string(zyla_camera, "TemperatureStatus")}.')

# whats the current temp of the sensor ... 
print(f'Current temperature of sensor is {andor_driver.get_float(zyla_camera, "SensorTemperature")} degrees.')

# whats the fan doing ...
print(f'Camera fan is {andor_driver.get_enum_string(zyla_camera, "FanSpeed")}.')

# is camera acquiring ...
print(f'Camera acquiring: {bool(andor_driver.get_bool(zyla_camera, "CameraAcquiring"))}.')

print('turning off cooler...')
andor_driver.set_bool(zyla_camera, "SensorCooling", 0)

# close the camera when we are finished with it ...
andor_driver.close(zyla_camera)

print('Closed driver and disconnected camera...')

