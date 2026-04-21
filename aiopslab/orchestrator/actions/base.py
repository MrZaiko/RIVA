# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Base class for task actions."""

import os
import re
from datetime import datetime, timedelta

import pandas as pd

# from aiopslab.observer import initialize_pod_and_service_lists
from aiopslab.observer.metric_api import PrometheusAPI
from aiopslab.observer.trace_api import TraceAPI
from aiopslab.orchestrator.actions.log_deduplication import greedy_compress_lines
from aiopslab.service.dock import Docker
from aiopslab.service.kubectl import KubeCtl
from aiopslab.service.shell import Shell
from aiopslab.utils.actions import action, read, read_bug, write

LOG_COMMAND_PATTERN: str = (
    r"\b(?:"
    r"kubectl\s+(?:logs|get\s+events|describe|get\s+\S+\s+-w)"  # logs/events/describe/watch
    r"|docker\s+(?:logs|events)"  # docker logs/events
    r")\b(?:[^\n]*)"
)

generating_for = None
tool_history = {}
MAX_TOOLS_PER_GOAL = 2


class TaskActions:
    """Base class for task actions."""

    @staticmethod
    @read
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
        print(logs)

        return logs

    @staticmethod
    @action
    def exec_shell(command: str, timeout: int = 30) -> str:
        """
        Execute any shell command in a predefined debugging environment.
        Note: this is NOT A STATEFUL OR INTERACTIVE shell session. So you cannot
        execute commands like "kubectl edit".

        Args:
            command (str): The command to execute.
            timeout (int): Timeout in seconds for the command execution. Default is 30.

        Returns:
            str: The output of the command.
        """
        BLOCK_LIST: dict[str, str] = {
            "kubectl edit": "Error: Cannot use `kubectl edit`. Use `kubectl patch` instead.",
            "edit svc": "Error: Cannot use `kubectl edit`. Use `kubectl patch` instead.",
            "kubectl port-forward": "Error: Cannot use `kubectl port-forward` because it is an interactive command.",
            "docker logs -f": "Error: Cannot use `docker logs -f`. Use `docker logs` instead.",
            "kubectl logs -f": "Error: Cannot use `kubectl logs -f`. Use `kubectl logs` instead.",
        }
        for pattern, error in BLOCK_LIST.items():
            if pattern in command:
                return error

        result = Shell.exec(command)

        if re.search(LOG_COMMAND_PATTERN, command):
            result = greedy_compress_lines(result)

        print(result)

        return result

    @staticmethod
    @read
    def get_metrics(namespace: str, duration: int = 5) -> str:
        """
        Collects metrics data from the service using Prometheus.

        Args:
            namespace (str): The namespace in which the service is running.
            duration (int): The number of minutes from now to start collecting metrics until now.

        Returns:
            str: Path to the directory where metrics are saved.
        """
        prometheus_url = (
            "http://localhost:32000"  # Replace with your Prometheus server URL
        )
        prometheus_api = PrometheusAPI(prometheus_url, namespace)
        prometheus_api.initialize_pod_and_service_lists(namespace)

        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=duration)
        save_path = os.path.join(os.getcwd(), "metrics_output")

        # Export all metrics and save to the specified path
        save_dir_str = prometheus_api.export_all_metrics(
            start_time=start_time, end_time=end_time, save_path=save_path, step=15
        )

        return save_dir_str

    @staticmethod
    @read
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

            return df_metrics.to_string(index=False)

        except Exception as e:
            return f"Failed to read metrics: {str(e)}"

    @staticmethod
    @read
    def get_traces(namespace: str, duration: int = 5) -> str:
        """
        Collects trace data from the service using Jaeger.

        Args:
            namespace (str): The namespace in which the service is running.
            duration (int): The number of minutes from now to start collecting traces until now.

        Returns:
            str: Path to the directory where traces are saved.
        """
        # jaeger_url = "http://localhost:16686"
        print(namespace)
        trace_api = TraceAPI(namespace=namespace)

        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=duration)

        traces = trace_api.extract_traces(start_time=start_time, end_time=end_time)
        df_traces = trace_api.process_traces(traces)
        save_path = os.path.join(os.getcwd(), "trace_output")

        return trace_api.save_traces(df_traces, save_path)
        # return f"Trace data exported to: {save_path}"

    @staticmethod
    @read
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

            return df_traces.to_string(index=False)

        except Exception as e:
            return f"Failed to read traces: {str(e)}"

    @staticmethod
    @read
    def get_goals() -> str:
        """
        Reads and returns the registered goals in the tool history

        Returns:
            str: The list of goals
        """

        return "The goals currently in the history are:\n" + ", ".join(
            tool_history.keys()
        )

    @staticmethod
    @read
    def get_command_goal(goal) -> str:
        """
        Reads and returns the commands and result related to the specified goal.

        Args:
            goal (str): The name of the goal.

        Returns:
            str: The list of goals
        """

        if goal not in tool_history:
            return f"error: Goal '{goal}' not found in tool history."

        commands = tool_history[goal]

        return "Command -> Result:\n\n" + "\n".join(
            f"{c['command']} -> {c['result']}" for c in commands
        )

    @staticmethod
    @read
    def add_goal(goal) -> str:
        """
        Add an entry for the specified goal in the goal history. A goal must be a small (3 to 5 words) string describing the goal of the commands linked to it. For example, if you want to generate commands to get logs from service_name, the goal should be named: get_logs_service_name.

        Args:
            goal (str): The name of the goal.

        Returns:
            str: if the operation was successfully performed
        """

        if goal in tool_history:
            return f"error: Goal '{goal}' already exists in tool history."

        tool_history[goal] = []

        return f"Goal '{goal}' added successfully."

    @staticmethod
    @read
    def ask_generator(goal, task) -> str:
        """
        Ask a generator agent to generate a tool call to perform the specified task.

        Args:
            goal (str): The name of the goal in the tool history.
            task (str): The action to generate the tool call for. For example, if you want to gather logs from a service, this argument shoiuld be: "get the logs from service_name"

        Returns:
            str: if the operation was successfully performed
        """

        global generating_for

        if goal not in tool_history:
            return f"error: Goal '{goal}' not found in tool history."

        if len(tool_history[goal]) >= MAX_TOOLS_PER_GOAL:
            return f"error: Maximum number of tool_calls ({MAX_TOOLS_PER_GOAL}) reached for goal '{goal}'"

        generating_for = goal

        return (
            "\n".join(f"{c['command']}" for c in tool_history[goal]) + "---" + f"{task}"
        )

    @staticmethod
    @read
    def submit_generated_tool(command, result) -> str:
        """
        Submit the generated tool call alongside its result.

        Args:
            command (str): The generated tool call
            result (str): The observation generated by the tool call. This needs to be the exact return value from the tool call (not a summary, not only a subset)

        Returns:
            str: if the operation was successfully performed
        """

        tool_history[generating_for].append({"command": command, "result": result})

        return f"Added generated command to goal: {generating_for}"
