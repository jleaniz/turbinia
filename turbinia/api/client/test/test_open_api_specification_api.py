"""
    Turbinia API Server

    Turbinia API server  # noqa: E501

    The version of the OpenAPI document: 1.0.0
    Generated by: https://openapi-generator.tech
"""


import unittest

import turbinia_api_client
from turbinia_api_client.api.open_api_specification_api import OpenAPISpecificationApi  # noqa: E501


class TestOpenAPISpecificationApi(unittest.TestCase):
    """OpenAPISpecificationApi unit test stubs"""

    def setUp(self):
        self.api = OpenAPISpecificationApi()  # noqa: E501

    def tearDown(self):
        pass

    def test_read_openapi_yaml(self):
        """Test case for read_openapi_yaml

        Read Openapi Yaml  # noqa: E501
        """
        pass


if __name__ == '__main__':
    unittest.main()
