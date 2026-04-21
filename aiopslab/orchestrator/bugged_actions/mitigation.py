# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Actions for the mitigation task."""

from aiopslab.orchestrator.bugged_actions.base import TaskActions
from aiopslab.utils.actions import action
from aiopslab.utils.status import SubmissionStatus


class MitigationActions(TaskActions):
    """
    Class for mitigation task's actions.
    """
