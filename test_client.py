# test_client.py
import boto3
import requests
import json
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

def call_function_url(query, model=None):
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    
    url = "https://gbdg5nx6eda2vvzekbp4uakxea0ygnct.lambda-url.us-east-2.on.aws/"
    payload = {"query": query}
    if model:
        payload["model"] = model
    
    request = AWSRequest(
        method="POST",
        url=url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"}
    )
    SigV4Auth(credentials, "lambda", "us-east-2").add_auth(request)
    
    prepared = request.prepare()
    response = requests.request(
        prepared.method, prepared.url,
        headers=prepared.headers, data=prepared.body, timeout=30
    )
    return response.json()

if __name__ == "__main__":
    result = call_function_url("Hello, how are you?")
    print(json.dumps(result, indent=2))