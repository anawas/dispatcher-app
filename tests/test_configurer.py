from cdci_data_analysis.configurer import DataServerConf
import os
import pytest

@pytest.fixture
def dispatcher_debug(monkeypatch):
    monkeypatch.setenv('DISPATCHER_DEBUG_MODE', 'yes')

@pytest.fixture
def dispatcher_nodebug(monkeypatch):
    monkeypatch.delenv('DISPATCHER_DEBUG_MODE', raising=False)

def test_dsconf_integral_osa(tmpdir):
    conf_dict = {'data_server_url': 'https://data-server:5000',
            'dispatcher_mnt_point': 'data',
            'data_server_remote_cache': 'reduced/ddcache',
            'dummy_cache': 'data/dummy_prods',
            }
    os.chdir(tmpdir)
    conf = DataServerConf.from_conf_dict(conf_dict)
    assert conf.dummy_cache == conf_dict['dummy_cache']
    assert conf.data_server_url == conf_dict['data_server_url']
    assert conf.data_server_remote_path == conf_dict['data_server_remote_cache']
    assert os.path.isdir(conf_dict['dispatcher_mnt_point'])

def test_dsconf_lost_url():
    conf_dict = {'dummy_cache': 'dumme_cache',
                 }
    with pytest.raises(KeyError):
        DataServerConf.from_conf_dict(conf_dict)

def test_dsconf_required_warning(caplog, dispatcher_debug):
    conf_dict = {'data_server_url': 'https://data-server:5000',
                 'dummy_cache': None}
    conf = DataServerConf.from_conf_dict(conf_dict)
    assert "required configuration" in caplog.text

def test_dsconf_required_error(caplog, dispatcher_nodebug):
    conf_dict = {'data_server_url': 'https://data-server:5000'}
    with pytest.raises(KeyError):
        conf = DataServerConf.from_conf_dict(conf_dict)

def test_dsconf_obsolete_warning(caplog):
    conf_dict = {'data_server_url': 'https://data-server:5000',
                 'dummy_cache': 'dummy_cache',
                 'data_server_port': '5000'
                 }
    conf = DataServerConf.from_conf_dict(conf_dict)
    assert "disregarded" in caplog.text

def test_dsconf_allowed_key():
    conf_dict = {'data_server_url': 'https://data-server:5000',
                 'dummy_cache': 'dummy_cache',
                 'data_server_cache': 'reduced/ddcache'
                 }
    conf = DataServerConf.from_conf_dict(conf_dict)

def test_dsconf_bad_key():
    conf_dict = {'data_server_url': 'https://data-server:5000',
                  'dummy_cache': 'dummy_cache',
                  'spam': 'eggs'
                }
    with pytest.raises(KeyError):
        conf = DataServerConf.from_conf_dict(conf_dict)

def test_dsconf_pass_keys():
    conf_dict = {'data_server_url': 'https://data-server:5000',
                 'dummy_cache': 'dummy_cache',
                 'required_key': 'required_value',
                 'extra_key': 'extra_value'}
    required_keys = ['data_server_url', 'dummy_cache', 'required_key']
    allowed_keys = required_keys + ['extra_key']
    conf = DataServerConf.from_conf_dict(conf_dict, required_keys, allowed_keys)

    conf_dict['spam'] = 'eggs'
    with pytest.raises(KeyError):
        conf = DataServerConf.from_conf_dict(conf_dict, required_keys, allowed_keys)

@pytest.mark.xfail
def test_dsconf_legacy_plugin_keys(caplog):
    conf = DataServerConf(data_server_url="eggs",
                          data_server_port="bacon",
                          data_server_remote_cache=None,
                          dispatcher_mnt_point=None,
                          dummy_cache="spam")

    assert conf.data_server_port is None
    assert conf.data_server_host is None
    assert 'attempting to access obsolete key data_server_port, returning None' in caplog.text
    assert 'attempting to access obsolete key data_server_host, returning None' in caplog.text

    with pytest.raises(AttributeError):
        conf.data_server_spam 

