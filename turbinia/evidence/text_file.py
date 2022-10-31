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


# TODO(aarontp): Find a way to integrate this into TurbiniaTaskResult instead.
class ReportText(interface.Evidence):
  """Text data for general reporting."""

  def __init__(self, text_data=None, *args, **kwargs):
    super(ReportText, self).__init__(copyable=True, *args, **kwargs)
    self.text_data = text_data


class FinalReport(ReportText):
  """Report format for the final complete Turbinia request report."""

  def __init__(self, *args, **kwargs):
    super(FinalReport, self).__init__(*args, **kwargs)
    self.save_metadata = True


class TextFile(interface.Evidence):
  """Text data."""

  def __init__(self, *args, **kwargs):
    super(TextFile, self).__init__(copyable=True, *args, **kwargs)


class FilteredTextFile(TextFile):
  """Filtered text data."""
  pass


class VolatilityReport(TextFile):
  """Volatility output file data."""
  pass
