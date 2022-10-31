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
from turbinia.lib.docker_manager import GetDockerPath
from turbinia.processors import containerd
from turbinia.processors import docker
from turbinia.processors import mount_local


class DockerContainer(interface.Evidence):
  """Evidence object for a DockerContainer filesystem.

  Attributes:
    container_id(str): The ID of the container to mount.
    _container_fs_path(str): Full path to where the container filesystem will
      be mounted.
    _docker_root_directory(str): Full path to the docker root directory.
  """

  REQUIRED_ATTRIBUTES = ['container_id']
  POSSIBLE_STATES = [interface.EvidenceState.CONTAINER_MOUNTED]

  def __init__(self, container_id=None, *args, **kwargs):
    """Initialization for Docker Container."""
    super(DockerContainer, self).__init__(*args, **kwargs)
    self.container_id = container_id
    self._container_fs_path = None
    self._docker_root_directory = None
    self.context_dependent = True

  @property
  def name(self):
    if self._name:
      return self._name
    else:
      if self.parent_evidence:
        return ':'.join((self.parent_evidence.name, self.container_id))
      else:
        return ':'.join((self.type, self.container_id))

  def _preprocess(self, _, required_states):
    if interface.EvidenceState.CONTAINER_MOUNTED in required_states:
      self._docker_root_directory = GetDockerPath(
          self.parent_evidence.mount_path)
      # Mounting the container's filesystem
      self._container_fs_path = docker.PreprocessMountDockerFS(
          self._docker_root_directory, self.container_id)
      self.mount_path = self._container_fs_path
      self.local_path = self.mount_path
      self.state[interface.EvidenceState.CONTAINER_MOUNTED] = True

  def _postprocess(self):
    if self.state[interface.EvidenceState.CONTAINER_MOUNTED]:
      # Unmount the container's filesystem
      mount_local.PostprocessUnmountPath(self._container_fs_path)
      self.state[interface.EvidenceState.CONTAINER_MOUNTED] = False


class ContainerdContainer(interface.Evidence):
  """Evidence object for a containerd evidence.

  Attributes:
    namespace (str): Namespace of the container to be mounted.
    container_id (str): ID of the container to be mounted.
    _image_path (str): Path where disk image is mounted.
    _container_fs_path (str): Path where containerd filesystem is mounted.
  """

  POSSIBLE_STATES = [interface.EvidenceState.CONTAINER_MOUNTED]

  def __init__(self, namespace=None, container_id=None, *args, **kwargs):
    """Initialization of containerd container."""
    super(ContainerdContainer, self).__init__(*args, **kwargs)
    self.namespace = namespace
    self.container_id = container_id
    self._image_path = None
    self._container_fs_path = None

    self.context_dependent = True

  @property
  def name(self):
    if self._name:
      return self._name

    if self.parent_evidence:
      return ':'.join((self.parent_evidence.name, self.container_id))
    else:
      return ':'.join((self.type, self.container_id))

  def _preprocess(self, _, required_states):
    if interface.EvidenceState.CONTAINER_MOUNTED in required_states:
      self._image_path = self.parent_evidence.mount_path

      # Mount containerd container
      self._container_fs_path = containerd.PreprocessMountContainerdFS(
          self._image_path, self.namespace, self.container_id)
      self.mount_path = self._container_fs_path
      self.local_path = self.mount_path
      self.state[interface.EvidenceState.CONTAINER_MOUNTED] = True

  def _postprocess(self):
    if self.state[interface.EvidenceState.CONTAINER_MOUNTED]:
      # Unmount the container
      mount_local.PostprocessUnmountPath(self._container_fs_path)
      self.state[interface.EvidenceState.CONTAINER_MOUNTED] = False
