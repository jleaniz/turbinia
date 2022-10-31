# -*- coding: utf-8 -*-
# Copyright 2020 Google Inc.
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
"""Job to execute Jupyter Notebook config analysis."""

from __future__ import unicode_literals

from turbinia.workers import artifact
from turbinia.evidence.containers import ContainerdContainer, DockerContainer
from turbinia.evidence.directory import Directory
from turbinia.evidence.ewf import EwfDisk
from turbinia.evidence.gcp import GoogleCloudDisk, GoogleCloudDiskRawEmbedded
from turbinia.evidence.raw import RawDisk
from turbinia.evidence.exported_file_artifact import ExportedFileArtifact
from turbinia.evidence.text_file import ReportText
from turbinia.jobs import interface
from turbinia.jobs import manager
from turbinia.workers.analysis.jupyter import JupyterAnalysisTask


class JupyterExtractionJob(interface.TurbiniaJob):
  """Extract Jupyter configuration files for analysis."""

  # The types of evidence that this Job will process
  evidence_input = [
      ContainerdContainer, Directory, DockerContainer, EwfDisk, GoogleCloudDisk,
      GoogleCloudDiskRawEmbedded, RawDisk
  ]
  evidence_output = [ExportedFileArtifact]

  NAME = 'JupyterExtractionJob'

  def create_tasks(self, evidence):
    """Create task.
    Args:
      evidence: List of evidence objects to process
    Returns:
        A list of tasks to schedule.
    """
    tasks = [
        artifact.FileArtifactExtractionTask('JupyterConfigFile')
        for _ in evidence
    ]
    return tasks


class JupyterAnalysisJob(interface.TurbiniaJob):
  """Jupyter analysis job."""

  evidence_input = [ExportedFileArtifact]
  evidence_output = [ReportText]

  NAME = 'JupyterAnalysisJob'

  def create_tasks(self, evidence):
    """Create task for Jupyter analysis job.

    Args:
      evidence: List of evidence objects to process

    Returns:
        A list of tasks to schedule.
    """
    tasks = []
    for evidence_item in evidence:
      if evidence_item.artifact_name == 'JupyterConfigFile':
        tasks.append(JupyterAnalysisTask())
    return tasks


manager.JobsManager.RegisterJobs([JupyterExtractionJob, JupyterAnalysisJob])
