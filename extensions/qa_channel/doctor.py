"""Compatibility shim for ``extensions.qa_channel.doctor``."""

from __future__ import annotations

from importlib import import_module

_module = import_module("extensions.qa-channel.doctor")

QAChannelDoctorStatus = _module.QAChannelDoctorStatus
qa_channel_doctor_contract = _module.qa_channel_doctor_contract

__all__ = ["QAChannelDoctorStatus", "qa_channel_doctor_contract"]
