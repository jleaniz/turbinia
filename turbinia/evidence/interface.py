# -*- coding: utf-8 -*-
# Copyright 2017 Google Inc.
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
"""Turbinia Evidence objects."""

from enum import IntEnum
from collections import defaultdict

import json
import logging
import sys
import inspect
import filelock

from turbinia import config
from turbinia import TurbiniaException
from turbinia import manager_interface
from turbinia.processors import resource_manager

log = logging.getLogger('turbinia')


class EvidenceManager(manager_interface.ManagerInterface):
  """The evidence manager."""

  @classmethod
  def evidence_class_names(cls, all_classes=False):
    """Returns a list of class names for the evidence module.

    Args:
      all_classes (bool): Flag to determine whether to include all classes
          in the module.

    Returns:
      class_names (list[str]): A list of class names within the Evidence module,
          minus the ignored class names.
    """

    def is_module(member):
      return inspect.ismodule(member) and not inspect.isbuiltin(member)

    def is_class(member):
      return inspect.isclass(member) and not inspect.isbuiltin(member)

    module_names = inspect.getmembers(sys.modules[__name__], is_module)
    class_names = []
    for module_name, _ in module_names:
      for class_name in inspect.getmembers(sys.modules[__name__ + module_name],
                                           is_class):
        class_names.append(class_name)

    if not all_classes:
      # TODO: Non-evidence types should be moved out of the evidence module,
      # so that we no longer have to ignore certain classes here. Especially
      # 'output' and 'report' types.
      # Ignore classes that are not real Evidence types and the base class.
      ignored_classes = (
          'BinaryExtraction', 'BulkExtractorOutput', 'Evidence',
          'EvidenceState', 'EvidenceCollection', 'EvidenceManager',
          'defaultdict', 'ExportedFileArtifact', 'FilteredTextFile',
          'FinalReport', 'IntEnum', 'PlasoCsvFile', 'PlasoFile',
          'PhotorecOutput', 'ReportText', 'TextFile', 'VolatilityReport',
          'TurbiniaException')
      class_names = filter(
          lambda class_tuple: class_tuple[0] not in ignored_classes,
          class_names)
    return list(class_names)

  @classmethod
  def map_evidence_attributes(cls):
    """Creates a dictionary that maps evidence types to their
        constructor attributes.

    Returns:
      object_attribute_mapping (defaultdict): A mapping of evidence types
          and their constructor attributes.
    """
    object_attribute_mapping = defaultdict(list)
    for class_name, class_type in cls.evidence_class_names():
      try:
        attributes_signature = inspect.signature(class_type)
        attributes = attributes_signature.parameters.keys()
        for attribute in attributes:
          if not object_attribute_mapping[class_name]:
            object_attribute_mapping[class_name] = defaultdict(dict)
          # Ignore 'args' and 'kwargs' attributes.
          if attribute not in ('args', 'kwargs'):
            object_attribute_mapping[class_name][attribute] = {
                'required': bool(attribute in class_type.REQUIRED_ATTRIBUTES),
                'type': 'str'
            }
        # Add optional attributes.
        for optional_attribute in Evidence.OPTIONAL_ATTRIBUTES:
          object_attribute_mapping[class_name][optional_attribute] = {
              'required': False,
              'type': 'str'
          }
      except ValueError as exception:
        log.info(exception)
    return object_attribute_mapping

  @classmethod
  def evidence_decode(cls, evidence_dict, strict=False):
    """Decode JSON into appropriate Evidence object.

    Args:
      evidence_dict: JSON serializable evidence object (i.e. a dict post JSON
                    decoding).
      strict: Flag to indicate whether strict attribute validation will occur.
          Defaults to False.

    Returns:
      An instantiated Evidence object (or a sub-class of it) or None.

    Raises:
      TurbiniaException: If input is not a dict, does not have a type attribute,
                        or does not deserialize to an evidence object.
    """
    if not isinstance(evidence_dict, dict):
      raise TurbiniaException(
          f'Evidence_dict is not a dictionary, type is {str(type(evidence_dict)):s}'
      )

    type_ = evidence_dict.pop('type', None)
    if not type_:
      raise TurbiniaException(
          f'No Type attribute for evidence object [{str(evidence_dict):s}]')
    evidence = None
    try:
      evidence_class = getattr(sys.modules[__name__], type_)
      evidence = evidence_class.from_dict(evidence_dict)
      evidence_object = evidence_class(source_path='dummy_object')
      if strict and evidence_object:
        for attribute_key in evidence_dict.keys():
          if not attribute_key in evidence_object.__dict__:
            message = f'Invalid attribute {attribute_key!s} for evidence type {type_:s}'
            log.error(message)
            raise TurbiniaException(message)
      if evidence:
        if evidence_dict.get('parent_evidence'):
          evidence.parent_evidence = cls.evidence_decode(
              evidence_dict['parent_evidence'])
        if evidence_dict.get('collection'):
          evidence.collection = [
              cls.evidence_decode(e) for e in evidence_dict['collection']
          ]
        # We can just reinitialize instead of deserializing because the
        # state should be empty when just starting to process on a new machine.
        evidence.state = {}
        for state in EvidenceState:
          evidence.state[state] = False
    except AttributeError:
      message = f'No Evidence object of type {type_!s} in evidence module'
      log.error(message)
      raise TurbiniaException(message) from AttributeError

    return evidence


class EvidenceState(IntEnum):
  """Runtime state of Evidence.

  Evidence objects will map each of these to a boolean indicating the current
  state for the given object.
  """
  MOUNTED = 1
  ATTACHED = 2
  DECOMPRESSED = 3
  CONTAINER_MOUNTED = 4


class Evidence:
  """Evidence object for processing.

  In most cases, these objects will just contain metadata about the actual
  evidence.

  Attributes:
    config (dict): Configuration options from the request to be used when
        processing this evidence.  Tasks should not read from this property
        directly, but should use `Task.task_config` to access any recipe or
        configuration variables.
    cloud_only (bool): Set to True for evidence types that can only be processed
        in a cloud environment, e.g. GoogleCloudDisk.
    context_dependent (bool): Whether this evidence is required to be built upon
        the context of a parent evidence.
    copyable (bool): Whether this evidence can be copied.  This will be set to
        True for object types that we want to copy to/from storage (e.g.
        PlasoFile, but not RawDisk).
    name (str): Name of evidence.
    description (str): Description of evidence.
    size (int): The evidence size in bytes where available (Used for metric
        tracking).
    saved_path (str): Path to secondary location evidence is saved for later
        retrieval (e.g. GCS).
    saved_path_type (str): The name of the output writer that saved evidence
        to the saved_path location.
    source (str): String indicating where evidence came from (including tool
        version that created it, if appropriate).
    local_path (str): Generic path to the evidence data after pre-processing
        has been run.  This is the path that most Tasks and any code that runs
        after the pre-processors should use to access evidence. Depending on
        the pre-processors and `REQUIRED_STATE` for the Task being run, this
        could point to a blockdevice or a mounted directory. The last
        pre-processor to run should always set this path. For example if the
        Evidence is a `RawDisk`, the `source_path` will be a path to the image
        file, then the pre-processors will (optionally, depending on the Task
        requirements) create a loop device and mount it which will set the
        `device_path` and `mount_path` respectively. After that, the
        `local_path` should point to whatever path the last pre-processor has
        created, in this case the mount_path.
    source_path (str): Path to the original un-processed source data for the
        Evidence.  This is the path that Evidence should be created and set up
        with initially and used any time prior to when the pre-processors run.
        Tasks should generally not use `source_path`, but instead use the
        `local_path` (or other more specific paths like `device_path` or
        `mount_path` depending on the Task requirements).
    mount_path (str): Path to a mounted file system (if relevant).
    credentials (list): Decryption keys for encrypted evidence.
    tags (dict): Extra tags associated with this evidence.
    request_id (str): The id of the request this evidence came from, if any.
    has_child_evidence (bool): This property indicates the evidence object has
        child evidence.
    parent_evidence (Evidence): The Evidence object that was used to generate
        this one, and which pre/post process methods we need to re-execute to
        access data relevant to us.
    save_metadata (bool): Evidence with this property set will save a metadata
        file alongside the Evidence when saving to external storage.  The
        metadata file will contain all of the key=value pairs sent along with
        the processing request in the recipe.  The output is in JSON format
    state (dict): A map of each interface.EvidenceState type to a boolean to indicate
        if that state is true.  This is used by the preprocessors to set the
        current state and Tasks can use this to determine if the Evidence is in
        the correct state for processing.
    resource_tracked (bool): Evidence with this property set requires tracking
        in a state file to allow for access amongst multiple workers.
    resource_id (str): The unique id used to track the state of a given Evidence
        type for stateful tracking.
  """

  # The list of attributes a given piece of Evidence requires to be set
  REQUIRED_ATTRIBUTES = []

  # An optional set of attributes that are generally used to describe
  # a given piece of Evidence.
  OPTIONAL_ATTRIBUTES = {'name', 'source', 'description', 'tags'}

  # The list of interface.EvidenceState states that the Evidence supports in its
  # pre/post-processing (e.g. MOUNTED, ATTACHED, etc).  See `preprocessor()`
  # docstrings for more info.
  POSSIBLE_STATES = []

  def __init__(
      self, name=None, description=None, size=None, source=None,
      source_path=None, tags=None, request_id=None, copyable=False):
    """Initialization for Evidence."""
    self.copyable = copyable
    self.config = {}
    self.context_dependent = False
    self.cloud_only = False
    self.description = description
    self.size = size
    self.mount_path = None
    self.credentials = []
    self.source = source
    self.source_path = source_path
    self.tags = tags if tags else {}
    self.request_id = request_id
    self.has_child_evidence = False
    self.parent_evidence = None
    self.save_metadata = False
    self.resource_tracked = False
    self.resource_id = None

    self.local_path = source_path

    # List of jobs that have processed this evidence
    self.processed_by = []
    self.type = self.__class__.__name__
    self._name = name
    self.saved_path = None
    self.saved_path_type = None

    self.state = {}
    for state in EvidenceState:
      self.state[state] = False

    if self.copyable and not self.local_path:
      raise TurbiniaException(
          f'Unable to initialize object, {self.type} is a copyable '
          f'evidence and needs a source_path')

    # TODO: Validating for required attributes breaks some units tests.
    # Github issue: https://github.com/google/turbinia/issues/1136
    # self.validate()

  def __str__(self):
    return f'{self.type}:{self.name}:{self.source_path}'

  def __repr__(self):
    return self.__str__()

  @property
  def name(self):
    """Returns evidence object name."""
    if self._name:
      return self._name
    else:
      return self.source_path if self.source_path else self.type

  @name.setter
  def name(self, value):
    self._name = value

  @name.deleter
  def name(self):
    del self._name

  @classmethod
  def from_dict(cls, dictionary):
    """Instantiate an Evidence object from a dictionary of attributes.

    Args:
      dictionary(dict): the attributes to set for this object.
    Returns:
      Evidence: the instantiated evidence.
    """
    name = dictionary.pop('name', None)
    description = dictionary.pop('description', None)
    size = dictionary.pop('size', None)
    source = dictionary.pop('source', None)
    source_path = dictionary.pop('source_path', None)
    tags = dictionary.pop('tags', None)
    request_id = dictionary.pop('request_id', None)
    new_object = cls(
        name=name, description=description, size=size, source=source,
        source_path=source_path, tags=tags, request_id=request_id)
    new_object.__dict__.update(dictionary)
    return new_object

  def serialize(self):
    """Return JSON serializable object."""
    # Clear any partition path_specs before serializing
    if hasattr(self, 'path_spec'):
      self.path_spec = None
    serialized_evidence = self.__dict__.copy()
    if self.parent_evidence:
      serialized_evidence['parent_evidence'] = self.parent_evidence.serialize()
    return serialized_evidence

  def to_json(self):
    """Convert object to JSON.

    Returns:
      A JSON serialized string of the current object.

    Raises:
      TurbiniaException: If serialization error occurs.
    """
    try:
      serialized = json.dumps(self.serialize())
    except TypeError as exception:
      msg = f'JSON serialization of evidence object {self.type} failed: {exception}'
      raise TurbiniaException(msg) from exception

    return serialized

  def set_parent(self, parent_evidence):
    """Set the parent evidence of this evidence.

    Also adds this evidence as a child of the parent.

    Args:
      parent_evidence(Evidence): The parent evidence object.
    """
    parent_evidence.has_child_evidence = True
    self.parent_evidence = parent_evidence

  def _preprocess(self, _, required_states):
    """Preprocess this evidence prior to task running.

    See `preprocess()` docstrings for more info.

    Args:
      tmp_dir(str): The path to the temporary directory that the
          Task will write to.
      required_states(list[interface.EvidenceState]): The list of evidence state
          requirements from the Task.
    """
    pass

  def _postprocess(self):
    """Postprocess this evidence after the task runs.

    This gets run in the context of the local task execution on the worker
    nodes after the task has finished.  This can be used to clean-up after the
    evidence is processed (e.g. detach a cloud disk, etc,).
    """
    pass

  def preprocess(self, task_id, tmp_dir=None, required_states=None):
    """Runs the possible parent's evidence preprocessing code, then ours.

    This is a wrapper function that will call the chain of pre-processors
    starting with the most distant ancestor.  After all of the ancestors have
    been processed, then we run our pre-processor.  These processors get run in
    the context of the local task execution on the worker nodes prior to the
    task itself running.  This can be used to prepare the evidence to be
    processed (e.g. attach a cloud disk, mount a local disk etc).

    Tasks export a list of the required_states they have for the state of the
    Evidence it can process in `TurbiniaTask.REQUIRED_STATES`[1].  Evidence also
    exports a list of the possible states it can have after pre/post-processing
    in `Evidence.POSSIBLE_STATES`.  The pre-processors should run selectively
    based on the these requirements that come from the Task, and the
    post-processors should run selectively based on the current state of the
    Evidence.

    If a Task requires a given state supported by the given Evidence class, but
    it is not met after the preprocessing of the Evidence is run, then the Task
    will abort early.  Note that for compound evidence types that have parent
    Evidence objects (e.g. where `context_dependent` is True), we only inspect
    the child Evidence type for its state as it is assumed that it would only be
    able to run the appropriate pre/post-processors when the parent Evidence
    processors have been successful.

    [1] Note that the evidence states required by the Task are only required if
    the Evidence also supports that state in `POSSSIBLE_STATES`.  This is so
    that the Tasks are flexible enough to support multiple types of Evidence.
    For example, `PlasoParserTask` allows both `CompressedDirectory` and
    `GoogleCloudDisk` as Evidence input, and has states `ATTACHED` and
    `DECOMPRESSED` listed in `PlasoParserTask.REQUIRED_STATES`.  Since `ATTACHED`
    state is supported by `GoogleCloudDisk`, and `DECOMPRESSED` is supported by
    `CompressedDirectory`, only those respective pre-processors will be run and
    the state is confirmed after the preprocessing is complete.

    Args:
      task_id(str): The id of a given Task.
      tmp_dir(str): The path to the temporary directory that the
                       Task will write to.
      required_states(list[interface.EvidenceState]): The list of evidence state
          requirements from the Task.

    Raises:
      TurbiniaException: If the required evidence state cannot be met by the
          possible states of the Evidence or if the parent evidence object does
          not exist when it is required by the Evidence type..
    """
    self.local_path = self.source_path
    if not required_states:
      required_states = []

    if self.context_dependent:
      if not self.parent_evidence:
        raise TurbiniaException(
            f'Evidence of type {self.type} needs parent_evidence to be set')
      self.parent_evidence.preprocess(task_id, tmp_dir, required_states)
    try:
      log.debugf('Starting pre-processor for evidence {name:s}', name=self.name)
      if self.resource_tracked:
        # Track resource and task id in state file
        with filelock.FileLock(config.RESOURCE_FILE_LOCK):
          resource_manager.PreprocessResourceState(self.resource_id, task_id)
      self._preprocess(tmp_dir, required_states)
    except TurbiniaException as exception:
      log.errorf(f'Error running preprocessor for {self.name:s}: {exception!s}')

    log.debugf(
        'Pre-processing evidence {self.name} is complete, and evidence is in state '
        '{self.format_state()}')

  def postprocess(self, task_id):
    """Runs our postprocessing code, then our possible parent's evidence.

    This is is a wrapper function that will run our post-processor, and will
    then recurse down the chain of parent Evidence and run those post-processors
    in order.

    Args:
      task_id(str): The id of a given Task.
    """
    log.infof(f'Starting post-processor for evidence {self.name:s}')
    log.debugf(f'Evidence state: {self.format_state():s}')

    is_detachable = True
    if self.resource_tracked:
      with filelock.FileLock(config.RESOURCE_FILE_LOCK):
        # Run postprocess to either remove task_id or resource_id.
        is_detachable = resource_manager.PostProcessResourceState(
            self.resource_id, task_id)
        if not is_detachable:
          # Prevent from running post process code if there are other tasks running.
          log.infof(
              f'Resource ID {self.resource_id} still in use. Skipping detaching Evidence...'
          )
        else:
          self._postprocess()
          # Set to False to prevent postprocess from running twice.
          is_detachable = False

    if is_detachable:
      self._postprocess()
    if self.parent_evidence:
      self.parent_evidence.postprocess(task_id)

  def format_state(self):
    """Returns a string representing the current state of evidence.

    Returns:
      str:  The state as a formatted string
    """
    output = []
    for state, value in self.state.items():
      output.append(f'{state.name:s}: {value!s}')
    return f"[{', '.join(output):s}]"

  def validate(self):
    """Runs validation to verify evidence meets minimum requirements.

    This default implementation will just check that the attributes listed in
    REQUIRED_ATTRIBUTES are set, but other evidence types can override this
    method to implement their own more stringent checks as needed.  This is
    called by the worker, prior to the pre/post-processors running.

    Raises:
      TurbiniaException: If validation fails
    """
    for attribute in self.REQUIRED_ATTRIBUTES:
      attribute_value = getattr(self, attribute, None)
      if not attribute_value:
        message = (
            f'Evidence validation failed: Required attribute {attribute} for class '
            f'{self.type} is not set. Please check original request.')
        raise TurbiniaException(message)


class EvidenceCollection:
  """A Collection of Evidence objects.

  Attributes:
    collection(list[Evidence]): The underlying Evidence objects
  """

  def __init__(self, collection=None):
    """Initialization for Evidence Collection object."""
    # This statement will avoid serialization errors if collection
    # is not a list.
    if collection and not isinstance(collection, list):
      raise TurbiniaException(
          f'An unexpected collection attribute was provided. '
          f'Expected a list, but got {type(collection)}')
    self.collection = collection if collection else []

  def serialize(self):
    """Return JSON serializable object."""
    serialized_evidence = [e.serialize() for e in self.collection]
    return serialized_evidence

  def add_evidence(self, evidence):
    """Adds evidence to the collection.

    Args:
      evidence (Evidence): The evidence to add.
    """
    self.collection.append(evidence)
