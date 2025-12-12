import datetime
import json
import time
import random
import string
import uuid
from copy import deepcopy

import numpy
from botocore.config import Config
from botocore.session import get_session
from tests import ClientHTTPStubber

session = get_session()
characters = string.ascii_letters + string.digits + string.punctuation
entries = []
num_tests = 500

#################### Helper Methods ####################

def get_random_string(str_len):
    return ''.join(random.choice(characters) for _ in range(str_len))

def get_list_of_random_strings(list_len, str_len):
    return [get_random_string(str_len) for _ in range(list_len)]

def get_metrics_for_call(operation, input, metrics, include_total_request_time=True):
    start_time = time.time()
    result = operation(**input)
    end_time = time.time()
    if include_total_request_time:
        metrics["Total request time (ms)"].append((end_time - start_time) * 1000)
    metrics["Serialization time (ms)"].append(result['ResponseMetadata']['SerializeTiming'] * 1000)
    metrics["Deserialization time (ms)"].append(result['ResponseMetadata']['DeserializeTiming'] * 1000)
    metrics["Request payload size (bytes)"].append(int(result['ResponseMetadata']['RequestPayloadSize']))
    metrics["Response payload size (bytes)"].append(int(result['ResponseMetadata']['ResponsePayloadSize']))

metrics_template = {
    "Total request time (ms)": [],
    "Serialization time (ms)": [],
    "Deserialization time (ms)": [],
    "Request payload size (bytes)": [],
    "Response payload size (bytes)": [],
}

#################### Local Service ####################

def complex_structure_test(start_timestamp, iteration):
    complex_struct = {
        'integerMember': random.randint(-9223372036854775808, 9223372036854775807),
        'longMember': random.randint(-9223372036854775808, 9223372036854775807),
        'stringMember': get_random_string(32),
        'complexStructMember': {
            'listOfStringsMember': get_list_of_random_strings(8, 32),
            'complexStructMember': {
                'mapOfStringToStringMember': {get_random_string(32): get_random_string(64) for _ in range(8)}
            }
        }
    }

    return "echo_operation", {
        'booleanMember': random.choice([True, False]),
        'blobMember': random.randbytes(128),
        'stringMember': get_random_string(32),
        'complexStructMember': complex_struct
    }, "Complex object"


def long_list_of_strings_test(start_timestamp, iteration):
    return "echo_operation", {"listOfStringsMember": get_list_of_random_strings(256, 64)}, "Long list of strings"

def all_types_test(start_timestamp, iteration):
    return "echo_operation", {
        'booleanMember': random.choice([True, False]),
        'stringMember': get_random_string(32),
        'integerMember': random.randint(-9223372036854775808, 9223372036854775807),
        'longMember': random.randint(-9223372036854775808, 9223372036854775807),
        'floatMember': random.uniform(-3.4e38, 3.4e38),
        'doubleMember': random.uniform(-1.7e308, 1.7e308),
        'timestampMember': start_timestamp,
        'blobMember': random.randbytes(128),
        "listOfStringsMember": get_list_of_random_strings(8, 32),
        'mapOfStringToStringMember': {
            get_random_string(32): get_random_string(64) for _ in  range(8)},
        'complexStructMember':  {
            'stringMember': get_random_string(32),
            'complexStructMember': {
                'stringMember': get_random_string(32),
            }
        }
    }, "All types"

def list_of_complex_objects_test(start_timestamp, iteration):
    return "echo_operation", {
        'listOfComplexObjectMember': [{
            'booleanMember': random.choice([True, False]),
            'blobMember': random.randbytes(128),
            'stringMember': get_random_string(32),
            'longMember': random.randint(-9223372036854775808, 9223372036854775807),
            'doubleMember': random.uniform(-9223372036854775808, 9223372036854775807),
            'listOfStringsMember': get_list_of_random_strings(8, 32),
            'timestampMember': start_timestamp
        } for _ in range(64)],
    }, "List of complex objects"

def large_blob_test(start_timestamp, iteration):
    return "echo_operation", {"blobMember": random.randbytes(262144)}, "Very large blob"

def run_echo_service_tests():
    echo_cbor = session.create_client('echo-cbor', region_name='us-west-2')
    echo_json = session.create_client('echo-json', region_name='us-west-2')
    tests = [long_list_of_strings_test, complex_structure_test, list_of_complex_objects_test,
             large_blob_test, all_types_test]
    metrics_template_without_total_req_time = {
        "Serialization time (ms)": [],
        "Deserialization time (ms)": [],
        "Request payload size (bytes)": [],
        "Response payload size (bytes)": [],
    }

    for test in tests:
        cbor_metrics = deepcopy(metrics_template_without_total_req_time)
        json_metrics = deepcopy(metrics_template_without_total_req_time)

        for i in range(num_tests):
            run_start_time = time.time()
            operation, input, test_name = test(run_start_time, i)
            for client, metrics, protocol in [(echo_cbor, cbor_metrics, 'cbor'), (echo_json, json_metrics, 'json')]:
                stubber = ClientHTTPStubber(client)
                with stubber:
                    op = getattr(client, operation)
                    get_metrics_for_call(op, input, metrics, include_total_request_time=False)

        for metrics, protocol in [(cbor_metrics, 'cbor'), (json_metrics, 'json')]:
            for metric_name, metric_values in metrics.items():
                entry = {
                    "service": "Local only",
                    "test-case": test_name,
                    "protocol": protocol,
                    "dimension_value": 0,
                    "metric": metric_name,
                    "p50": numpy.percentile(metric_values, 50).item(),
                    "p90": numpy.percentile(metric_values, 90).item(),
                    "max": max(metric_values),
                }
                entries.append(entry)

#################### Secrets Manager ####################

def create_secret(client, secret_name, value, tags):
    client.create_secret(
        Name=secret_name,
        SecretString=value,
        Description=f"The testing secret for run {secret_name.split('_')[-1]}",
        Tags=tags
    )

def run_secrets_manager_service_tests():
    config = Config(retries={'max_attempts': 0})
    sm_cbor = session.create_client('secretsmanager-cbor', config=config, region_name='us-west-2')
    sm_json = session.create_client('secretsmanager', config=config, region_name='us-west-2')
    run_start_time = time.time()

    # Create initial resources, no profiling necessary
    for i in range(num_tests):
        iteration = f"{i:0>3}"
        tags = [
            {"Key": "Stage", "Value": "Production"},
            {"Key": "Iteration", "Value": f"{iteration}"}
        ]
        string_secret_name = f"TestSecret_{run_start_time}_{iteration}"
        binary_secret_name = f"TestBinarySecret_{run_start_time}_{iteration}"
        create_secret(sm_cbor, string_secret_name, "A temporary secret value", tags)
        create_secret(sm_cbor, binary_secret_name, "A temporary secret value", tags)

    dimensions = [64, 512, 4096, 8192, 45056]
    test_metrics_results = {
        "Put string secret": {},
        "Put binary secret": {},
        "Get string secret": {},
        "Get binary secret": {},
        "Describe secret": {},
        "List secrets": {"cbor": {0: deepcopy(metrics_template)}, "json": {0: deepcopy(metrics_template)}},
    }
    for dimension in dimensions:
        for test_name in ["Put string secret", "Put binary secret", "Get string secret", "Get binary secret"]:
            if test_name not in test_metrics_results:
                test_metrics_results[test_name] = {}
            for protocol in ['cbor', 'json']:
                if protocol not in test_metrics_results[test_name]:
                    test_metrics_results[test_name][protocol] = {}
                test_metrics_results[test_name][protocol][dimension] = deepcopy(metrics_template)


    for dimension in dimensions:
        for i in range(num_tests):
            for client, protocol in [(sm_cbor, 'cbor'), (sm_json, 'json')]:
                iteration = f"{i:0>3}"
                string_secret_name = f"TestSecret_{run_start_time}_{iteration}"
                binary_secret_name = f"TestBinarySecret_{run_start_time}_{iteration}"

                get_metrics_for_call(
                    getattr(client, "put_secret_value"),
                    {
                        "SecretId": string_secret_name,
                        "SecretString": get_random_string(dimension)
                    },
                    test_metrics_results["Put string secret"][protocol][dimension]
                )
                get_metrics_for_call(
                    getattr(client, "put_secret_value"),
                    {
                        "SecretId": binary_secret_name,
                        "SecretBinary": random.randbytes(dimension)
                    },
                    test_metrics_results["Put binary secret"][protocol][dimension]
                )

        for i in range(num_tests):
            for client, protocol in [(sm_cbor, 'cbor'), (sm_json, 'json')]:
                iteration = f"{i:0>3}"
                string_secret_name = f"TestSecret_{run_start_time}_{iteration}"
                binary_secret_name = f"TestBinarySecret_{run_start_time}_{iteration}"

                get_metrics_for_call(
                    getattr(client, "get_secret_value"),
                    {
                        "SecretId": string_secret_name,
                    },
                    test_metrics_results["Get string secret"][protocol][dimension]
                )
                get_metrics_for_call(
                    getattr(client, "get_secret_value"),
                    {
                        "SecretId": binary_secret_name,
                    },
                    test_metrics_results["Get binary secret"][protocol][dimension]
                )

    for test_name in ["Describe secret", "List secrets"]:
        for protocol in ['cbor', 'json']:
            if test_name not in test_metrics_results:
                test_metrics_results[test_name] = {}
            if protocol not in test_metrics_results[test_name]:
                test_metrics_results[test_name][protocol] = {}
            if 0 not in test_metrics_results[test_name][protocol]:
                test_metrics_results[test_name][protocol][0] = deepcopy(metrics_template)

        for i in range(num_tests):
            for client, protocol in [(sm_cbor, 'cbor'), (sm_json, 'json')]:
                iteration = f"{i:0>3}"
                string_secret_name = f"TestSecret_{run_start_time}_{iteration}"
                get_metrics_for_call(
                    getattr(client, "describe_secret"),
                    {
                        "SecretId": string_secret_name,
                    },
                    test_metrics_results["Describe secret"][protocol][0]
                )
                get_metrics_for_call(
                    getattr(client, "list_secrets"),
                    {
                        "Filters": [
                            {
                                "Key": "tag-key",
                                "Values": ["Iteration"],
                            },
                            {
                                "Key": "tag-value",
                                "Values": [f"{iteration}"],
                            }
                        ]
                    },
                    test_metrics_results["List secrets"][protocol][0]
                )

    # Clean up resources
    for i in range(num_tests):
        iteration = f"{i:0>3}"
        string_secret_name = f"TestSecret_{run_start_time}_{iteration}"
        binary_secret_name = f"TestBinarySecret_{run_start_time}_{iteration}"
        sm_cbor.delete_secret(SecretId=string_secret_name)
        sm_cbor.delete_secret(SecretId=binary_secret_name)

    for test_name, test_dict in test_metrics_results.items():
        for protocol, protocol_dict in test_dict.items():
            for dimension, dimension_dict in protocol_dict.items():
                for metric_name, metric_values in dimension_dict.items():
                    entries.append({
                        "service": "Secrets Manager",
                        "test-case": test_name,
                        "protocol": protocol,
                        "dimension_value": dimension,
                        "metric": metric_name,
                        "p50": numpy.percentile(metric_values, 50).item(),
                        "p90": numpy.percentile(metric_values, 90).item(),
                        "max": max(metric_values),
                    })

#################### Cloudwatch ####################

def run_cloud_watch_service_tests():
    config = Config(retries={'max_attempts': 0},  disable_request_compression=True)
    cw_cbor = session.create_client('cloudwatch-cbor', config=config, region_name='us-west-2')
    cw_query = session.create_client('cloudwatch', config=config, region_name='us-west-2')
    run_start_time = time.time()
    metric_counts = [16, 64, 256, 1000]
    suite_id = uuid.uuid4()
    test_metrics_results = {
        "Put metric data": {},
        "Get metric data": {},
    }
    for dimension in metric_counts:
        for test_name in test_metrics_results.keys():
            if test_name not in test_metrics_results:
                test_metrics_results[test_name] = {}
            for protocol in ['cbor', 'query']:
                if protocol not in test_metrics_results[test_name]:
                    test_metrics_results[test_name][protocol] = {}
                test_metrics_results[test_name][protocol][dimension] = deepcopy(metrics_template)
    current_time_ms = int(round(time.time() * 1000))
    two_hours_ago_ms = current_time_ms - (2 * 60 * 60 * 1000)
    for dimension in metric_counts:
        for i in range(num_tests):
            if i % 25 == 0:
                time.sleep(2)
            for client, protocol in [(cw_cbor, 'cbor'), (cw_query, 'query')]:
                metric_data = []
                for j in range(dimension):
                    to_add = (2000 * (j + 1)) / 1000.0  #
                    metric_data.append(
                        {
                            "MetricName": "TestMetric",
                            "Dimensions": [
                                {
                                    "Name": "TestDimension",
                                    "Value": f"{suite_id}-{dimension}",
                                },
                            ],
                            "Value": random.random(),
                            "Unit": "None",
                            "Timestamp": datetime.datetime.fromtimestamp(
                                (two_hours_ago_ms + to_add) / 1000.0)  # Convert ms to seconds
                        },
                    )
                get_metrics_for_call(
                    getattr(client, "put_metric_data"),
                    {
                        "Namespace": "TestNamespace",
                        "MetricData": metric_data
                    },
                    test_metrics_results["Put metric data"][protocol][dimension]
                )
        start_time = datetime.datetime.fromtimestamp((two_hours_ago_ms) / 1000.0)
        end_time = start_time + datetime.timedelta(hours=1)
        for i in range(num_tests):
            if i % 25 == 0:
                time.sleep(2)
            for client, protocol in [(cw_cbor, 'cbor'), (cw_query, 'query')]:

                get_metrics_for_call(
                    getattr(client, "get_metric_data"),
                    {
                        "StartTime": start_time,
                        "EndTime": end_time,
                        "MetricDataQueries": [
                            {
                            "Id": "m0",
                            "ReturnData": True,
                            "MetricStat":
                                {
                                    "Unit": "None",
                                    "Stat": "Sum",
                                    "Metric": {
                                        "Namespace": "TestNamespace",
                                        "MetricName": "TestMetric",
                                        "Dimensions": [
                                            {
                                                "Name": "TestDimension",
                                                "Value": f"{suite_id}-{dimension}",
                                            }
                                        ],
                                    },
                                    "Period": 60
                                }
                            }
                        ]
                    },
                    test_metrics_results["Get metric data"][protocol][dimension]
                )

    test_name = "List metrics"
    test_metrics_results[test_name] = {}
    for protocol in ['cbor', 'query']:
        if protocol not in test_metrics_results[test_name]:
            test_metrics_results[test_name][protocol] = {}
            test_metrics_results[test_name][protocol][0] = deepcopy(metrics_template)


    for i in range(num_tests):
        if i % 25 == 0:
            time.sleep(2)
        for client, protocol in [(cw_cbor, 'cbor'), (cw_query, 'query')]:
            get_metrics_for_call(
                getattr(client, "list_metrics"),
                {
                    "Namespace": "TestNamespace",
                },
                test_metrics_results["List metrics"][protocol][0]
            )

    for test_name, test_dict in test_metrics_results.items():
        for protocol, protocol_dict in test_dict.items():
            for dimension, dimension_dict in protocol_dict.items():
                for metric_name, metric_values in dimension_dict.items():
                    entries.append({
                        "service": "CloudWatch",
                        "test-case": test_name,
                        "protocol": protocol,
                        "dimension_value": dimension,
                        "metric": metric_name,
                        "p50": numpy.percentile(metric_values, 50).item(),
                        "p90": numpy.percentile(metric_values, 90).item(),
                        "max": max(metric_values),
                    })


run_echo_service_tests()
print("echo service done")
# run_secrets_manager_service_tests()
# print("secrets manager done")
# run_cloud_watch_service_tests()
# print("cloudwatch done!")
with open('./python-cbor-perf-data-cleaned.json', 'w') as f:
    f.write(json.dumps(entries, indent=4))
