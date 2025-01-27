# pylint: disable=W0621
import os
from pathlib import Path

import bentoml
import pytest

from bentoctl import deployment_config as dconf
from bentoctl.exceptions import DeploymentConfigNotFound, InvalidDeploymentConfig
from bentoctl.operator.operator import _import_module

from .conftest import TESTOP_PATH


def mock_bentoml_get(name):
    if "testservice" not in name:
        raise bentoml.exceptions.BentoMLException("not found!")
    else:
        return bentoml.Bento


def test_get_bento_path(tmpdir, monkeypatch):
    tmp_bento_path = os.path.join(tmpdir, "testbento")

    monkeypatch.setattr(bentoml, "get", mock_bentoml_get)
    with pytest.raises(InvalidDeploymentConfig):
        dconf.get_bento_path(tmp_bento_path)

    Path(tmp_bento_path).mkdir()
    Path(tmp_bento_path, "bento.yaml").touch()
    assert dconf.get_bento_path(tmp_bento_path) == tmp_bento_path


def assert_no_help_message_in_schema(schema):
    for _, rules in schema.items():
        assert "help_message" not in rules
        if rules["type"] == "dict":
            assert_no_help_message_in_schema(rules["schema"])
        elif rules["type"] == "list":
            assert_no_help_message_in_schema({"list_item": rules["schema"]})


def test_remove_help_message():
    operator_config = _import_module("operator_config", TESTOP_PATH)
    schema = operator_config.OPERATOR_SCHEMA
    schema_without_help_msg = dconf.remove_help_message(schema)
    assert_no_help_message_in_schema(schema_without_help_msg)


def test_deployment_config_init(op_reg, monkeypatch, tmpdir):
    # empty deployment_config
    with pytest.raises(InvalidDeploymentConfig):
        dconf.DeploymentConfig({})

    # deployment_config with incorrect api_version
    with pytest.raises(InvalidDeploymentConfig):
        dconf.DeploymentConfig({"api_version": "v1"})

    # deployment_config with no deployment name
    with pytest.raises(InvalidDeploymentConfig):
        dconf.DeploymentConfig({"api_version": "v1", "metadata": {}, "spec": {}})

    # deployment_config with operator that is not installed
    monkeypatch.setattr(dconf, "local_operator_registry", op_reg)
    with pytest.raises(InvalidDeploymentConfig):
        dconf.DeploymentConfig(
            {
                "api_version": "v1",
                "metadata": {"name": "test", "operator": "testop"},
                "spec": {},
            }
        )

    # valid bento
    op_reg.add(TESTOP_PATH)
    Path(tmpdir, "bento.yaml").touch()
    dconfigobj = dconf.DeploymentConfig(
        {
            "api_version": "v1",
            "metadata": {"name": "test", "operator": "testop"},
            "spec": {
                "bento": tmpdir,
                "instances": {"min": 1, "max": 2},
                "project_id": "test",
            },
        }
    )
    assert dconfigobj.bento == tmpdir
    assert dconfigobj.bento_path == tmpdir


VALID_YAML = """
api_version: v1
metadata:
    name: test
    operator: testop
spec:
    bento: {bento_path}
    project_id: testproject
    instances:
        min: 1
        max: 2
"""
INVALID_YAML = """
api_version: tst: something: something
"""
VALID_YAML_INVALID_SCHEMA = """
api_version: v1
metadata:
    name: test
    operator: testop
spec:
    bento: {bento_path}
    project_id: testproject
"""


def create_yaml_file(yml_str, path):
    with open(Path(path, "deployment_config.yaml"), "w", encoding="utf-8") as f:
        f.write(yml_str)


@pytest.fixture
def op_reg_with_testop(op_reg, monkeypatch):
    monkeypatch.setattr(dconf, "local_operator_registry", op_reg)
    op_reg.add(TESTOP_PATH)

    yield op_reg


@pytest.fixture
def tmp_bento_path(tmpdir):
    Path(tmpdir, "bento.yaml").touch()
    return tmpdir


def test_deployment_config_from_file(
    tmp_path, op_reg_with_testop, tmp_bento_path
):  # pylint: disable=W0613
    with pytest.raises(DeploymentConfigNotFound):
        dconf.DeploymentConfig.from_file(tmp_path / "nofile.yaml")

    create_yaml_file(INVALID_YAML, tmp_path)
    with pytest.raises(InvalidDeploymentConfig):
        dconf.DeploymentConfig.from_file(tmp_path / "deployment_config.yaml")

    create_yaml_file(VALID_YAML.format(bento_path=tmp_bento_path), tmp_path)
    assert dconf.DeploymentConfig.from_file(tmp_path / "deployment_config.yaml")


def test_validate_operator_config(
    op_reg_with_testop, tmp_bento_path
):  # pylint: disable=W0613
    import yaml

    dconf.DeploymentConfig(yaml.safe_load(VALID_YAML.format(bento_path=tmp_bento_path)))

    with pytest.raises(InvalidDeploymentConfig):
        dconf.DeploymentConfig(
            yaml.safe_load(VALID_YAML_INVALID_SCHEMA.format(bento_path=tmp_bento_path))
        )
