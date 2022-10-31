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
"""Turbinia Manager pattern interface."""


class ManagerInterface:
  """Interface for manager pattern classes.

  This class is not an abstract interface and should be extended
  as needed for more specific manager classes (e.g. EvidenceManager).

  The existing class methods should not be modified unless the change
  is valid for all manager class implementations.
  """
  _registered_classes = {}

  @classmethod
  def Register(cls, class_object):
    class_name = class_object().type.lower()
    if class_name in cls._registered_classes:
      raise KeyError(f'Class already registered for name: {class_name}.')
    cls._registered_classes[class_name] = class_object

  @classmethod
  def Deregister(cls, class_object):
    class_name = class_object().type.lower()
    if class_name not in cls._registered_classes:
      raise KeyError(f'Class {class_name} is not registered.')
    del cls._registered_classes[class_name]

  @classmethod
  def DeregisterByName(cls, class_name):
    if class_name not in cls._registered_classes:
      raise KeyError(f'Class {class_name} is not registered.')
    del cls._registered_classes[class_name]

  @classmethod
  def GetRegisteredClasses(cls):
    for class_name, class_instance in iter(cls._registered_classes.items()):
      yield class_name, class_instance

  @classmethod
  def GetInstance(cls, class_name):
    class_name = class_name.lower()
    if class_name not in cls._registered_classes:
      raise KeyError(f'Class not registered for name: {class_name}.')
    class_instance = cls._registered_classes[class_name]
    return class_instance()

  @classmethod
  def GetInstances(cls, class_names):
    class_instances = []
    for class_name, class_instance in iter(cls.GetRegisteredClasses()):
      if class_names and class_name in class_names:
        class_instances.append(class_instance())
