from pathlib import Path

import pytest
import yaml

from deploy.serve import render_config

ROOT=Path(__file__).resolve().parents[1]


def test_staging_exposes_only_ingress_and_keeps_state_ephemeral_nonprivileged():
    config=yaml.safe_load((ROOT/'compose.staging.yaml').read_text())
    assert set(config['services'])=={'demo'}
    service=config['services']['demo']
    assert service['build']['target']=='portfolio'
    assert service['read_only'] and not service.get('volumes')
    assert service['cap_drop']==['ALL'] and service['security_opt']==['no-new-privileges:true']
    assert service['pids_limit']<=128 and service['mem_limit']=='1536m'
    assert len(service['ports'])==1 and service['ports'][0].startswith('127.0.0.1:')
    assert service['environment']['CASHGUARD_INFERENCE_PROVIDER']=='deterministic'
    assert service['environment']['CASHGUARD_PUBLIC_DEMO']=='true'


def test_render_template_has_no_automatic_deployment_or_operational_service():
    config=yaml.safe_load((ROOT/'render.yaml').read_text())
    assert len(config['services'])==1
    service=config['services'][0]
    assert service['autoDeployTrigger']=='off' and service['numInstances']==1
    assert service['healthCheckPath']=='/ready' and not service.get('disk')
    variables={item['key']:item for item in service['envVars']}
    assert variables['CASHGUARD_API_TOKEN']['generateValue'] is True
    assert variables['CASHGUARD_INFERENCE_PROVIDER']['value']=='deterministic'


@pytest.mark.parametrize('port,scheme',[(8000,'http'),(8501,'http'),(80,'http'),(True,'http'),(8080,'https; injected')])
def test_ingress_configuration_rejects_conflicting_ports_and_injection(port,scheme):
    with pytest.raises(ValueError):
        render_config('@PORT@ @SCHEME@ @RUNTIME@','/tmp/cashguard-safe',port,scheme)


def test_ingress_blocks_framework_uploads_and_private_routes_even_without_widgets():
    template=(ROOT/'deploy/nginx.conf.template').read_text()
    rendered=render_config(template,'/tmp/cashguard-safe',8080,'http')
    assert '@PORT@' not in rendered and 'listen 8080;' in rendered
    assert '/_stcore/upload_file' in rendered and 'return 403' in rendered
    assert 'GET|HEAD|OPTIONS' in rendered and 'return 405' in rendered
    assert 'proxy_pass http://127.0.0.1:8501' in rendered
    assert 'limit_conn demo_connections 64' in rendered
    assert 'access_log off' in rendered
