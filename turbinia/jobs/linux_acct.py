# -*- coding: utf-8 -*-
# Copyright 2021 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Job to execute linux_acct analysis task."""

from turbinia.evidence.containers import ContainerdContainer, DockerContainer
from turbinia.evidence.directory import CompressedDirectory, Directory
from turbinia.evidence.ewf import EwfDisk
from turbinia.evidence.gcp import GoogleCloudDisk, GoogleCloudDiskRawEmbedded
from turbinia.evidence.raw import RawDisk
from turbinia.evidence.text_file import ReportText
from turbinia.jobs import interface
from turbinia.jobs import manager
from turbinia.workers.analysis import linux_acct


class LinuxAccountAnalysisJob(interface.TurbiniaJob):
  """Linux Account analysis job."""

  evidence_input = [
      CompressedDirectory, ContainerdContainer, Directory, DockerContainer,
      EwfDisk, GoogleCloudDisk, GoogleCloudDiskRawEmbedded, RawDisk
  ]
  evidence_output = [ReportText]

  NAME = 'LinuxAccountAnalysisJob'

  def create_tasks(self, evidence):
    """Create task.
    Args:
      evidence: List of evidence objects to process
    Returns:
        A list of tasks to schedule.
    """
    tasks = [linux_acct.LinuxAccountAnalysisTask() for _ in evidence]
    return tasks


manager.JobsManager.Register(LinuxAccountAnalysisJob)
