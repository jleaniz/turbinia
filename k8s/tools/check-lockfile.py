# This script tries to acquire a lock on the worker using
# a timeout equal to the maximum job timeout. It will return
# if a lock can be acquired or the lock process times out.
# It can be used in container orchestration setups (eg k8s)
# to make sure workers terminate gracefully.

import filelock
from turbinia import config


def main():
  config.LoadConfig()
  max_timeout = 0
  for values in config.DEPENDENCIES:
    timeout = values.get('timeout')
    if timeout > max_timeout:
      max_timeout = timeout
  config.log.info(f'Set max timeout: {max_timeout}')
  try:
    lock = filelock.FileLock(config.LOCK_FILE)
    with lock.acquire(timeout=max_timeout):
      config.log.info(f'Lock {config.LOCK_FILE} acquired')
      return
  except filelock.Timeout:
    config.log.info(f'Lock {config.LOCK_FILE} timed out')
    return


if __name__ == '__main__':
  main()
