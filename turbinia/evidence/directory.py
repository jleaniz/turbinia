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
from turbinia.processors import archive


class Directory(interface.Evidence):
  """Filesystem directory evidence.

  Attributes:
    source_path: The path to the source directory used as evidence.
  """
  REQUIRED_ATTRIBUTES = ['source_path']

  def __init__(self, source_path=None, *args, **kwargs):
    super(Directory, self).__init__(source_path=source_path, *args, **kwargs)
    self.source_path = source_path


class CompressedDirectory(interface.Evidence):
  """CompressedDirectory based evidence.

  Attributes:
    compressed_directory: The path to the compressed directory.
    uncompressed_directory: The path to the uncompressed directory.
  """
  REQUIRED_ATTRIBUTES = ['source_path']
  POSSIBLE_STATES = [interface.EvidenceState.DECOMPRESSED]

  def __init__(self, source_path=None, *args, **kwargs):
    """Initialization for CompressedDirectory evidence object."""
    super(CompressedDirectory, self).__init__(
        source_path=source_path, *args, **kwargs)
    self.compressed_directory = None
    self.uncompressed_directory = None
    self.copyable = True

  def _preprocess(self, tmp_dir, required_states):
    # Uncompress a given tar file and return the uncompressed path.
    if interface.EvidenceState.DECOMPRESSED in required_states:
      self.uncompressed_directory = archive.UncompressTarFile(
          self.local_path, tmp_dir)
      self.local_path = self.uncompressed_directory
      self.state[interface.EvidenceState.DECOMPRESSED] = True

  def compress(self):
    """ Compresses a file or directory.

    Creates a tar.gz from the uncompressed_directory attribute.
    """
    # Compress a given directory and return the compressed path.
    self.compressed_directory = archive.CompressDirectory(
        self.uncompressed_directory)
    self.source_path = self.compressed_directory
    self.state[interface.EvidenceState.DECOMPRESSED] = False


class BinaryExtraction(CompressedDirectory):
  """Binaries extracted from evidence."""
  pass

class BulkExtractorOutput(CompressedDirectory):
  """Bulk Extractor based evidence."""
  pass


class PhotorecOutput(CompressedDirectory):
  """Photorec based evidence."""
  pass
