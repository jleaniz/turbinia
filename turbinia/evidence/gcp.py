# -*- coding: utf-8 -*-
# Copyright 2022 Google Inc.
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
"""Turbinia evidence."""

import os
import filelock

from turbinia.evidence import interface
from turbinia.processors import mount_local
from turbinia import config
from turbinia import TurbiniaException

config.LoadConfig()
if config.CLOUD_PROVIDER:
  from turbinia.processors import google_cloud


class GoogleCloudDisk(interface.Evidence):
  """Evidence object for a Google Cloud Disk.

  Attributes:
    project: The cloud project name this disk is associated with.
    zone: The geographic zone.
    disk_name: The cloud disk name.
  """

  REQUIRED_ATTRIBUTES = ['disk_name', 'project', 'zone']
  POSSIBLE_STATES = [
      interface.EvidenceState.ATTACHED, interface.EvidenceState.MOUNTED
  ]

  def __init__(
      self, project=None, zone=None, disk_name=None, mount_partition=1, *args,
      **kwargs):
    """Initialization for Google Cloud Disk."""
    super(GoogleCloudDisk, self).__init__(*args, **kwargs)
    self.project = project
    self.zone = zone
    self.disk_name = disk_name
    self.mount_partition = mount_partition
    self.partition_paths = None
    self.cloud_only = True
    self.resource_tracked = True
    self.resource_id = self.disk_name
    self.device_path = None

  def _preprocess(self, _, required_states):
    # The GoogleCloudDisk should never need to be mounted unless it has child
    # evidence (GoogleCloudDiskRawEmbedded). In all other cases, the
    # DiskPartition evidence will be used. In this case we're breaking the
    # evidence layer isolation and having the child evidence manage the
    # mounting and unmounting.

    # Explicitly lock this method to prevent race condition with two workers
    # attempting to attach disk at same time, given delay with attaching in GCP.
    with filelock.FileLock(config.RESOURCE_FILE_LOCK):
      if interface.EvidenceState.ATTACHED in required_states:
        self.device_path, partition_paths = google_cloud.PreprocessAttachDisk(
            self.disk_name)
        self.partition_paths = partition_paths
        self.local_path = self.device_path
        self.state[interface.EvidenceState.ATTACHED] = True

  def _postprocess(self):
    if self.state[interface.EvidenceState.ATTACHED]:
      google_cloud.PostprocessDetachDisk(self.disk_name, self.device_path)
      self.state[interface.EvidenceState.ATTACHED] = False


class GoogleCloudDiskRawEmbedded(GoogleCloudDisk):
  """Evidence object for raw disks embedded in Persistent Disks.

  This is for a raw image file that is located in the filesystem of a mounted
  GCP Persistent Disk.  This can be useful if you want to process a raw disk
  image originating from outside cloud, and it is much more performant and
  reliable option than reading it directly from GCS FUSE.

  Attributes:
    embedded_path: The path of the raw disk image inside the Persistent Disk
  """

  REQUIRED_ATTRIBUTES = ['disk_name', 'project', 'zone', 'embedded_path']
  POSSIBLE_STATES = [interface.EvidenceState.ATTACHED]

  def __init__(
      self, embedded_path=None, project=None, zone=None, disk_name=None,
      mount_partition=1, *args, **kwargs):
    """Initialization for Google Cloud Disk containing a raw disk image."""
    super(GoogleCloudDiskRawEmbedded, self).__init__(
        project=project, zone=zone, disk_name=disk_name, mount_partition=1,
        *args, **kwargs)
    self.embedded_path = embedded_path
    # This Evidence needs to have a GoogleCloudDisk as a parent
    self.context_dependent = True

  @property
  def name(self):
    if self._name:
      return self._name
    else:
      return ':'.join((self.disk_name, self.embedded_path))

  def _preprocess(self, _, required_states):
    # Need to mount parent disk
    if not self.parent_evidence.partition_paths:
      self.parent_evidence.mount_path = mount_local.PreprocessMountPartition(
          self.parent_evidence.device_path, self.path_spec.type_indicator)
    else:
      partition_paths = self.parent_evidence.partition_paths
      self.parent_evidence.mount_path = mount_local.PreprocessMountDisk(
          partition_paths, self.parent_evidence.mount_partition)
    self.parent_evidence.local_path = self.parent_evidence.mount_path
    self.parent_evidence.state[interface.EvidenceState.MOUNTED] = True

    if interface.EvidenceState.ATTACHED in required_states or self.has_child_evidence:
      rawdisk_path = os.path.join(
          self.parent_evidence.mount_path, self.embedded_path)
      if not os.path.exists(rawdisk_path):
        raise TurbiniaException(
            f'Unable to find raw disk image {rawdisk_path:s} in GoogleCloudDisk'
        )
      self.device_path = mount_local.PreprocessLosetup(rawdisk_path)
      self.state[interface.EvidenceState.ATTACHED] = True
      self.local_path = self.device_path

  def _postprocess(self):
    if self.state[interface.EvidenceState.ATTACHED]:
      mount_local.PostprocessDeleteLosetup(self.device_path)
      self.state[interface.EvidenceState.ATTACHED] = False

    # Need to unmount parent disk
    if self.parent_evidence.state[interface.EvidenceState.MOUNTED]:
      mount_local.PostprocessUnmountPath(self.parent_evidence.mount_path)
      self.parent_evidence.state[interface.EvidenceState.MOUNTED] = False
