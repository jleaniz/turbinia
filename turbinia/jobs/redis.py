# -*- coding: utf-8 -*-
# Copyright 2015 Google Inc.
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
"""Job to execute redis_config analysis task."""

from turbinia.workers import artifact
from turbinia.workers import redis
from turbinia.evidence.containers import ContainerdContainer, DockerContainer
from turbinia.evidence.directory import Directory
from turbinia.evidence.gcp import GoogleCloudDisk, GoogleCloudDiskRawEmbedded
from turbinia.evidence.raw import RawDisk
from turbinia.evidence.ewf import EwfDisk
from turbinia.evidence.exported_file_artifact import ExportedFileArtifact
from turbinia.evidence.text_file import ReportText
from turbinia.jobs import interface
from turbinia.jobs import manager


class RedisExtractionJob(interface.TurbiniaJob):
  """Extract Redis configuration files for analysis."""

  # The types of evidence that this Job will process
  evidence_input = [
      ContainerdContainer, Directory, DockerContainer, GoogleCloudDisk,
      GoogleCloudDiskRawEmbedded, RawDisk, EwfDisk
  ]
  evidence_output = [ExportedFileArtifact]

  NAME = 'RedisExtractionJob'

  def create_tasks(self, evidence):
    """Create task.

    Args:
      evidence: List of evidence objects to process

    Returns:
        A list of tasks to schedule.
    """
    tasks = [
        artifact.FileArtifactExtractionTask('RedisConfigFile') for _ in evidence
    ]
    return tasks


class RedisAnalysisJob(interface.TurbiniaJob):
  """Create tasks to analyse Redis configuration files."""

  evidence_input = [ExportedFileArtifact]
  evidence_output = [ReportText]

  NAME = 'RedisAnalysisJob'

  def create_tasks(self, evidence):
    """Create task.

    Args:
      evidence: List of evidence objects to process

    Returns:
        A list of tasks to schedule.
    """
    tasks = []
    for evidence_item in evidence:
      if evidence_item.artifact_name == 'RedisConfigFile':
        tasks.append(redis.RedisAnalysisTask())
    return tasks


manager.JobsManager.RegisterJobs([RedisAnalysisJob, RedisExtractionJob])
