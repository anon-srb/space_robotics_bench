import sys
import threading
import time
from collections.abc import Callable
from typing import List

import numpy as np
import pyspacemouse
from scipy.spatial.transform import Rotation

from space_robotics_bench.core.teleop_devices import DeviceBase


class Se3SpaceMouse(DeviceBase):
    def __init__(
        self,
        pos_sensitivity: float = 0.4,
        rot_sensitivity: float = 0.8,
        rate: float = 1000.0,
    ):
        # Store inputs
        self.pos_sensitivity = pos_sensitivity
        self.rot_sensitivity = rot_sensitivity
        self.sleep_rate = 1.0 / rate

        # Command buffers
        self._close_gripper = False
        self._delta_pos = np.zeros(3)  # (x, y, z)
        self._delta_rot = np.zeros(3)  # (roll, pitch, yaw)
        self._additional_callbacks = {}

        # Open the device
        try:
            success = pyspacemouse.open(
                dof_callback=self._cb_dof,
                button_callback=self._cb_button,
            )
            if success:
                # Run a background thread for the device
                self._thread = threading.Thread(target=self._run_device)
                self._thread.daemon = True
                self._thread.start()
            else:
                print(
                    "[ERROR] Failed to open a SpaceMouse device. Is it connected?",
                    file=sys.stderr,
                )
        except Exception as e:
            print(
                f"[ERROR] Failed to open a SpaceMouse device. Is it connected?\n{e}",
                file=sys.stderr,
            )

    def __del__(self):
        self._thread.join()

    def __str__(self) -> str:
        msg = f"Spacemouse Controller ({self.__class__.__name__})\n"
        msg += "\tToggle gripper (alternative): Right button\n"
        msg += "\tReset: Left button\n"
        return msg

    def reset(self):
        # Default flags
        self._close_gripper = False
        self._delta_pos = np.zeros(3)
        self._delta_rot = np.zeros(3)

    def add_callback(self, key: str, func: Callable):
        if key not in ["L", "R", "LR"]:
            raise ValueError(
                f"Only left (L), right (R), and right-left (LR) buttons supported. Provided: {key}."
            )
        self._additional_callbacks[key] = func

    def advance(self) -> tuple[np.ndarray, bool]:
        rot_vec = Rotation.from_euler("XYZ", self._delta_rot).as_rotvec()
        return np.concatenate([self._delta_pos, rot_vec]), self._close_gripper

    def _run_device(self):
        while True:
            _state = pyspacemouse.read()
            time.sleep(self.sleep_rate)

    def _cb_dof(self, state: pyspacemouse.SpaceNavigator):
        self._delta_pos = np.array(
            [
                state.y * self.pos_sensitivity,
                -state.x * self.pos_sensitivity,
                state.z * self.pos_sensitivity,
            ]
        )
        self._delta_rot = np.array(
            [
                -state.roll * self.rot_sensitivity,
                -state.pitch * self.rot_sensitivity,
                -state.yaw * self.rot_sensitivity,
            ]
        )

    def _cb_button(self, state: pyspacemouse.SpaceNavigator, buttons: List[bool]):
        if buttons[0]:
            self.reset()
            if "L" in self._additional_callbacks.keys():
                self._additional_callbacks["L"]()
        if buttons[1]:
            self._close_gripper = not self._close_gripper
            if "R" in self._additional_callbacks.keys():
                self._additional_callbacks["R"]()
        if all(buttons):
            if "LR" in self._additional_callbacks.keys():
                self._additional_callbacks["LR"]()