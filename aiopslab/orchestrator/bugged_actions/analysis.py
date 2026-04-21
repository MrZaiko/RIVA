# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Actions for the root-cause analysis task."""

from aiopslab.orchestrator.bugged_actions.base import TaskActions
from aiopslab.utils.actions import action
from aiopslab.utils.status import SubmissionStatus


class AnalysisActions(TaskActions):
    """
    Class for root-cause analysis task's actions.
    """
