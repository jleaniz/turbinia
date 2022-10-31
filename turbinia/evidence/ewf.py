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

#TODO implement support for several ewf devices if there are more than one
#inside the ewf_mount_path
class EwfDisk(interface.Evidence):
  """Evidence object for a EWF based evidence.

  Attributes:
    device_path (str): Path to a relevant 'raw' data source (ie: a block.
    ewf_path (str): Path to mounted EWF image.
    ewf_mount_path (str): Path to EWF mount directory.
  """
  REQUIRED_ATTRIBUTES = ['source_path', 'ewf_path', 'ewf_mount_path']
  POSSIBLE_STATES = [interface.EvidenceState.ATTACHED]

  def __init__(
      self, source_path=None, ewf_path=None, ewf_mount_path=None, *args,
      **kwargs):
    """Initialization for EWF evidence object."""
    super(EwfDisk, self).__init__(*args, **kwargs)
    self.source_path = source_path
    self.ewf_path = ewf_path
    self.ewf_mount_path = ewf_mount_path
    self.device_path = None

  def _preprocess(self, _, required_states):
    if interface.EvidenceState.ATTACHED in required_states or self.has_child_evidence:
      self.ewf_mount_path = mount_local.PreprocessMountEwfDisk(self.source_path)
      self.ewf_path = mount_local.GetEwfDiskPath(self.ewf_mount_path)
      self.device_path = self.ewf_path
      self.local_path = self.ewf_path
      self.state[interface.EvidenceState.ATTACHED] = True

  def _postprocess(self):
    if self.state[interface.EvidenceState.ATTACHED]:
      self.state[interface.EvidenceState.ATTACHED] = False
      mount_local.PostprocessUnmountPath(self.ewf_mount_path)
