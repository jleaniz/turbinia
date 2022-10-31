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

from turbinia.evidence import interface
from turbinia.processors import mount_local


class RawDisk(interface.Evidence):
  """Evidence object for Disk based evidence.

  Attributes:
    source_path (str): Path to a relevant 'raw' data source (ie: a block
        device or a raw disk image).
    mount_partition: The mount partition for this disk (if any).
  """
  REQUIRED_ATTRIBUTES = ['source_path']
  POSSIBLE_STATES = [interface.EvidenceState.ATTACHED]

  def __init__(self, source_path=None, *args, **kwargs):
    """Initialization for raw disk evidence object."""
    super(RawDisk, self).__init__(source_path=source_path, *args, **kwargs)
    self.device_path = None

  def _preprocess(self, _, required_states):
    if self.size is None:
      self.size = mount_local.GetDiskSize(self.source_path)
    if interface.EvidenceState.ATTACHED in required_states or self.has_child_evidence:
      self.device_path = mount_local.PreprocessLosetup(self.source_path)
      self.state[interface.EvidenceState.ATTACHED] = True
      self.local_path = self.device_path

  def _postprocess(self):
    if self.state[interface.EvidenceState.ATTACHED]:
      mount_local.PostprocessDeleteLosetup(self.device_path)
      self.state[interface.EvidenceState.ATTACHED] = False