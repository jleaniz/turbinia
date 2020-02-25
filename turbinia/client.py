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
"""Client objects for Turbinia."""

from __future__ import unicode_literals

from collections import defaultdict
from datetime import datetime
from datetime import timedelta

import json
import logging
from operator import itemgetter
from operator import attrgetter
import os
import stat
import time
import subprocess
import codecs

from turbinia import config
from turbinia.config import logger
from turbinia.config import DATETIME_FORMAT
from turbinia import task_manager
from turbinia import TurbiniaException
from turbinia.lib import text_formatter as fmt
from turbinia.lib import docker_manager
from turbinia.jobs import manager as job_manager
from turbinia.workers import Priority
from turbinia.workers.artifact import FileArtifactExtractionTask
from turbinia.workers.analysis.wordpress import WordpressAccessLogAnalysisTask
from turbinia.workers.analysis.jenkins import JenkinsAnalysisTask
from turbinia.workers.finalize_request import FinalizeRequestTask
from turbinia.workers.docker import DockerContainersEnumerationTask
from turbinia.workers.grep import GrepTask
from turbinia.workers.hadoop import HadoopAnalysisTask
from turbinia.workers.hindsight import HindsightTask
from turbinia.workers.plaso import PlasoTask
from turbinia.workers.psort import PsortTask
from turbinia.workers.sshd import SSHDAnalysisTask
from turbinia.workers.strings import StringsAsciiTask
from turbinia.workers.strings import StringsUnicodeTask
from turbinia.workers.tomcat import TomcatAnalysisTask
from turbinia.workers.volatility import VolatilityTask
from turbinia.workers.worker_stat import StatTask
from turbinia.workers.binary_extractor import BinaryExtractorTask
from turbinia.workers.bulk_extractor import BulkExtractorTask

# TODO(aarontp): Remove this map after
# https://github.com/google/turbinia/issues/278 is fixed.
TASK_MAP = {
    'fileartifactextractiontask': FileArtifactExtractionTask,
    'wordpressaccessloganalysistask': WordpressAccessLogAnalysisTask,
    'finalizerequesttask': FinalizeRequestTask,
    'jenkinsanalysistask': JenkinsAnalysisTask,
    'greptask': GrepTask,
    'hadoopanalysistask': HadoopAnalysisTask,
    'hindsighttask': HindsightTask,
    'plasotask': PlasoTask,
    'psorttask': PsortTask,
    'sshdanalysistask': SSHDAnalysisTask,
    'stringsasciitask': StringsAsciiTask,
    'stringsunicodetask': StringsUnicodeTask,
    'tomcatanalysistask': TomcatAnalysisTask,
    'volatilitytask': VolatilityTask,
    'stattask': StatTask,
    'binaryextractor': BinaryExtractorTask,
    'bulkextractortask': BulkExtractorTask,
    'dockertask': DockerContainersEnumerationTask
}

config.LoadConfig()
if config.TASK_MANAGER.lower() == 'psq':
  import psq

  from google.cloud import exceptions
  from google.cloud import datastore
  from google.cloud import pubsub

  from turbinia.lib.google_cloud import GoogleCloudFunction
elif config.TASK_MANAGER.lower() == 'celery':
  from turbinia.state_manager import RedisStateManager

log = logging.getLogger('turbinia')
logger.setup()


def get_turbinia_client(run_local=False):
  """Return Turbinia client based on config.

  Returns:
    Initialized BaseTurbiniaClient or TurbiniaCeleryClient object.
  """
  config.LoadConfig()
  # pylint: disable=no-else-return
  if config.TASK_MANAGER.lower() == 'psq':
    return BaseTurbiniaClient(run_local=run_local)
  elif config.TASK_MANAGER.lower() == 'celery':
    return TurbiniaCeleryClient(run_local=run_local)
  else:
    msg = 'Task Manager type "{0:s}" not implemented'.format(
        config.TASK_MANAGER)
    raise TurbiniaException(msg)


def check_docker_dependencies(dependencies):
  """Checks docker dependencies.

  Args:
    dependencies(dict): dictionary of dependencies to check for.

  Raises:
    TurbiniaException: If dependency is not met.
  """
  #TODO(wyassine): may run into issues down the line when a docker image
  # does not have bash or which installed. (no linux fs layer).
  log.info('Performing docker dependency check.')
  job_names = list(job_manager.JobsManager.GetJobNames())
  images = docker_manager.DockerManager().list_images(return_filter='short_id')

  # Iterate through list of jobs
  for job, values in dependencies.items():
    if job not in job_names:
      log.warning(
          'The job {0:s} was not found or has been disabled. Skipping '
          'dependency check...'.format(job))
      continue
    elif values.get('docker_image') in images:
      for program in values['programs']:
        cmd = 'type {0:s}'.format(program)
        stdout, stderr, ret = docker_manager.ContainerManager(
            values['docker_image']).execute_container(cmd, shell=True)
        if ret != 0:
          raise TurbiniaException(
              'Job dependency {0:s} not found for job {1:s}. Please install '
              'the dependency for the container or disable the job.'.format(
                  program, job))
      job_manager.JobsManager.RegisterDockerImage(job, values['docker_image'])
    elif values.get('docker_image'):
      raise TurbiniaException(
          'Docker image {0:s} was not found for the job {1:s}. Please '
          'update the config with the correct image id'.format(
              values['docker_image'], job))


def check_system_dependencies(dependencies):
  """Checks system dependencies.

  Args:
    dependencies(dict): dictionary of dependencies to check for.

  Raises:
    TurbiniaException: If dependency is not met.
  """
  log.info('Performing system dependency check.')
  job_names = list(job_manager.JobsManager.GetJobNames())

  # Iterate through list of jobs
  for job, values in dependencies.items():
    if job not in job_names:
      log.warning(
          'The job {0:s} was not found or has been disabled. Skipping '
          'dependency check...'.format(job))
      continue
    elif not values.get('docker_image'):
      for program in values['programs']:
        cmd = 'type {0:s}'.format(program)
        proc = subprocess.Popen(cmd, shell=True)
        proc.communicate()
        ret = proc.returncode
        if ret != 0:
          raise TurbiniaException(
              'Job dependency {0:s} not found in $PATH for the job {1:s}. '
              'Please install the dependency or disable the job.'.format(
                  program, job))


def check_directory(directory):
  """Checks directory to make sure it exists and is writable.

  Args:
    directory (string): Path to directory

  Raises:
    TurbiniaException: When directory cannot be created or used.
  """
  if os.path.exists(directory) and not os.path.isdir(directory):
    raise TurbiniaException(
        'File {0:s} exists, but is not a directory'.format(directory))

  if not os.path.exists(directory):
    try:
      os.makedirs(directory)
    except OSError:
      raise TurbiniaException(
          'Can not create Directory {0:s}'.format(directory))

  if not os.access(directory, os.W_OK):
    try:
      mode = os.stat(directory)[0]
      os.chmod(directory, mode | stat.S_IWUSR)
    except OSError:
      raise TurbiniaException(
          'Can not add write permissions to {0:s}'.format(directory))


class TurbiniaStats(object):
  """Statistics for Turbinia task execution.

  Attributes:
    count(int): The number of tasks
    min(datetime.timedelta): The minimum run time of all tasks
    max(datetime.timedelta): The maximum run time of all tasks
    mean(datetime.timedelta): The mean run time of all tasks
    tasks(list): A list of tasks to calculate stats for
  """

  def __init__(self, description=None):
    self.description = description
    self.min = None
    self.mean = None
    self.max = None
    self.tasks = []

  def __str__(self):
    return self.format_stats()

  @property
  def count(self):
    """Gets a count of the tasks in this stats object.

    Returns:
      Int of task count.
    """
    return len(self.tasks)

  def add_task(self, task):
    """Add a task result dict.

    Args:
      task(dict): The task results we want to count stats for.
    """
    self.tasks.append(task)

  def calculate_stats(self):
    """Calculates statistics of the current tasks."""
    if not self.tasks:
      return

    sorted_tasks = sorted(self.tasks, key=itemgetter('run_time'))
    self.min = sorted_tasks[0]['run_time']
    self.max = sorted_tasks[len(sorted_tasks) - 1]['run_time']
    self.mean = sorted_tasks[len(sorted_tasks) // 2]['run_time']

    # Remove the microseconds to keep things cleaner
    self.min = self.min - timedelta(microseconds=self.min.microseconds)
    self.max = self.max - timedelta(microseconds=self.max.microseconds)
    self.mean = self.mean - timedelta(microseconds=self.mean.microseconds)

  def format_stats(self):
    """Formats statistics data.

    Returns:
      String of statistics data
    """
    return '{0:s}: Count: {1:d}, Min: {2!s}, Mean: {3!s}, Max: {4!s}'.format(
        self.description, self.count, self.min, self.mean, self.max)

  def format_stats_csv(self):
    """Formats statistics data into CSV output.

    Returns:
      String of statistics data in CSV format
    """
    return '{0:s}, {1:d}, {2!s}, {3!s}, {4!s}'.format(
        self.description, self.count, self.min, self.mean, self.max)


class BaseTurbiniaClient(object):
  """Client class for Turbinia.

  Attributes:
    task_manager (TaskManager): Turbinia task manager
  """

  def __init__(self, run_local=False):
    config.LoadConfig()
    if run_local:
      self.task_manager = None
    else:
      self.task_manager = task_manager.get_task_manager()
      self.task_manager.setup(server=False)

  def create_task(self, task_name):
    """Creates a Turbinia Task by name.

    Args:
      task_name(string): Name of the Task we are going to run.

    Returns:
      TurbiniaTask: An instantiated Task object.

    Raises:
      TurbiniaException: When no Task object matching task_name is found.
    """
    task_obj = TASK_MAP.get(task_name.lower())
    log.debug('Looking up Task {0:s} by name'.format(task_name))
    if not task_obj:
      raise TurbiniaException('No Task named {0:s} found'.format(task_name))
    return task_obj()

  def list_jobs(self):
    """List the available jobs."""
    # TODO(aarontp): Refactor this out so that we don't need to depend on
    # the task manager from the client.
    log.info('Available Jobs:')
    for job in self.task_manager.jobs:
      log.info('\t{0:s}'.format(job.NAME))

  def wait_for_request(
      self, instance, project, region, request_id=None, user=None,
      poll_interval=60):
    """Polls and waits for Turbinia Request to complete.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      project (string): The name of the project.
      region (string): The name of the region to execute in.
      request_id (string): The Id of the request we want tasks for.
      user (string): The user of the request we want tasks for.
      poll_interval (int): Interval of seconds between polling cycles.
    """
    last_completed_count = -1
    last_uncompleted_count = -1
    while True:
      task_results = self.get_task_data(
          instance, project, region, request_id=request_id, user=user)
      completed_tasks = []
      uncompleted_tasks = []
      for task in task_results:
        if task.get('successful') is not None:
          completed_tasks.append(task)
        else:
          uncompleted_tasks.append(task)

      if completed_tasks and len(completed_tasks) == len(task_results):
        break

      completed_names = [t.get('name') for t in completed_tasks]
      completed_names = ', '.join(sorted(completed_names))
      uncompleted_names = [t.get('name') for t in uncompleted_tasks]
      uncompleted_names = ', '.join(sorted(uncompleted_names))
      total_count = len(completed_tasks) + len(uncompleted_tasks)
      msg = (
          'Tasks completed ({0:d}/{1:d}): [{2:s}], waiting for [{3:s}].'.format(
              len(completed_tasks), total_count, completed_names,
              uncompleted_names))
      if (len(completed_tasks) > last_completed_count or
          len(uncompleted_tasks) > last_uncompleted_count):
        log.info(msg)
      else:
        log.debug(msg)

      last_completed_count = len(completed_tasks)
      last_uncompleted_count = len(uncompleted_tasks)
      time.sleep(poll_interval)

    log.info('All {0:d} Tasks completed'.format(len(task_results)))

  def get_task_data(
      self, instance, project, region, days=0, task_id=None, request_id=None,
      user=None, function_name='gettasks'):
    """Gets task data from Google Cloud Functions.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      project (string): The name of the project.
      region (string): The name of the region to execute in.
      days (int): The number of days we want history for.
      task_id (string): The Id of the task.
      request_id (string): The Id of the request we want tasks for.
      user (string): The user of the request we want tasks for.
      function_name (string): The GCF function we want to call

    Returns:
      List of Task dict objects.
    """
    cloud_function = GoogleCloudFunction(project_id=project, region=region)
    func_args = {'instance': instance, 'kind': 'TurbiniaTask'}

    if days:
      start_time = datetime.now() - timedelta(days=days)
      # Format this like '1990-01-01T00:00:00z' so we can cast it directly to a
      # javascript Date() object in the cloud function.
      start_string = start_time.strftime(DATETIME_FORMAT)
      func_args.update({'start_time': start_string})
    elif task_id:
      func_args.update({'task_id': task_id})
    elif request_id:
      func_args.update({'request_id': request_id})

    if user:
      func_args.update({'user': user})

    response = cloud_function.ExecuteFunction(function_name, func_args)
    if 'result' not in response:
      log.error('No results found')
      if response.get('error', '{}') != '{}':
        msg = 'Error executing Cloud Function: [{0!s}].'.format(
            response.get('error'))
        log.error(msg)
      log.debug('GCF response: {0!s}'.format(response))
      raise TurbiniaException(
          'Cloud Function {0:s} returned no results.'.format(function_name))

    try:
      results = json.loads(response['result'])
    except (TypeError, ValueError) as e:
      raise TurbiniaException(
          'Could not deserialize result [{0!s}] from GCF: [{1!s}]'.format(
              response.get('result'), e))

    # Convert run_time/last_update back into datetime objects
    task_data = results[0]
    for task in task_data:
      if task.get('run_time'):
        task['run_time'] = timedelta(seconds=task['run_time'])
      if task.get('last_update'):
        task['last_update'] = datetime.strptime(
            task['last_update'], DATETIME_FORMAT)

    return task_data

  def format_task_detail(self, task, show_files=False):
    """Formats a single task in detail.

    Args:
      task (dict): The task to format data for
      show_files (bool): Whether we want to print out log file paths

    Returns:
      list: Formatted task data
    """
    report = []
    saved_paths = task.get('saved_paths') or []
    status = task.get('status') or 'No task status'

    report.append(fmt.heading2(task.get('name')))
    line = '{0:s} {1:s}'.format(fmt.bold('Status:'), status)
    report.append(fmt.bullet(line))
    report.append(fmt.bullet('Task Id: {0:s}'.format(task.get('id'))))
    report.append(
        fmt.bullet('Executed on worker {0:s}'.format(task.get('worker_name'))))
    if task.get('report_data'):
      report.append('')
      report.append(fmt.heading3('Task Reported Data'))
      report.extend(task.get('report_data').splitlines())
    if show_files:
      report.append('')
      report.append(fmt.heading3('Saved Task Files:'))
      for path in saved_paths:
        report.append(fmt.bullet(fmt.code(path)))
      report.append('')
    return report

  def format_task(self, task, show_files=False):
    """Formats a single task in short form.

    Args:
      task (dict): The task to format data for
      show_files (bool): Whether we want to print out log file paths

    Returns:
      list: Formatted task data
    """
    report = []
    saved_paths = task.get('saved_paths') or []
    status = task.get('status') or 'No task status'
    report.append(fmt.bullet('{0:s}: {1:s}'.format(task.get('name'), status)))
    if show_files:
      for path in saved_paths:
        report.append(fmt.bullet(fmt.code(path), level=2))
      report.append('')
    return report

  def get_task_statistics(
      self, instance, project, region, days=0, task_id=None, request_id=None,
      user=None):
    """Gathers statistics for Turbinia execution data.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      project (string): The name of the project.
      region (string): The name of the zone to execute in.
      days (int): The number of days we want history for.
      task_id (string): The Id of the task.
      request_id (string): The Id of the request we want tasks for.
      user (string): The user of the request we want tasks for.

    Returns:
      task_stats(dict): Mapping of statistic names to values
    """
    task_results = self.get_task_data(
        instance, project, region, days, task_id, request_id, user)
    if not task_results:
      return {}

    task_stats = {
        'all_tasks': TurbiniaStats('All Tasks'),
        'successful_tasks': TurbiniaStats('Successful Tasks'),
        'failed_tasks': TurbiniaStats('Failed Tasks'),
        'requests': TurbiniaStats('Total Request Time'),
        # The following are dicts mapping the user/worker/type names to their
        # respective TurbiniaStats() objects.
        # Total wall-time for all tasks of a given type
        'tasks_per_type': {},
        # Total wall-time for all tasks per Worker
        'tasks_per_worker': {},
        # Total wall-time for all tasks per User
        'tasks_per_user': {},
    }

    # map of request ids to [min time, max time]
    requests = {}

    for task in task_results:
      request_id = task.get('request_id')
      task_type = task.get('name')
      worker = task.get('worker_name')
      user = task.get('requester')
      if not task.get('run_time'):
        log.debug(
            'Ignoring task {0:s} in statistics because the run_time is not '
            'set, and it is required to calculate stats'.format(
                task.get('name')))
        continue

      # Stats for all/successful/failed tasks
      task_stats['all_tasks'].add_task(task)
      if task.get('successful') is True:
        task_stats['successful_tasks'].add_task(task)
      elif task.get('successful') is False:
        task_stats['failed_tasks'].add_task(task)

      # Stats for Tasks per Task type.
      if task_type in task_stats['tasks_per_type']:
        task_type_stats = task_stats['tasks_per_type'].get(task_type)
      else:
        task_type_stats = TurbiniaStats('Task type {0:s}'.format(task_type))
        task_stats['tasks_per_type'][task_type] = task_type_stats
      task_type_stats.add_task(task)

      # Stats per worker.
      if worker in task_stats['tasks_per_worker']:
        worker_stats = task_stats['tasks_per_worker'].get(worker)
      else:
        worker_stats = TurbiniaStats('Worker {0:s}'.format(worker))
        task_stats['tasks_per_worker'][worker] = worker_stats
      worker_stats.add_task(task)

      # Stats per submitting User.
      if user in task_stats['tasks_per_user']:
        user_stats = task_stats['tasks_per_user'].get(user)
      else:
        user_stats = TurbiniaStats('User {0:s}'.format(user))
        task_stats['tasks_per_user'][user] = user_stats
      user_stats.add_task(task)

      # Stats for the total request.  This will, for each request, calculate the
      # start time of the earliest task and the stop time of the latest task.
      # This will give the overall run time covering all tasks in the request.
      task_start_time = task['last_update'] - task['run_time']
      task_stop_time = task['last_update']
      if request_id in requests:
        start_time, stop_time = requests[request_id]
        if task_start_time < start_time:
          requests[request_id][0] = task_start_time
        if task_stop_time > stop_time:
          requests[request_id][1] = task_stop_time
      else:
        requests[request_id] = [task_start_time, task_stop_time]

    # Add a fake task result for each request with our calculated times to the
    # stats module
    for min_time, max_time in requests.values():
      task = {}
      task['run_time'] = max_time - min_time
      task_stats['requests'].add_task(task)

    # Go over all stat objects and calculate them
    for stat_obj in task_stats.values():
      if isinstance(stat_obj, dict):
        for inner_stat_obj in stat_obj.values():
          inner_stat_obj.calculate_stats()
      else:
        stat_obj.calculate_stats()

    return task_stats

  def format_task_statistics(
      self, instance, project, region, days=0, task_id=None, request_id=None,
      user=None, csv=False):
    """Formats statistics for Turbinia execution data.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      project (string): The name of the project.
      region (string): The name of the zone to execute in.
      days (int): The number of days we want history for.
      task_id (string): The Id of the task.
      request_id (string): The Id of the request we want tasks for.
      user (string): The user of the request we want tasks for.
      csv (bool): Whether we want the output in CSV format.

    Returns:
      String of task statistics report
    """
    task_stats = self.get_task_statistics(
        instance, project, region, days, task_id, request_id, user)
    if not task_stats:
      return 'No tasks found'

    stats_order = [
        'all_tasks', 'successful_tasks', 'failed_tasks', 'requests',
        'tasks_per_type', 'tasks_per_worker', 'tasks_per_user'
    ]

    if csv:
      report = ['stat_type, count, min, mean, max']
    else:
      report = ['Execution time statistics for Turbinia:', '']
    for stat_name in stats_order:
      stat_obj = task_stats[stat_name]
      if isinstance(stat_obj, dict):
        # Sort by description so that we get consistent report output
        inner_stat_objs = sorted(
            stat_obj.values(), key=attrgetter('description'))
        for inner_stat_obj in inner_stat_objs:
          if csv:
            report.append(inner_stat_obj.format_stats_csv())
          else:
            report.append(inner_stat_obj.format_stats())
      else:
        if csv:
          report.append(stat_obj.format_stats_csv())
        else:
          report.append(stat_obj.format_stats())

    report.append('')
    return '\n'.join(report)

  def format_task_status(
      self, instance, project, region, days=0, task_id=None, request_id=None,
      user=None, all_fields=False, full_report=False,
      priority_filter=Priority.HIGH):
    """Formats the recent history for Turbinia Tasks.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      project (string): The name of the project.
      region (string): The name of the zone to execute in.
      days (int): The number of days we want history for.
      task_id (string): The Id of the task.
      request_id (string): The Id of the request we want tasks for.
      user (string): The user of the request we want tasks for.
      all_fields (bool): Include all fields for the task, including task,
          request ids and saved file paths.
      full_report (bool): Generate a full markdown report instead of just a
          summary.
      priority_filter (int): Output only a summary for Tasks with a value
          greater than the priority_filter.

    Returns:
      String of task status
    """
    task_results = self.get_task_data(
        instance, project, region, days, task_id, request_id, user)
    if not task_results:
      return ''
    # Sort all tasks by the report_priority so that tasks with a higher
    # priority are listed first in the report.
    for result in task_results:
      # 0 is a valid value, so checking against specific values
      if result.get('report_priority') in (None, ''):
        result['report_priority'] = Priority.LOW
    task_results = sorted(task_results, key=itemgetter('report_priority'))
    num_results = len(task_results)
    if not num_results:
      msg = 'No Turbinia Tasks found.'
      log.info(msg)
      return '\n{0:s}'.format(msg)

    # Build up data
    report = []
    requester = task_results[0].get('requester')
    request_id = task_results[0].get('request_id')
    success_types = ['Successful', 'Failed', 'Scheduled or Running']
    success_values = [True, False, None]
    # Reverse mapping values to types
    success_map = dict(zip(success_values, success_types))
    task_map = defaultdict(list)
    success_types.insert(0, 'High Priority')
    for task in task_results:
      if task.get('report_priority') <= priority_filter:
        task_map['High Priority'].append(task)
      else:
        task_map[success_map[task.get('successful')]].append(task)

    # Generate report header
    report.append('\n')
    report.append(fmt.heading1('Turbinia report {0:s}'.format(request_id)))
    report.append(
        fmt.bullet(
            'Processed {0:d} Tasks for user {1:s}'.format(
                num_results, requester)))

    # Print report data for tasks
    for success_type in success_types:
      report.append('')
      report.append(fmt.heading1('{0:s} Tasks'.format(success_type)))
      if not task_map[success_type]:
        report.append(fmt.bullet('None'))
      for task in task_map[success_type]:
        if full_report and success_type == success_types[0]:
          report.extend(self.format_task_detail(task, show_files=all_fields))
        else:
          report.extend(self.format_task(task, show_files=all_fields))

    return '\n'.join(report)

  def run_local_task(self, task_name, request):
    """Runs a Turbinia Task locally.

    Args:
      task_name(string): Name of the Task we are going to run.
      request (TurbiniaRequest): Object containing request and evidence info.

    Returns:
      TurbiniaTaskResult: The result returned by the Task Execution.
    """
    task = self.create_task(task_name)
    task.request_id = request.request_id
    task.base_output_dir = config.OUTPUT_DIR
    task.run_local = True
    if not request.evidence:
      raise TurbiniaException('TurbiniaRequest does not contain evidence.')
    log.info('Running Task {0:s} locally'.format(task_name))
    result = task.run_wrapper(request.evidence[0])
    return result

  def send_request(self, request):
    """Sends a TurbiniaRequest message.

    Args:
      request: A TurbiniaRequest object.
    """
    self.task_manager.server_pubsub.send_request(request)

  def close_tasks(
      self, instance, project, region, request_id=None, task_id=None, user=None,
      requester=None):
    """Close Turbinia Tasks based on Request ID.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      project (string): The name of the project.
      region (string): The name of the zone to execute in.
      request_id (string): The Id of the request we want tasks for.
      task_id (string): The Id of the request we want task for.
      user (string): The user of the request we want tasks for.
      requester (string): The user making the request to close tasks.

    Returns: String of closed Task IDs.
    """
    cloud_function = GoogleCloudFunction(project_id=project, region=region)
    func_args = {
        'instance': instance,
        'kind': 'TurbiniaTask',
        'request_id': request_id,
        'task_id': task_id,
        'user': user,
        'requester': requester
    }
    response = cloud_function.ExecuteFunction('closetasks', func_args)
    return 'Closed Task IDs: %s' % response.get('result')


class TurbiniaCeleryClient(BaseTurbiniaClient):
  """Client class for Turbinia (Celery).

  Overriding some things specific to Celery operation.

  Attributes:
    redis (RedisStateManager): Redis datastore object
  """

  def __init__(self, *args, **kwargs):
    super(TurbiniaCeleryClient, self).__init__(*args, **kwargs)
    self.redis = RedisStateManager()

  def send_request(self, request):
    """Sends a TurbiniaRequest message.

    Args:
      request: A TurbiniaRequest object.
    """
    self.task_manager.kombu.send_request(request)

  # pylint: disable=arguments-differ
  def get_task_data(
      self, instance, _, __, days=0, task_id=None, request_id=None,
      function_name=None):
    """Gets task data from Redis.

    We keep the same function signature, but ignore arguments passed for GCP.

    Args:
      instance (string): The Turbinia instance name (by default the same as the
          INSTANCE_ID in the config).
      days (int): The number of days we want history for.
      task_id (string): The Id of the task.
      request_id (string): The Id of the request we want tasks for.

    Returns:
      List of Task dict objects.
    """
    return self.redis.get_task_data(instance, days, task_id, request_id)


class TurbiniaServer(object):
  """Turbinia Server class.

  Attributes:
    task_manager (TaskManager): An object to manage turbinia tasks.
  """

  def __init__(self, jobs_blacklist=None, jobs_whitelist=None):
    """Initializes Turbinia Server.

    Args:
      jobs_blacklist (Optional[list[str]]): Jobs we will exclude from running
      jobs_whitelist (Optional[list[str]]): The only Jobs we will include to run
    """
    config.LoadConfig()
    self.task_manager = task_manager.get_task_manager()
    self.task_manager.setup(jobs_blacklist, jobs_whitelist)

  def start(self):
    """Start Turbinia Server."""
    log.info('Running Turbinia Server.')
    self.task_manager.run()

  def add_evidence(self, evidence_):
    """Add evidence to be processed."""
    self.task_manager.add_evidence(evidence_)


class TurbiniaCeleryWorker(BaseTurbiniaClient):
  """Turbinia Celery Worker class.

  Attributes:
    worker (celery.app): Celery worker app
  """

  def __init__(self, jobs_blacklist=None, jobs_whitelist=None):
    """Initialization for celery worker.

    Args:
      jobs_blacklist (Optional[list[str]]): Jobs we will exclude from running
      jobs_whitelist (Optional[list[str]]): The only Jobs we will include to run
    """
    super(TurbiniaCeleryWorker, self).__init__()
    # Deregister jobs from blacklist/whitelist.
    disabled_jobs = list(config.DISABLED_JOBS) if config.DISABLED_JOBS else []
    job_manager.JobsManager.DeregisterJobs(jobs_blacklist, jobs_whitelist)
    if disabled_jobs:
      log.info(
          'Disabling jobs that were configured to be disabled in the '
          'config file: {0:s}'.format(', '.join(disabled_jobs)))
      job_manager.JobsManager.DeregisterJobs(jobs_blacklist=disabled_jobs)

    # Check for valid dependencies/directories.
    dependencies = config.ParseDependencies()
    if config.DOCKER_ENABLED:
      check_docker_dependencies(dependencies)
    check_system_dependencies(config.DEPENDENCIES)
    check_directory(config.MOUNT_DIR_PREFIX)
    check_directory(config.OUTPUT_DIR)
    check_directory(config.TMP_DIR)

    jobs = job_manager.JobsManager.GetJobNames()
    log.info(
        'Dependency check complete. The following jobs will be enabled '
        'for this worker: {0:s}'.format(','.join(jobs)))
    self.worker = self.task_manager.celery.app

  def start(self):
    """Start Turbinia Celery Worker."""
    log.info('Running Turbinia Celery Worker.')
    self.worker.task(task_manager.task_runner, name='task_runner')
    argv = ['celery', 'worker', '--loglevel=info', '--pool=solo']
    self.worker.start(argv)


class TurbiniaPsqWorker(object):
  """Turbinia PSQ Worker class.

  Attributes:
    worker (psq.Worker): PSQ Worker object
    psq (psq.Queue): A Task queue object

  Raises:
    TurbiniaException: When errors occur
  """

  def __init__(self, jobs_blacklist=None, jobs_whitelist=None):
    """Initialization for PSQ Worker.

    Args:
      jobs_blacklist (Optional[list[str]]): Jobs we will exclude from running
      jobs_whitelist (Optional[list[str]]): The only Jobs we will include to run
    """
    config.LoadConfig()
    psq_publisher = pubsub.PublisherClient()
    psq_subscriber = pubsub.SubscriberClient()
    datastore_client = datastore.Client(project=config.TURBINIA_PROJECT)
    try:
      self.psq = psq.Queue(
          psq_publisher, psq_subscriber, config.TURBINIA_PROJECT,
          name=config.PSQ_TOPIC, storage=psq.DatastoreStorage(datastore_client))
    except exceptions.GoogleCloudError as e:
      msg = 'Error creating PSQ Queue: {0:s}'.format(str(e))
      log.error(msg)
      raise TurbiniaException(msg)

    # Deregister jobs from blacklist/whitelist.
    disabled_jobs = list(config.DISABLED_JOBS) if config.DISABLED_JOBS else []
    job_manager.JobsManager.DeregisterJobs(jobs_blacklist, jobs_whitelist)
    if disabled_jobs:
      log.info(
          'Disabling jobs that were configured to be disabled in the '
          'config file: {0:s}'.format(', '.join(disabled_jobs)))
      job_manager.JobsManager.DeregisterJobs(jobs_blacklist=disabled_jobs)

    # Check for valid dependencies/directories.
    dependencies = config.ParseDependencies()
    if config.DOCKER_ENABLED:
      check_docker_dependencies(dependencies)
    check_system_dependencies(dependencies)
    check_directory(config.MOUNT_DIR_PREFIX)
    check_directory(config.OUTPUT_DIR)
    check_directory(config.TMP_DIR)

    jobs = job_manager.JobsManager.GetJobNames()
    log.info(
        'Dependency check complete. The following jobs will be enabled '
        'for this worker: {0:s}'.format(','.join(jobs)))
    log.info('Starting PSQ listener on queue {0:s}'.format(self.psq.name))
    self.worker = psq.Worker(queue=self.psq)

  def start(self):
    """Start Turbinia PSQ Worker."""
    log.info('Running Turbinia PSQ Worker.')
    self.worker.listen()
