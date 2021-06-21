import boto3

c = boto3.client(
    "kafkaconnect",
    region_name="us-east-1",
    endpoint_url="https://kafkaconnect-beta.us-east-1.amazonaws.com/",
)

c.list_connectors()
