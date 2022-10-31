# -*- coding: utf-8 -*-
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Job to execute partition enumeration task."""

from turbinia.evidence.ewf import EwfDisk
from turbinia.evidence.disk_partition import DiskPartition
from turbinia.evidence.gcp import GoogleCloudDisk, GoogleCloudDiskRawEmbedded
from turbinia.evidence.raw import RawDisk
from turbinia.jobs import interface
from turbinia.jobs import manager
from turbinia.workers.partitions import PartitionEnumerationTask


class PartitionEnumerationJob(interface.TurbiniaJob):
  """Partition Enumeration Job.

  This will generate a Partition Enumeration task for each piece of evidence.
  """

  # The types of evidence that this Job will process
  evidence_input = [
      EwfDisk, GoogleCloudDisk, GoogleCloudDiskRawEmbedded, RawDisk
  ]
  evidence_output = [DiskPartition]

  NAME = 'PartitionEnumerationJob'

  def create_tasks(self, evidence):
    """Create task for Partition Enumeration.

    Args:
      evidence: List of evidence objects to process

    Returns:
        A list of tasks to schedule.
    """
    tasks = [PartitionEnumerationTask() for _ in evidence]
    return tasks


manager.JobsManager.Register(PartitionEnumerationJob)
