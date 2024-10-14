TODO:







___________________ Basic Troubleshooting: ___________________

Problem: "AttributeError: 'ATCore' object has no attribute 'lib'"
Fix: This issue is normally due to an older version of setuptools and cffi python modules in the venv, simply upgrade both ... pip install --upgrade setuptools cffi

Problem: Camera is connected yet extremely slow, may throw errors regarding divide by zero and Nan when trying to transfer data into a .fits file.
Fix: Ensure the camera is connected to a USB3 port and not a USB2. 
