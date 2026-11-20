"""Camera capture on the CardputerZero IMX219 sensor via picamera2."""

import os
import time

import numpy as np

PREVIEW_SIZE = (320, 170)
CAPTURE_SIZE = (1280, 720)

# Exposure ladder, tried in order when the auto-exposed frame is too dark.
#
# Measured on the real IMX219 of a CardputerZero in a dim room: the default
# (auto) exposure yields a nearly black frame with a mean luminance of ~6/255,
# which the quality gate rejects with "画面偏暗" and OCR never runs. The very
# same scene is perfectly readable at 20 s / 32x gain (mean ~147). So instead
# of telling the user to add light, the capture path retries with a longer
# exposure and a higher analogue gain.
#
# Each entry is (exposure_time_us, analogue_gain).
EXPOSURE_LADDER = (
    (2_000_000, 4.0),
    (6_000_000, 8.0),
    (12_000_000, 16.0),
    (20_000_000, 32.0),
)

# Total wall-clock budget for the whole ladder. A dim scene should not make
# the user wait forever, and a covered lens must be rejected quickly.
LADDER_BUDGET_S = 10.0

# Below this mean the lens is almost certainly covered (a covered lens reads
# ~2 on this sensor, an unlit room still reads ~10): climbing the ladder
# would only burn the budget. Anything dimmer-but-alive must climb.
COVERED_MEAN = 5.0

# A frame is considered usable when it is bright enough and has enough
# contrast to carry text. These match the quality gate thresholds.
TARGET_MEAN = 45.0
TARGET_STD = 12.0


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

    def _switch(self, config):
        """Switch the running camera to another configuration.

        picamera2 0.3.37 (the version installed on the device) exposes
        `switch_mode`, not `switch_cameras`. Prefer the API that actually
        exists and fall back to the other spelling so the app keeps working
        if the package is upgraded.
        """
        for name in ("switch_mode", "switch_cameras"):
            fn = getattr(self._cam, name, None)
            if fn is None:
                continue
            try:
                fn(config)
                return True
            except Exception:
                continue
        return False

    def _set_controls(self, exposure_us, gain):
        """Apply exposure/gain to the running camera.

        Controls have to be applied *after* the camera is running and
        configured, otherwise picamera2 silently ignores them.
        """
        try:
            self._cam.set_controls({
                "ExposureTime": int(exposure_us),
                "AnalogueGain": float(gain),
            })
        except Exception:
            pass

    @staticmethod
    def _score(frame):
        """Return (mean, std) luminance of an RGB frame."""
        arr = np.asarray(frame)
        gray = (
            arr[:, :, 0].astype(np.float32) * 0.299
            + arr[:, :, 1].astype(np.float32) * 0.587
            + arr[:, :, 2].astype(np.float32) * 0.114
        )
        return float(gray.mean()), float(gray.std())

    def _shoot(self, exposure_us=None, gain=None):
        """Take one still frame with the given exposure, or auto if unset."""
        if exposure_us is not None:
            self._set_controls(exposure_us, gain)
            # The sensor integrates over the whole exposure time, so give it
            # time to finish plus a little margin before grabbing the frame.
            time.sleep(exposure_us / 1_000_000.0 * 1.15 + 0.25)
        return self._cam.capture_array("main")

    def capture(self):
        """Capture a still frame and return it as an RGB numpy array.

        The auto-exposed frame is tried first, so a well-lit scene keeps the
        fast path. If it comes out too dark or too flat, the exposure ladder
        is walked and the best frame is kept.
        """
        if self._cam is None:
            raise CameraError("camera not started")
        try:
            cfg = self._cam.create_still_configuration(
                main={"size": CAPTURE_SIZE, "format": "RGB888"},
            )
            self._switch(cfg)
            self._cam.set_controls({"ExposureTime": 0, "AnalogueGain": 1.0})
            frame = self._shoot()
            best = frame
            best_mean, best_std = self._score(frame)

            # A near-zero frame means the lens is covered. A merely dark
            # frame (unlit room, mean ~10) is recoverable and must climb.
            if best_mean < COVERED_MEAN:
                return np.asarray(best)[:, :, :3]

            if best_mean < TARGET_MEAN or best_std < TARGET_STD:
                spent = 0.0
                for exposure_us, gain in EXPOSURE_LADDER:
                    wait = exposure_us / 1_000_000.0 * 1.15 + 0.25
                    if spent + wait > LADDER_BUDGET_S:
                        break
                    spent += wait
                    cand = self._shoot(exposure_us, gain)
                    if cand is None:
                        continue
                    mean, std = self._score(cand)
                    # Keep the frame that is bright enough to read, and
                    # otherwise the one with the most signal.
                    if mean >= TARGET_MEAN and std >= TARGET_STD:
                        best = cand
                        break
                    if mean > best_mean:
                        best, best_mean, best_std = cand, mean, std

            # Go back to the cheap preview pipeline for the next frame.
            pcfg = self._cam.create_preview_configuration(
                main={"size": PREVIEW_SIZE, "format": "RGB888"},
                buffer_count=2,
            )
            self._switch(pcfg)
        except Exception as exc:
            raise CameraError("capture failed: %s" % exc)
        if best is None:
            raise CameraError("capture returned no frame")
        return np.asarray(best)[:, :, :3]

    def save_jpeg(self, array, path):
        from PIL import Image
        Image.fromarray(array).save(path, "JPEG", quality=92)
        return path
