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
"""Task to run fsstat on disk partitions."""

import os

from turbinia.workers import TurbiniaTask
from turbinia.evidence import EvidenceState as state
from turbinia.evidence import ReportText


class FsstatTask(TurbiniaTask):
  """Task to run fsstat on an evidence object."""

  REQUIRED_STATES = [state.ATTACHED]

  def run(self, evidence, result):
    """Task to execute fsstat.

    Args:
        evidence (Evidence object):  The evidence we will process.
        result (TurbiniaTaskResult): The object to place task results into.

    Returns:
        TurbiniaTaskResult object.
    """
    fsstat_output = os.path.join(self.output_dir, 'fsstat.txt')

    if evidence.path_spec is None:
      message = 'Could not run fsstat since partition does not have a path_spec'
      result.log(message)
      result.close(self, success=False, status=message)
    # Since fsstat does not support some filesystems, we won't run it when we
    # know the partition is not supported.
    elif evidence.path_spec.type_indicator in ("APFS", "XFS"):
      message = 'Not processing since partition is not supported'
      result.log(message)
      result.close(self, success=True, status=message)
    else:
      output_evidence = ReportText(source_path=fsstat_output)
      cmd = ['sudo', 'fsstat', evidence.device_path]
      result.log(f'Running fsstat as [{cmd!s}]')
      self.execute(
          cmd, result, stdout_file=fsstat_output,
          new_evidence=[output_evidence], close=True)

    return result
