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
import logging

from turbinia import TurbiniaException
from turbinia.evidence import interface
from turbinia.processors import mount_local

log = logging.getLogger('turbinia')

class DiskPartition(interface.Evidence):
  """Evidence object for a partition within Disk based evidence.

  More information on dfVFS types:
  https://dfvfs.readthedocs.io/en/latest/sources/Path-specifications.html

  Attributes:
    partition_location (str): dfVFS partition location (The location of the
        volume within the volume system, similar to a volume identifier).
    partition_offset (int): Offset of the partition in bytes.
    partition_size (int): Size of the partition in bytes.
    path_spec (dfvfs.PathSpec): Partition path spec.
  """
  POSSIBLE_STATES = [
      interface.EvidenceState.ATTACHED, interface.EvidenceState.MOUNTED
  ]

  def __init__(
      self, partition_location=None, partition_offset=None, partition_size=None,
      lv_uuid=None, path_spec=None, important=True, *args, **kwargs):
    """Initialization for raw volume evidence object."""
    self.partition_location = partition_location
    if partition_offset:
      try:
        self.partition_offset = int(partition_offset)
      except ValueError as exception:
        log.errorf(
            f'Unable to cast partition_offset attribute to integer. {exception!s}'
        )
    if partition_size:
      try:
        self.partition_size = int(partition_size)
      except ValueError as exception:
        log.errorf(
            f'Unable to cast partition_size attribute to integer. {exception!s}'
        )
    self.lv_uuid = lv_uuid
    self.path_spec = path_spec
    self.important = important
    super(DiskPartition, self).__init__(*args, **kwargs)

    # This Evidence needs to have a parent
    self.context_dependent = True

  @property
  def name(self):
    if self._name:
      return self._name
    else:
      if self.parent_evidence:
        return ':'.join((self.parent_evidence.name, self.partition_location))
      else:
        return ':'.join((self.type, self.partition_location))

  def _preprocess(self, _, required_states):
    # Late loading the partition processor to avoid loading dfVFS unnecessarily.
    from turbinia.processors import partitions

    # We need to enumerate partitions in preprocessing so the path_specs match
    # the parent evidence location for each task.
    try:
      # We should only get one path_spec here since we're specifying the location.
      path_specs = partitions.Enumerate(
          self.parent_evidence, self.partition_location)
    except TurbiniaException as exception:
      log.error(str(exception))

    if len(path_specs) > 1:
      path_specs_dicts = [path_spec.CopyToDict() for path_spec in path_specs]
      raise TurbiniaException(
          f'Found more than one path_spec for {self.parent_evidence.name} '
          f'{self.partition_location}: {path_specs_dicts}')
    elif len(path_specs) == 1:
      self.path_spec = path_specs[0]
      log.debugf(
          f'Found path_spec {self.path_spec.CopyToDict()} '
          f'for parent evidence {self.parent_evidence.name}')
    else:
      raise TurbiniaException(
          f'Could not find path_spec for location {self.partition_location:s}')

    # In attaching a partition, we create a new loopback device using the
    # partition offset and size.
    if interface.EvidenceState.ATTACHED in required_states or self.has_child_evidence:
      # Check for encryption
      encryption_type = partitions.GetPartitionEncryptionType(self.path_spec)
      if encryption_type == 'BDE':
        self.device_path = mount_local.PreprocessBitLocker(
            self.parent_evidence.device_path,
            partition_offset=self.partition_offset,
            credentials=self.parent_evidence.credentials)
        if not self.device_path:
          log.error('Could not decrypt partition.')
      else:
        self.device_path = mount_local.PreprocessLosetup(
            self.parent_evidence.device_path,
            partition_offset=self.partition_offset,
            partition_size=self.partition_size, lv_uuid=self.lv_uuid)
      if self.device_path:
        self.state[interface.EvidenceState.ATTACHED] = True
        self.local_path = self.device_path

    if interface.EvidenceState.MOUNTED in required_states or self.has_child_evidence:
      self.mount_path = mount_local.PreprocessMountPartition(
          self.device_path, self.path_spec.type_indicator)
      if self.mount_path:
        self.local_path = self.mount_path
        self.state[interface.EvidenceState.MOUNTED] = True

  def _postprocess(self):
    if self.state[interface.EvidenceState.MOUNTED]:
      mount_local.PostprocessUnmountPath(self.mount_path)
      self.state[interface.EvidenceState.MOUNTED] = False
    if self.state[interface.EvidenceState.ATTACHED]:
      # Late loading the partition processor to avoid loading dfVFS unnecessarily.
      from turbinia.processors import partitions

      # Check for encryption
      encryption_type = partitions.GetPartitionEncryptionType(self.path_spec)
      if encryption_type == 'BDE':
        # bdemount creates a virtual device named bde1 in the mount path. This
        # needs to be unmounted rather than detached.
        mount_local.PostprocessUnmountPath(self.device_path.replace('bde1', ''))
        self.state[interface.EvidenceState.ATTACHED] = False
      else:
        mount_local.PostprocessDeleteLosetup(self.device_path, self.lv_uuid)
        self.state[interface.EvidenceState.ATTACHED] = False
