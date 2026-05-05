"""Adapters from current infrastructure models into meridian-core contracts."""

from meridian.adapters.execution import RemoteExecutorConnection, legacy_command_result
from meridian.adapters.reporters import JsonlReporter
from meridian.adapters.ssh import SSHRemoteExecutor, remote_command_result, ssh_remote_executor

__all__ = [
    "RemoteExecutorConnection",
    "SSHRemoteExecutor",
    "JsonlReporter",
    "legacy_command_result",
    "remote_command_result",
    "ssh_remote_executor",
]
