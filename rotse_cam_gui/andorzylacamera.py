import asyncio
import logging
import math
import time
import datetime
from typing import Tuple, Any, Optional, Dict, List
import numpy as np

from pyobs.interfaces import ICamera, IWindow, IBinning, ITemperatures, IAbortable
from pyobs.modules.camera.basecamera import BaseCamera
from pyobs.images import Image
from pyobs.utils.enums import ExposureStatus
from pyobs.utils.parallel import event_wait

# import the Andor SDK3 python wrapper provided with the camera ...
from pyobs.modules.camera.atcore import ATCore

log = logging.getLogger(__name__)


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


class AndorZylaCamera(
    BaseCamera, ICamera, IWindow, IBinning, ITemperatures, IAbortable
):
    """A pyobs module for Andor Zyla USB cameras."""

    __module__ = "pyobs_andors"

    def __init__(self, setpoint: float = 0.00, **kwargs: Any):
        """Initializes a new  AndorZylaCamera."""
        BaseCamera.__init__(self, **kwargs)

        # set the andor skd3 driver
        self._driver = ATCore()

        # activate lock
        self._lock_active = asyncio.Lock()

        # window and binning values init ...
        self._full_frame = (0, 0, 0, 0)
        self._window = (0, 0, 0, 0)
        self._binning = (1, 1)
        self._driver
        self._binnings_available = []

    async def open(self) -> None:
        """Open module.

        Raises:
            ValueError: If cannot connect to camera.
        """
        #await BaseCamera.open(self)

        # open driver add pyobs utils exceptions ...
        log.info("Connecting to Andor camera ...")
        try:
            # connect to the Andor camera with device index 0 ...
            self._camera = self._driver.open(0)

            # Let user know we have a successful connection
            serial = self._driver.get_string(self._camera, "SerialNumber")
            model = self._driver.get_string(self._camera, "CameraModel")
            log.info("Connected to camera %s with serial number: %s", model, serial)

        except ValueError as e:
            raise ValueError("Could not establish link: %s" % str(e))

        # ask the camera for its available binning options and convert to a list of tuples ...
        self._binnings_available = [
            (int(binning.split("x")[0]), int(binning.split("x")[1]))
            for binning in self._driver.get_enum_string_options(
                self._camera, "AOIBinning"
            )
        ]

        # get the cameras initial full frame size ...
        self._full_frame = (
            0,
            0,
            self._driver.get_int(self._camera, "SensorWidth"),
            self._driver.get_int(self._camera, "SensorHeight"),
        )

        # get the cameras current area of interest window frame, noting that the SDK3 returns the coords shifted by +1 ...
        self._window = (
            self._driver.get_int(self._camera, "AOILeft") - 1,
            self._driver.get_int(self._camera, "AOITop") - 1,
            self._driver.get_int(self._camera, "AOIWidth"),
            self._driver.get_int(self._camera, "AOIHeight"),
        )

        # get the current binning settings of the camera ...
        self._binning = _binning_string_to_tuple(
            self._driver.get_enum_string(self._camera, "AOIBinning")
        )

        # Zyla cameras only a support single set point of 0°C. Cooler control is restricted to enabling or disabling the cooling ...
        # start cooling on camera init as not enough functionality to include ICooling interface ...
        log.info("Enabling cooling and setting setpoint 0°C.")
        self._driver.set_bool(self._camera, "SensorCooling", int(True))

    async def close(self) -> None:
        """Close the module."""
        await BaseCamera.close(self)

        # turn off cooling and disconnect camera ...
        self._driver.set_bool(self._camera, "SensorCooling", int(False))
        self._driver.close(self._camera)

    async def get_full_frame(self, **kwargs: Any) -> Tuple[int, int, int, int]:
        """Returns full size of CMOS.

        Returns:
            Tuple with left, top, width, and height set.
        """
        return self._full_frame

    async def get_window(self, **kwargs: Any) -> Tuple[int, int, int, int]:
        """Returns the camera window.

        Returns:
            Tuple with left, top, width, and height set.
        """
        return self._window

    async def set_window(
        self, left: int, top: int, width: int, height: int, **kwargs: Any
    ) -> None:
        """Set the camera window.

        Args:
            left: X offset of window.
            top: Y offset of window.
            width: Width of window.
            height: Height of window.

        Raises:
            ValueError: If binning could not be set.
        """
        self._window = (left, top, width, height)
        log.info("Setting window to %dx%d at %d,%d...", width, height, left, top)

    async def get_binning(self, **kwargs: Any) -> Tuple[int, int]:
        """Returns the camera binning.

        Returns:
            Tuple with x and y.
        """
        return self._binning

    async def set_binning(self, x: int, y: int, **kwargs: Any) -> None:
        """Set the camera binning.

        Args:
            x: X binning.
            y: Y binning.

        Raises:
            ValueError: If binning could not be set.
        """
        self._binning = (x, y)
        log.info("Setting binning to %dx%d...", x, y)

    async def list_binnings(self, **kwargs: Any) -> List[Tuple[int, int]]:
        """List available binnings.

        Returns:
            List of available binnings as (x, y) tuples.
        """
        return self._binnings_available

    async def get_temperatures(self, **kwargs: Any) -> Dict[str, float]:
        """Returns all temperatures measured by this module.

        Returns:
            Dict containing temperatures.
        """
        return {
            "CMOS": self._driver.get_float(self._camera, "SensorTemperature"),
        }

    async def _expose(
        self, exposure_time: float, open_shutter: bool, abort_event: asyncio.Event
    ) -> Image:
        """Actually do the exposure, should be implemented by derived classes.

        Args:
            exposure_time: The requested exposure time in seconds.
            open_shutter: Whether or not to open the shutter.
            abort_event: Event that gets triggered when exposure should be aborted.

        Returns:
            The actual image.

        Raises:
            GrabImageError: If exposure was not successful.
        """

        # set the binning on the camera ...
        log.info("Set binning to %dx%d.", self._binning[0], self._binning[1])
        await self._driver.set_enum_string(
            self._camera, "AOIBinning", f"{self._binning[0]}x{self._binning[1]}"
        )

        # determine window, noting from the SDK3 documentation: "The AOIWidth and AOIHeight features are set and retrieved in
        # units of super-pixels Therefore, when binning is in use, the AOIWidth value will always indicate the number of data
        # pixels that each row of the image data contains and not the number of pixels read off the sensor. The AOILeft and
        # AOITop coordinates are specified in units of sensor pixels."
        width = int(math.floor(self._window[2]) / self._binning[0])
        height = int(math.floor(self._window[3]) / self._binning[1])

        log.info(
            "Set window to %dx%d (binned %dx%d) at %d,%d.",
            self._window[2],
            self._window[3],
            width,
            height,
            self._window[0],
            self._window[1],
        )

        # set the camera encoding ...
        self._driver.set_enum_string(self._camera, "PixelEncoding", "Mono16")

        # set the window on the camera remembering the SDK3 has the origin at (+1,+1) ...
        await self._driver.set_int(self._camera, "AOIWidth", width)
        await self._driver.set_int(self._camera, "AOIHeight", height)
        await self._driver.set_int(self._camera, "AOILeft", self._window[0] + 1)
        await self._driver.set_int(self._camera, "AOITop", self._window[1] + 1)

        # set the cameras shutter state ...
        if open_shutter:
            await self._driver.set_enum_string(self._camera, "ShutterMode", "Open")
        else:
            await self._driver.set_enum_string(self._camera, "ShutterMode", "Closed")

        # set the cameras exposure time in seconds ...
        await self._driver.set_float(self._camera, "ExposureTime", exposure_time)

        # get the expected size of the required memory buffer in bytes from the camera ...
        imageSizeBytes = self._driver.get_int(self._camera, "ImageSizeBytes")

        # setup a primary and secondary buffer as per SDK3 documentation ...s
        primary_buffer = np.empty((imageSizeBytes,), dtype="B")
        self._driver.queue_buffer(
            self._camera, primary_buffer.ctypes.data, imageSizeBytes
        )

        secondary_buffer = np.empty((imageSizeBytes,), dtype="B")
        self._driver.queue_buffer(
            self._camera, secondary_buffer.ctypes.data, imageSizeBytes
        )

        # get the current date and time of exposure ...
        date_obs = datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")

        log.info(
            "Starting exposure with %s shutter for %.2f seconds...",
            "open" if open_shutter else "closed",
            exposure_time,
        )

        # start the exposure ...
        self._driver.command(self._camera, "AcquisitionStart")

        # wait for exposure to finish or be aborted before reading out ...
        await self._wait_exposure(abort_event, exposure_time, open_shutter)

        # begin the readout ...
        log.info("Exposure finished, reading out...")
        await self._change_exposure_status(ExposureStatus.READOUT)
        width = int(math.floor(self._window[2] / self._binning[0]))
        height = int(math.floor(self._window[3] / self._binning[1]))

        # we need the stride data ... from SDK3 documentation: "AOIStride - At the end of each row there may be additional padding bytes.
        # This padding area does not contain any valid pixel data and should be skipped over when processing or displaying an image."
        aoistride = self._driver.get_int(self._camera, "AOIStride")

        # read in the data from the primary buffer and remove stride/padding pixels  ...
        primary_buffer = primary_buffer[0 : height * aoistride]
        np_d = primary_buffer.view(dtype=np.uint16)
        np_d = np_d.reshape(height, round(np_d.size / height))
        img = np_d[0:height, 0:width]

        # create FITS image and set header ...
        image = Image(img)
        image.header["DATE-OBS"] = (date_obs, "Date and time of start of exposure")
        image.header["EXPTIME"] = (exposure_time, "Exposure time [s]")
        image.header["DET-TEMP"] = (
            self._driver.get_float(self._camera, "SensorTemperature"),
            "CMOS temperature [C]",
        )

        # camera has fixed setpoint ...
        image.header["DET-TSET"] = (0, "Cooler setpoint [C]")

        # note instrument and detector ...
        image.header["INSTRUMENT"] = (
            self._driver.get_string(self._camera, "CameraModel"),
            "Name of instrument",
        )

        # note binning ...
        image.header["XBINNING"] = image.header["DET-BIN1"] = (
            self._binning[0],
            "Binning factor used on X axis",
        )
        image.header["YBINNING"] = image.header["DET-BIN2"] = (
            self._binning[1],
            "Binning factor used on Y axis",
        )

        # note window ...
        image.header["XORGSUBF"] = (self._window[0], "Subframe origin on X axis")
        image.header["YORGSUBF"] = (self._window[1], "Subframe origin on Y axis")

        # note statistics ...
        image.header["DATAMIN"] = (float(np.min(img)), "Minimum data value")
        image.header["DATAMAX"] = (float(np.max(img)), "Maximum data value")
        image.header["DATAMEAN"] = (float(np.mean(img)), "Mean data value")

        # biassec/trimsec
        self.set_biassec_trimsec(image.header, *self._full_frame)

        # return FITS image
        log.info("Readout finished.")
        return image

    async def _wait_exposure(
        self, abort_event: asyncio.Event, exposure_time: float, open_shutter: bool
    ) -> None:
        """Wait for exposure to finish.

        Params:
            abort_event: Event that aborts the exposure.
            exposure_time: Exp time in sec.
        """

        while True:
            # has the exposure been aborted?
            if abort_event.is_set():
                await self._change_exposure_status(ExposureStatus.IDLE)
                raise InterruptedError("Aborted exposure.")

            # is exposure finished?
            try:
                self._driver.wait_buffer(self._camera, timeout=0)
                self._driver.command(self._camera, "AcquisitionStop")
                break
            except:
                await asyncio.sleep(0.01)

    async def _abort_exposure(self) -> None:
        """Abort the running exposure. Should be implemented by derived class.

        Raises:
            ValueError: If an error occured.
        """
        self._driver.command(self._camera, "AcquisitionStop")


__all__ = ["AndorZylaCamera"]
