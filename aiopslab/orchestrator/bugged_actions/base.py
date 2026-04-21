# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Base class for task actions."""

import os
import pandas as pd
from datetime import datetime, timedelta
from aiopslab.utils.actions import action, read, read_bug, write
from aiopslab.service.kubectl import KubeCtl
from aiopslab.service.dock import Docker
from aiopslab.service.shell import Shell

# from aiopslab.observer import initialize_pod_and_service_lists
from aiopslab.observer.metric_api import PrometheusAPI
from aiopslab.observer.trace_api import TraceAPI

from aiopslab.orchestrator.actions.log_deduplication import greedy_compress_lines

import re

LOG_COMMAND_PATTERN: str = (
    r"\b(?:"
    r"kubectl\s+(?:logs|get\s+events|describe|get\s+\S+\s+-w)"  # logs/events/describe/watch
    r"|docker\s+(?:logs|events)"  # docker logs/events
    r")\b(?:[^\n]*)"
)


class TaskActions:
    """Base class for task actions."""

    @staticmethod
    @read_bug
    def get_logs(namespace: str, service: str) -> str:
        """
        Collects relevant log data from a pod using Kubectl or from a container with Docker.

        Args:
            namespace (str): The namespace in which the service is running.
            service (str): The name of the service.

        Returns:
            str | dict | list[dicts]: Log data as a structured object or a string.
        """
        if namespace == "docker":
            docker = Docker()
            try:
                logs = docker.get_logs(service)
            except Exception as e:
                return "Error: Your service does not exist. Use docker to check."

        else:
            kubectl = KubeCtl()
            try:
                if namespace == "test-social-network":
                    user_service_pod = kubectl.get_pod_name(namespace, f"app={service}")
                elif namespace == "test-hotel-reservation":
                    user_service_pod = kubectl.get_pod_name(
                        namespace, f"io.kompose.service={service}"
                    )
                elif namespace == "astronomy-shop":
                    user_service_pod = kubectl.get_pod_name(
                        namespace, f"app.kubernetes.io/name={service}"
                    )
                elif namespace == "default" and "wrk2-job" in service:
                    user_service_pod = kubectl.get_pod_name(
                        namespace, f"job-name=wrk2-job"
                    )
                else:
                    raise Exception
                logs = kubectl.get_pod_logs(user_service_pod, namespace)
            except Exception as e:
                return "Error: Your service/namespace does not exist. Use kubectl to check."

        logs = greedy_compress_lines(logs)

        return ""

    @staticmethod
    @read_bug
    def read_metrics(file_path: str) -> str:
        """
        Reads and returns metrics from a specified CSV file.

        Args:
            file_path (str): Path to the metrics file (CSV format).

        Returns:
            str: The requested metrics or an error message.
        """
        if not os.path.exists(file_path):
            return f"error: Metrics file '{file_path}' not found."

        try:
            df_metrics = pd.read_csv(file_path)

            return ""

        except Exception as e:
            return f"Failed to read metrics: {str(e)}"

    @staticmethod
    @read_bug
    def read_traces(file_path: str) -> str:
        """
        Reads and returns traces from a specified CSV file.

        Args:
            file_path (str): Path to the traces file (CSV format).

        Returns:
            str: The requested traces or an error message.
        """
        if not os.path.exists(file_path):
            return f"error: Traces file '{file_path}' not found."

        try:
            df_traces = pd.read_csv(file_path)

            return ""

        except Exception as e:
            return f"Failed to read traces: {str(e)}"
