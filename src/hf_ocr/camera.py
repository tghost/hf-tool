"""Camera capture on the CardputerZero IMX219 sensor via picamera2."""

import os
import time

import numpy as np

PREVIEW_SIZE = (320, 170)
CAPTURE_SIZE = (1280, 720)


class CameraError(RuntimeError):
    pass


class Camera:
    """Thin wrapper around picamera2.

    The device ships python3-picamera2, so we do not bundle any imaging
    dependency of our own.
    """

    def __init__(self):
        self._cam = None

    def start(self):
        try:
            from picamera2 import Picamera2
        except ImportError as exc:  # pragma: no cover - device only
            raise CameraError("picamera2 unavailable: %s" % exc)
        try:
            self._cam = Picamera2()
            config = self._cam.create_preview_configuration(
                main={"size": PREVIEW_SIZE, "format": "RGB888"},
                buffer_count=2,
            )
            self._cam.configure(config)
            self._cam.start()
            # The sensor needs a moment to settle exposure/white balance.
            time.sleep(0.8)
        except Exception as exc:
            raise CameraError("camera start failed: %s" % exc)
        return self

    def stop(self):
        if self._cam is not None:
            try:
                self._cam.stop()
            except Exception:
                pass
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None

    def preview_frame(self):
        """Return the current preview frame as an RGB numpy array."""
        if self._cam is None:
            return None
        try:
            frame = self._cam.capture_array("main")
        except Exception:
            return None
        if frame is None:
            return None
        return np.asarray(frame)[:, :, :3]

    def capture(self):
        """Capture a still frame and return it as an RGB numpy array."""
        if self._cam is None:
            raise CameraError("camera not started")
        try:
            cfg = self._cam.create_still_configuration(
                main={"size": CAPTURE_SIZE, "format": "RGB888"},
            )
            self._cam.switch_cameras(cfg)
            frame = self._cam.capture_array("main")
            # Go back to the cheap preview pipeline for the next frame.
            pcfg = self._cam.create_preview_configuration(
                main={"size": PREVIEW_SIZE, "format": "RGB888"},
                buffer_count=2,
            )
            self._cam.switch_cameras(pcfg)
        except Exception as exc:
            raise CameraError("capture failed: %s" % exc)
        if frame is None:
            raise CameraError("capture returned no frame")
        return np.asarray(frame)[:, :, :3]

    def save_jpeg(self, array, path):
        from PIL import Image
        Image.fromarray(array).save(path, "JPEG", quality=92)
        return path
