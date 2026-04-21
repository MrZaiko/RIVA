# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Actions for the detection task."""

from aiopslab.orchestrator.bugged_actions.base import TaskActions
from aiopslab.utils.actions import action
from aiopslab.utils.status import SubmissionStatus


class DetectionActions(TaskActions):
    """
    Class for detection task's actions.
    """
