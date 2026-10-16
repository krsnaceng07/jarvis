
import pytest

# Skip the whole test module if boto3 isn't available in this environment.
pytest.importorskip("boto3")


def test_create_aws_session_with_registry_creds(monkeypatch):
    import src.sessions.client_factory as cf

    # Mock resolve_credentials to return a common AWS shape
    monkeypatch.setattr(
        cf,
        "resolve_credentials",
        lambda provider, model: {
            "aws_access_key_id": "AKIA_TEST_KEY",
            "aws_secret_access_key": "TEST_SECRET",
            "aws_session_token": "TEST_TOKEN",
        },
    )

    sess = cf.create_aws_session(region="us-west-2", provider="amazon-bedrock")
    creds = sess.get_credentials()
    assert creds is not None
    assert creds.access_key == "AKIA_TEST_KEY"
    assert creds.secret_key == "TEST_SECRET"
    assert sess.region_name == "us-west-2"


def test_create_aws_client_falls_back_and_plugin_metadata(monkeypatch):
    import src.sessions.client_factory as cf

    # When registry returns None, create_aws_session should still return a Session
    monkeypatch.setattr(cf, "resolve_credentials", lambda provider, model: None)
    sess = cf.create_aws_session(region="eu-central-1", provider="amazon-bedrock")
    assert sess is not None

    # Patch create_aws_client to a simple marker so provider init can use it safely.
    import src.sessions.client_factory as client_factory_module

    monkeypatch.setattr(
        client_factory_module,
        "create_aws_client",
        lambda service, region=None, provider="amazon-bedrock": f"client-{service}-{region}",
    )

    # Import the provider module by path and call its init to attach metadata
    import importlib.util
    import sys
    from pathlib import Path

    plugin_path = Path("extensions/amazon-bedrock/plugin.py").resolve()
    spec = importlib.util.spec_from_file_location("extensions.amazon_bedrock.plugin", str(plugin_path))
    bedrock = importlib.util.module_from_spec(spec)
    sys.modules["extensions.amazon_bedrock.plugin"] = bedrock
    spec.loader.exec_module(bedrock)  # type: ignore

    # Ensure provider metadata is empty initially
    bedrock.amazon_bedrock_provider.metadata.clear()
    bedrock.amazon_bedrock_provider.init(ctx=None)

    assert "aws_client" in bedrock.amazon_bedrock_provider.metadata
    factory = bedrock.amazon_bedrock_provider.metadata["aws_client"]
    assert callable(factory)
    assert factory("s3", "ap-southeast-1") == "client-s3-ap-southeast-1"
