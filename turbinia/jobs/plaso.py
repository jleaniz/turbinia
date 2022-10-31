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
"""Job to execute Plaso task."""

from turbinia.evidence.ewf import EwfDisk
from turbinia.evidence.bodyfile import BodyFile
from turbinia.evidence.containers import ContainerdContainer, DockerContainer
from turbinia.evidence.directory import CompressedDirectory, Directory
from turbinia.evidence.gcp import GoogleCloudDisk, GoogleCloudDiskRawEmbedded
from turbinia.evidence.plaso import PlasoFile
from turbinia.evidence.raw import RawDisk
from turbinia.jobs import interface
from turbinia.jobs import manager
from turbinia.workers.plaso import PlasoParserTask
from turbinia.workers.plaso import PlasoHasherTask


class PlasoJob(interface.TurbiniaJob):
  """Runs Plaso on some evidence to generate a Plaso file."""
  # The types of evidence that this Job will process
  evidence_input = [
      BodyFile, ContainerdContainer, Directory, EwfDisk, RawDisk,
      GoogleCloudDisk, GoogleCloudDiskRawEmbedded, CompressedDirectory,
      DockerContainer
  ]
  evidence_output = [PlasoFile]

  NAME = 'PlasoJob'

  def create_tasks(self, evidence):
    """Create task for Plaso.

    Args:
      evidence: List of evidence objects to process

    Returns:
        A list of PlasoParserTask and PlasoHasherTask objects.
    """
    tasks = []
    for evidence_object in evidence:
      # No need to run the hasher task for BodyFile type.
      if evidence_object.type is not 'BodyFile':
        tasks.append(PlasoHasherTask())
      tasks.append(PlasoParserTask())
    return tasks


manager.JobsManager.Register(PlasoJob)
