"""
    Turbinia API Server

    Turbinia API server  # noqa: E501

    The version of the OpenAPI document: 1.0.0
    Generated by: https://openapi-generator.tech
"""


import unittest

import turbinia_api_lib
from turbinia_api_lib.api.turbinia_tasks_api import TurbiniaTasksApi  # noqa: E501


class TestTurbiniaTasksApi(unittest.TestCase):
    """TurbiniaTasksApi unit test stubs"""

    def setUp(self):
        self.api = TurbiniaTasksApi()  # noqa: E501

    def tearDown(self):
        pass

    def test_get_task_status(self):
        """Test case for get_task_status

        Get Task Status  # noqa: E501
        """
        pass


if __name__ == '__main__':
    unittest.main()
