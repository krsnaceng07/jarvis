"""jarvis.system.audio_controller — Windows Core Audio master volume and mute controller.

Implements native COM interface access to IAudioEndpointVolume and IMMDeviceEnumerator
via pure Python ctypes. Provides 100% accurate volume measurement, scalar normalization,
safe volume modification, mute management, and post-action physical verification.
"""

from __future__ import annotations

import ctypes
from ctypes import HRESULT, POINTER, Structure, byref, c_float, c_void_p, wintypes
from typing import Any, Dict, Optional, Tuple
import uuid

ole32 = ctypes.oledll.ole32


class GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

    def __init__(self, guid_str: str) -> None:
        super().__init__()
        u = uuid.UUID(guid_str)
        self.Data1 = u.time_low
        self.Data2 = u.time_mid
        self.Data3 = u.time_hi_version
        for i in range(8):
            self.Data4[i] = u.bytes[8 + i]


CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IAudioEndpointVolume = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")


class IMMDeviceEnumeratorVtbl(Structure):
    _fields_ = [
        ("QueryInterface", c_void_p),
        ("AddRef", c_void_p),
        ("Release", c_void_p),
        ("EnumAudioEndpoints", c_void_p),
        (
            "GetDefaultAudioEndpoint",
            ctypes.WINFUNCTYPE(HRESULT, c_void_p, wintypes.DWORD, wintypes.DWORD, POINTER(c_void_p)),
        ),
        ("GetDevice", c_void_p),
        ("RegisterEndpointNotificationCallback", c_void_p),
        ("UnregisterEndpointNotificationCallback", c_void_p),
    ]


class IMMDeviceVtbl(Structure):
    _fields_ = [
        ("QueryInterface", c_void_p),
        ("AddRef", c_void_p),
        ("Release", c_void_p),
        (
            "Activate",
            ctypes.WINFUNCTYPE(
                HRESULT, c_void_p, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p)
            ),
        ),
        ("OpenPropertyStore", c_void_p),
        ("GetId", c_void_p),
        ("GetState", c_void_p),
    ]


class IAudioEndpointVolumeVtbl(Structure):
    _fields_ = [
        ("QueryInterface", c_void_p),
        ("AddRef", c_void_p),
        ("Release", c_void_p),
        ("RegisterControlChangeNotify", c_void_p),
        ("UnregisterControlChangeNotify", c_void_p),
        ("GetChannelCount", c_void_p),
        ("SetMasterVolumeLevel", c_void_p),
        ("SetMasterVolumeLevelScalar", ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_float, POINTER(GUID))),
        ("GetMasterVolumeLevel", c_void_p),
        ("GetMasterVolumeLevelScalar", ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_float))),
        ("SetChannelVolumeLevel", c_void_p),
        ("SetChannelVolumeLevelScalar", c_void_p),
        ("GetChannelVolumeLevel", c_void_p),
        ("GetChannelVolumeLevelScalar", c_void_p),
        ("SetMute", ctypes.WINFUNCTYPE(HRESULT, c_void_p, wintypes.BOOL, POINTER(GUID))),
        ("GetMute", ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(wintypes.BOOL))),
        ("GetVolumeStepInfo", c_void_p),
        ("VolumeStepUp", c_void_p),
        ("VolumeStepDown", c_void_p),
        ("QueryHardwareSupport", c_void_p),
        ("GetVolumeRange", c_void_p),
    ]


class AudioController:
    """Windows Core Audio hardware-grounded volume and mute controller."""

    _instance: Optional[AudioController] = None

    @classmethod
    def get_instance(cls) -> AudioController:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _acquire_endpoint() -> Tuple[Optional[Tuple[Any, Any]], Optional[str]]:
        """Acquire Windows default audio endpoint COM interface."""
        try:
            ole32.CoInitialize(None)
            enumerator = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(CLSID_MMDeviceEnumerator),
                None,
                1,  # CLSCTX_INPROC_SERVER
                byref(IID_IMMDeviceEnumerator),
                byref(enumerator),
            )
            if hr != 0:
                return None, f"CoCreateInstance failed with HRESULT 0x{hr:x}"

            enum_vtbl = ctypes.cast(
                ctypes.cast(enumerator, POINTER(c_void_p)).contents,
                POINTER(IMMDeviceEnumeratorVtbl),
            ).contents

            device = c_void_p()
            # eRender = 0, eMultimedia = 1
            hr = enum_vtbl.GetDefaultAudioEndpoint(enumerator, 0, 1, byref(device))
            if hr != 0:
                return None, f"GetDefaultAudioEndpoint failed with HRESULT 0x{hr:x}"

            dev_vtbl = ctypes.cast(
                ctypes.cast(device, POINTER(c_void_p)).contents,
                POINTER(IMMDeviceVtbl),
            ).contents

            endpoint = c_void_p()
            hr = dev_vtbl.Activate(device, byref(IID_IAudioEndpointVolume), 23, None, byref(endpoint))
            if hr != 0:
                return None, f"Activate IAudioEndpointVolume failed with HRESULT 0x{hr:x}"

            ep_vtbl = ctypes.cast(
                ctypes.cast(endpoint, POINTER(c_void_p)).contents,
                POINTER(IAudioEndpointVolumeVtbl),
            ).contents

            return (endpoint, ep_vtbl), None
        except Exception as e:
            return None, f"Windows Audio API exception: {e}"

    def get_volume(self) -> Dict[str, Any]:
        """Read actual current system volume percentage, scalar, and mute state."""
        handle, err = self._acquire_endpoint()
        if not handle:
            return {
                "ok": False,
                "error": "The current volume could not be verified.",
                "details": err,
                "verified": False,
            }
        endpoint, ep_vtbl = handle
        try:
            vol = c_float()
            hr = ep_vtbl.GetMasterVolumeLevelScalar(endpoint, byref(vol))
            if hr != 0:
                return {
                    "ok": False,
                    "error": "The current volume could not be verified.",
                    "details": f"GetMasterVolumeLevelScalar failed with HRESULT 0x{hr:x}",
                    "verified": False,
                }
            mute = wintypes.BOOL()
            ep_vtbl.GetMute(endpoint, byref(mute))
            percent = int(round(vol.value * 100))
            is_muted = bool(mute.value)
            return {
                "ok": True,
                "volume_percent": percent,
                "volume_scalar": round(vol.value, 4),
                "muted": is_muted,
                "device_name": "Default Windows Audio Device",
                "formatted": f"System volume is currently {percent}%, {'muted' if is_muted else 'unmuted'}.",
                "verified": True,
            }
        finally:
            ole32.CoUninitialize()

    def set_volume(self, target_percent: int) -> Dict[str, Any]:
        """Set master volume percentage [0-100] and verify physical outcome."""
        target_percent = max(0, min(100, int(target_percent)))
        target_scalar = round(target_percent / 100.0, 4)

        handle, err = self._acquire_endpoint()
        if not handle:
            return {
                "ok": False,
                "error": "The current volume could not be verified.",
                "details": err,
                "verified": False,
            }
        endpoint, ep_vtbl = handle
        try:
            hr = ep_vtbl.SetMasterVolumeLevelScalar(endpoint, c_float(target_scalar), None)
            if hr != 0:
                return {
                    "ok": False,
                    "error": f"Failed to set master volume: HRESULT 0x{hr:x}",
                    "verified": False,
                }

            # If unmuting when raising volume > 0, make sure mute is cleared
            if target_percent > 0:
                mute_check = wintypes.BOOL()
                ep_vtbl.GetMute(endpoint, byref(mute_check))
                if mute_check.value:
                    ep_vtbl.SetMute(endpoint, wintypes.BOOL(False), None)

            # Verification read-back
            vol = c_float()
            ep_vtbl.GetMasterVolumeLevelScalar(endpoint, byref(vol))
            mute = wintypes.BOOL()
            ep_vtbl.GetMute(endpoint, byref(mute))

            actual_percent = int(round(vol.value * 100))
            is_muted = bool(mute.value)
            verified = abs(actual_percent - target_percent) <= 1

            return {
                "ok": True,
                "volume_percent": actual_percent,
                "volume_scalar": round(vol.value, 4),
                "muted": is_muted,
                "target_percent": target_percent,
                "verified": verified,
                "formatted": f"Volume set to {actual_percent}%, {'muted' if is_muted else 'unmuted'}.",
            }
        finally:
            ole32.CoUninitialize()

    def adjust_volume(self, delta_percent: int) -> Dict[str, Any]:
        """Increase or decrease master volume by delta_percent and verify."""
        current = self.get_volume()
        if not current.get("ok"):
            return current
        current_pct = current["volume_percent"]
        target = max(0, min(100, current_pct + delta_percent))
        return self.set_volume(target)

    def set_mute(self, mute_state: bool) -> Dict[str, Any]:
        """Mute or unmute system audio and verify physical state."""
        handle, err = self._acquire_endpoint()
        if not handle:
            return {
                "ok": False,
                "error": "The mute state could not be verified.",
                "details": err,
                "verified": False,
            }
        endpoint, ep_vtbl = handle
        try:
            hr = ep_vtbl.SetMute(endpoint, wintypes.BOOL(mute_state), None)
            if hr != 0:
                return {
                    "ok": False,
                    "error": f"Failed to set mute state: HRESULT 0x{hr:x}",
                    "verified": False,
                }
            # Verification read-back
            mute = wintypes.BOOL()
            ep_vtbl.GetMute(endpoint, byref(mute))
            vol = c_float()
            ep_vtbl.GetMasterVolumeLevelScalar(endpoint, byref(vol))

            actual_muted = bool(mute.value)
            verified = (actual_muted == mute_state)
            pct = int(round(vol.value * 100))

            return {
                "ok": True,
                "muted": actual_muted,
                "volume_percent": pct,
                "verified": verified,
                "formatted": f"Audio is now {'muted' if actual_muted else 'unmuted'} (volume: {pct}%).",
            }
        finally:
            ole32.CoUninitialize()
