import base64
import datetime
import json
import mock
import unittest

import botocore
from botocore.awsrequest import AWSRequest
from botocore.compat import HAS_CRT, six

from tests import requires_crt
from tests.unit.auth.test_signers import (
    BasePresignTest,
    BaseTestWithFixedDate,
    TestS3SigV4Auth,
    TestSigV4Presign,
    TestSigV4Resign,
)


@requires_crt()
class TestCrtS3SigV4Auth(TestS3SigV4Auth):
    # Repeat TestS3SigV4Auth tests, but using CRT signer
    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtS3SigV4Auth


@requires_crt()
class TestCrtSigV4Resign(TestSigV4Resign):
    # Run same tests against CRT auth
    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtSigV4Auth


@requires_crt()
class TestCrtSigV4Presign(TestSigV4Presign):
    # Run same tests against CRT auth
    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtSigV4QueryAuth


@requires_crt()
class TestCrtS3SigV4AsymAuth(BaseTestWithFixedDate):

    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtS3SigV4AsymAuth

    def setUp(self):
        super().setUp()
        self.credentials = botocore.credentials.Credentials(
            access_key="foo", secret_key="bar", token="baz"
        )
        self.auth = self.AuthClass(self.credentials, "ec2", "eu-central-1")
        self.request = AWSRequest(data=six.BytesIO(b"foo bar baz"))
        self.request.method = "PUT"
        self.request.url = "https://s3.eu-central-1.amazonaws.com/"

        self.client_config = mock.Mock()
        self.s3_config = {}
        self.client_config.s3 = self.s3_config

        self.request.context = {"client_config": self.client_config}

    def test_signature_is_not_normalized(self):
        request = AWSRequest()
        request.url = "https://s3.amazonaws.com/bucket/foo/./bar/../bar"
        request.method = "GET"
        credentials = botocore.credentials.Credentials("access_key", "secret_key")
        auth = self.AuthClass(credentials, "s3", "us-east-1")
        auth.add_auth(request)
        self.assertTrue(
            request.headers["Authorization"].startswith(
                "AWS4-ECDSA-P256-SHA256 "
                "Credential=access_key/20140310/s3/aws4_request, "
                "SignedHeaders=host;x-amz-content-sha256;x-amz-date;x-amz-region-set, Signature="
            )
        )

    def test_query_string_params_in_urls(self):
        if not hasattr(self.AuthClass, "canonical_query_string"):
            raise unittest.SkipTest(
                "%s does not expose interim steps" % self.AuthClass.__name__
            )

        request = AWSRequest()
        request.url = (
            "https://s3.amazonaws.com/bucket?" "marker=%C3%A4%C3%B6%C3%BC-01.txt&prefix"
        )
        request.data = {"Action": "MyOperation"}
        request.method = "GET"

        # Check that the canonical query string is correct formatting
        # by ensuring that query string paramters that are added to the
        # canonical query string are correctly formatted.
        cqs = self.auth.canonical_query_string(request)
        self.assertEqual("marker=%C3%A4%C3%B6%C3%BC-01.txt&prefix=", cqs)

    def _test_blocklist_header(self, header, value):
        request = AWSRequest()
        request.url = "https://s3.amazonaws.com/bucket/foo"
        request.method = "PUT"
        request.headers[header] = value
        credentials = botocore.credentials.Credentials("access_key", "secret_key")
        auth = self.AuthClass(credentials, "s3", "us-east-1")
        auth.add_auth(request)
        self.assertNotIn(header, request.headers["Authorization"])

    def test_blocklist_expect_headers(self):
        self._test_blocklist_header("expect", "100-continue")

    def test_blocklist_trace_id(self):
        self._test_blocklist_header("x-amzn-trace-id", "Root=foo;Parent=bar;Sampleid=1")

    def test_blocklist_headers(self):
        self._test_blocklist_header("user-agent", "botocore/1.4.11")

    def test_uses_sha256_if_config_value_is_true(self):
        self.client_config.s3["payload_signing_enabled"] = True
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertNotEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_does_not_use_sha256_if_config_value_is_false(self):
        self.client_config.s3["payload_signing_enabled"] = False
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_uses_sha256_if_md5_unset(self):
        self.request.context["has_streaming_input"] = True
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertNotEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_uses_sha256_if_not_https(self):
        self.request.context["has_streaming_input"] = True
        self.request.headers.add_header("Content-MD5", "foo")
        self.request.url = "http://s3.amazonaws.com/bucket"
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertNotEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_uses_sha256_if_not_streaming_upload(self):
        self.request.context["has_streaming_input"] = False
        self.request.headers.add_header("Content-MD5", "foo")
        self.request.url = "https://s3.amazonaws.com/bucket"
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertNotEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_does_not_use_sha256_if_md5_set(self):
        self.request.context["has_streaming_input"] = True
        self.request.headers.add_header("Content-MD5", "foo")
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_does_not_use_sha256_if_context_config_set(self):
        self.request.context["payload_signing_enabled"] = False
        self.request.headers.add_header("Content-MD5", "foo")
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_sha256_if_context_set_on_http(self):
        self.request.context["payload_signing_enabled"] = False
        self.request.headers.add_header("Content-MD5", "foo")
        self.request.url = "http://s3.amazonaws.com/bucket"
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertNotEqual(sha_header, "UNSIGNED-PAYLOAD")

    def test_sha256_if_context_set_without_md5(self):
        self.request.context["payload_signing_enabled"] = False
        self.request.url = "https://s3.amazonaws.com/bucket"
        self.auth.add_auth(self.request)
        sha_header = self.request.headers["X-Amz-Content-SHA256"]
        self.assertNotEqual(sha_header, "UNSIGNED-PAYLOAD")

@requires_crt()
class TestCrtS3SigV4AsymPresign(BasePresignTest):

    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtS3SigV4AsymQueryAuth

    def setUp(self):
        self.access_key = "access_key"
        self.secret_key = "secret_key"
        self.credentials = botocore.credentials.Credentials(
            self.access_key, self.secret_key
        )
        self.service_name = "myservice"
        self.region_name = "myregion"
        self.auth = self.AuthClass(
            self.credentials, self.service_name, self.region_name, expires=60
        )
        self.datetime_patcher = mock.patch.object(
            botocore.auth.datetime, "datetime", mock.Mock(wraps=datetime.datetime)
        )
        mocked_datetime = self.datetime_patcher.start()
        mocked_datetime.utcnow.return_value = datetime.datetime(2014, 1, 1, 0, 0)

    def tearDown(self):
        self.datetime_patcher.stop()

    def test_presign_no_params(self):
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://ec2.us-east-1.amazonaws.com/"
        self.auth.add_auth(request)
        query_string = self.get_parsed_query_string(request)

        # Signature is non-deterministic so we won't compare
        del query_string["X-Amz-Signature"]

        self.assertEqual(
            query_string,
            {
                "X-Amz-Algorithm": "AWS4-ECDSA-P256-SHA256",
                "X-Amz-Credential": ("access_key/20140101/" "myservice/aws4_request"),
                "X-Amz-Date": "20140101T000000Z",
                "X-Amz-Expires": "60",
                "X-Amz-Region-Set": "myregion",
                "X-Amz-SignedHeaders": "host",
            },
        )

    def test_operation_params_before_auth_params(self):
        # The spec is picky about this.
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://ec2.us-east-1.amazonaws.com/?Action=MyOperation"
        self.auth.add_auth(request)
        # Verify auth params come after the existing params.
        self.assertIn("?Action=MyOperation&X-Amz", request.url)

    def test_operation_params_before_auth_params_in_body(self):
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://ec2.us-east-1.amazonaws.com/"
        request.data = {"Action": "MyOperation"}
        self.auth.add_auth(request)
        # Same situation, the params from request.data come before the auth
        # params in the query string.
        self.assertIn("?Action=MyOperation&X-Amz", request.url)

    def test_presign_with_spaces_in_param(self):
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://ec2.us-east-1.amazonaws.com/"
        request.data = {"Action": "MyOperation", "Description": "With Spaces"}
        self.auth.add_auth(request)
        # Verify we encode spaces as '%20, and we don't use '+'.
        self.assertIn("Description=With%20Spaces", request.url)

    def test_presign_with_empty_param_value(self):
        request = AWSRequest()
        request.method = "POST"
        # actual URL format for creating a multipart upload
        request.url = "https://s3.amazonaws.com/mybucket/mykey?uploads"
        self.auth.add_auth(request)
        # verify that uploads param is still in URL
        self.assertIn("uploads", request.url)

    def test_presign_with_security_token(self):
        self.credentials.token = "security-token"
        auth = botocore.crt.auth.CrtS3SigV4AsymQueryAuth(
            self.credentials, self.service_name, self.region_name, expires=60
        )
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://ec2.us-east-1.amazonaws.com/"
        auth.add_auth(request)
        query_string = self.get_parsed_query_string(request)
        self.assertEqual(query_string["X-Amz-Security-Token"], "security-token")

    def test_presign_where_body_is_json_bytes(self):
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://myservice.us-east-1.amazonaws.com/"
        request.data = b'{"Param": "value"}'
        self.auth.add_auth(request)
        query_string = self.get_parsed_query_string(request)

        # Signature is non-deterministic so we won't compare
        del query_string["X-Amz-Signature"]

        expected_query_string = {
            "X-Amz-Algorithm": "AWS4-ECDSA-P256-SHA256",
            "X-Amz-Credential": ("access_key/20140101/myservice/aws4_request"),
            "X-Amz-Expires": "60",
            "X-Amz-Region-Set": "myregion",
            "X-Amz-Date": "20140101T000000Z",
            "X-Amz-SignedHeaders": "host",
            "Param": "value",
        }
        self.assertEqual(query_string, expected_query_string)

    def test_presign_where_body_is_json_string(self):
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://myservice.us-east-1.amazonaws.com/"
        request.data = '{"Param": "value"}'
        self.auth.add_auth(request)
        query_string = self.get_parsed_query_string(request)

        # Signature is non-deterministic so we won't compare
        del query_string["X-Amz-Signature"]

        expected_query_string = {
            "X-Amz-Algorithm": "AWS4-ECDSA-P256-SHA256",
            "X-Amz-Credential": ("access_key/20140101/myservice/aws4_request"),
            "X-Amz-Expires": "60",
            "X-Amz-Date": "20140101T000000Z",
            "X-Amz-Region-Set": "myregion",
            "X-Amz-SignedHeaders": "host",
            "Param": "value",
        }
        self.assertEqual(query_string, expected_query_string)

    def test_presign_content_type_form_encoded_not_signed(self):
        request = AWSRequest()
        request.method = "GET"
        request.url = "https://myservice.us-east-1.amazonaws.com/"
        request.headers[
            "Content-Type"
        ] = "application/x-www-form-urlencoded; charset=utf-8"
        self.auth.add_auth(request)
        query_string = self.get_parsed_query_string(request)
        signed_headers = query_string.get("X-Amz-SignedHeaders")
        self.assertNotIn("content-type", signed_headers)
