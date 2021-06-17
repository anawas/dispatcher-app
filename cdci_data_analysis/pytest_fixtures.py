# this could be a separate package or/and a pytest plugin
from collections import OrderedDict
from json import JSONDecodeError
import yaml

import cdci_data_analysis.flask_app.app
from cdci_data_analysis.flask_app.dispatcher_query import InstrumentQueryBackEnd
from cdci_data_analysis.analysis.hash import make_hash

import re
import json
import string
import random
import requests
import logging
import shutil
import tempfile
import pytest
import subprocess
import os
import copy
import time
import hashlib
import glob

from threading import Thread

__this_dir__ = os.path.join(os.path.abspath(os.path.dirname(__file__)))

logger = logging.getLogger()

import signal, psutil
def kill_child_processes(parent_pid, sig=signal.SIGINT):
    try:
        parent = psutil.Process(parent_pid)
        children = parent.children(recursive=True)
        for process in children:
            process.send_signal(sig)
    except psutil.NoSuchProcess:
        return


@pytest.fixture(scope="session")
def app():
    app = cdci_data_analysis.flask_app.app.app
    return app


@pytest.fixture
def dispatcher_debug(monkeypatch):
    monkeypatch.setenv('DISPATCHER_DEBUG_MODE', 'yes')


@pytest.fixture
def default_params_dict():
    params = dict(
        query_status="new",
        query_type="Real",
        instrument="isgri",
        product_type="isgri_image",
        osa_version="OSA10.2",
        E1_keV=20.,
        E2_keV=40.,
        T1="2008-01-01T11:11:11.0",
        T2="2009-01-01T11:11:11.0",
        max_pointings=2,
        RA=83,
        DEC=22,
        radius=6,
        async_dispatcher=False
    )
    yield params


@pytest.fixture
def default_token_payload():
    default_exp_time = int(time.time()) + 5000
    default_token_payload = dict(
        sub="mtm@mtmco.net",
        name="mmeharga",
        roles="general",
        exp=default_exp_time,
        tem=0,
        mstout=True,
        mssub=True,
        intsub=5
    )

    yield default_token_payload


@pytest.fixture
def dispatcher_nodebug(monkeypatch):
    monkeypatch.delenv('DISPATCHER_DEBUG_MODE', raising=False)
    # monkeypatch.setenv('DISPATCHER_DEBUG_MODE', 'no')

def run_analysis(server, params, method='get'):
    if method == 'get':
        return requests.get(server + "/run_analysis",
                    params={**params},
                    )

    elif method == 'post':
        return requests.post(server + "/run_analysis",
                    data={**params},
                    )
    else:
        raise NotImplementedError


def ask(server, params, expected_query_status, expected_job_status=None, max_time_s=None, expected_status_code=200, method='get'):
    t0 = time.time()

    c = run_analysis(server, params, method=method)

    logger.info(f"\033[31m request took {time.time() - t0} seconds\033[0m")
    t_spent = time.time() - t0

    if max_time_s is not None:
        assert t_spent < max_time_s

    logger.info("content: %s", c.text[:1000])
    if len(c.text) > 1000:
        print(".... (truncated)")

    jdata=c.json()

    if expected_status_code is not None:
        assert c.status_code == expected_status_code

    logger.info(list(jdata.keys()))

    if expected_job_status is not None:
        assert jdata["exit_status"]["job_status"] in expected_job_status

    if expected_query_status is not None:
        assert jdata["query_status"] in expected_query_status

    return jdata

def loop_ask(server, params, method='get', max_time_s=None, async_dispatcher=False):
    jdata = ask(server,
                {**params, 
                'async_dispatcher': async_dispatcher,
                'query_status': 'new',
                },
                expected_query_status=["submitted", "done"],
                method=method,
                )

    last_status = jdata["query_status"]

    t0 = time.time()

    tries_till_reset = 20

    while True:
        if tries_till_reset <= 0:
            next_query_status = "ready"
            print("\033[1;31;46mresetting query status to new, too long!\033[0m")
            tries_till_reset = 20
        else:
            next_query_status = jdata['query_status']
            tries_till_reset -= 1

        jdata = ask(server,
                    {**params, "async_dispatcher": async_dispatcher,
                            'query_status': next_query_status,
                            'job_id': jdata['job_monitor']['job_id'],
                            'session_id': jdata['session_id']},
                    expected_query_status=["submitted", "done"],
                    max_time_s=max_time_s,
                    )

        if jdata["query_status"] in ["ready", "done"]:
            logger.info("query READY: %s", jdata["query_status"])
            break

        logger.info("query NOT-READY: %s monitor %s", jdata["query_status"], jdata["job_monitor"])
        logger.info("looping...")

        time.sleep(5)

    logger.info(f"\033[31m total request took {time.time() - t0} seconds\033[0m")


    return jdata, time.time() - t0

def validate_no_data_products(jdata):
    assert jdata["exit_status"]["debug_message"] == "{\"node\": \"dataanalysis.core.AnalysisException\", \"exception\": \"{}\", \"exception_kind\": \"handled\"}"
    assert jdata["exit_status"]["error_message"] == "AnalysisException:{}"
    assert jdata["exit_status"]["message"] == "failed: get dataserver products "
    assert jdata["job_status"] == "failed"




@pytest.fixture
def dispatcher_local_mail_server(pytestconfig, dispatcher_test_conf):
    from aiosmtpd.controller import Controller

    class CustomController(Controller):
        def __init__(self, id, handler, hostname='127.0.0.1', port=dispatcher_test_conf['email_options']['smtp_port']):
            self.id = id
            super().__init__(handler, hostname=hostname, port=port)

        @property
        def local_smtp_output_json_fn(self):
            return self.handler.output_file_path

        @property
        def local_smtp_output(self):
            return json.load(open(self.local_smtp_output_json_fn))

        def assert_email_number(self, N):
            f_local_smtp_jdata = self.local_smtp_output
            assert len(f_local_smtp_jdata) == N, f"found {len(f_local_smtp_jdata)} emails, expected == {N}"

        def get_email_record(self, i=0, N=None):
            if N is not None:
                assert i < N
                self.assert_email_number(N)

            return self.local_smtp_output[i]
            
            



    class CustomHandler:
        def __init__(self, output_file_path):
            self.output_file_path = output_file_path

        async def handle_DATA(self, server, session, envelope):
            try:
                obj_email_data = dict(
                    mail_from=envelope.mail_from,
                    rcpt_tos=envelope.rcpt_tos,
                    data=envelope.content.decode()
                )
                peer = session.peer
                mail_from = envelope.mail_from
                rcpt_tos = envelope.rcpt_tos
                data = envelope.content
                print(f"mail server: Receiving message from: {peer}")
                print(f"mail server: Message addressed from: {mail_from}")
                print(f"mail server: Message addressed to: {rcpt_tos}")
                print(f"mail server: Message length : {len(data)}")

                # log in a file
                l = []
                if os.path.exists(self.output_file_path):
                    with open(self.output_file_path, 'r') as readfile:
                        try:
                            l = json.load(readfile)
                        except JSONDecodeError as e:
                            pass
                with open(self.output_file_path, 'w+') as outfile:
                    l.append(obj_email_data)
                    json.dump(l, outfile)

            except Exception as e:
                return '500 Could not process your message'
            return '250 OK'

    id = u''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    if not os.path.exists('local_smtp_log'):
        os.makedirs('local_smtp_log')

    fn =f'local_smtp_log/{id}_local_smtp_output.json'
    handler = CustomHandler(fn)
    controller = CustomController(id, handler, hostname='127.0.0.1', port=dispatcher_test_conf['email_options']['smtp_port'])
    # Run the event loop in a separate thread
    controller.start()

    yield controller

    print("will stop the mail server")
    controller.stop()


@pytest.fixture
def dispatcher_local_mail_server_subprocess(pytestconfig, dispatcher_test_conf):
    import subprocess
    import os
    import copy
    from threading import Thread

    env = copy.deepcopy(dict(os.environ))
    print(("rootdir", str(pytestconfig.rootdir)))
    env['PYTHONPATH'] = str(pytestconfig.rootdir) + ":" + str(pytestconfig.rootdir) + "/tests:" + env.get('PYTHONPATH',
                                                                                                          "")
    print(("pythonpath", env['PYTHONPATH']))

    cmd = [
        "python",
        "-m", "smtpd",
        "-c", "DebuggingServer",
        "-n", 
        f"localhost:{dispatcher_test_conf['email_options']['smtp_port']}"
    ]

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        env=env,
    )

    def follow_output():
        for line in iter(p.stdout):
            line = line.decode()
            print(f"mail server: {line.rstrip()}")

    thread = Thread(target=follow_output, args=())
    thread.start()

    yield thread

    print("will stop local mail server")
    print(("child:", p.pid))
    import os, signal
    kill_child_processes(p.pid, signal.SIGINT)
    os.kill(p.pid, signal.SIGINT)


@pytest.fixture
def dispatcher_test_conf_fn(tmpdir):
    fn = os.path.join(tmpdir, "test-dispatcher-conf.yaml")
    with open(fn, "w") as f:
        f.write("""
dispatcher:
    dummy_cache: dummy-cache
    products_url: PRODUCTS_URL
    dispatcher_callback_url_base: http://localhost:8001
    sentry_url: "https://2ba7e5918358439485632251fa73658c@sentry.io/1467382"
    logstash_host: 
    logstash_port: 
    secret_key: 'secretkey_test'
    bind_options:
        bind_host: 0.0.0.0
        bind_port: 8001
    email_options:
        smtp_server: 'localhost'
        sender_email_address: 'team@odahub.io'
        cc_receivers_email_addresses: ['team@odahub.io']
        smtp_port: 61025
        smtp_server_password: ''
        email_sending_timeout: True
        email_sending_timeout_default_threshold: 1800
        email_sending_job_submitted: True
        email_sending_job_submitted_default_interval: 60
    """)

    yield fn


@pytest.fixture
def dispatcher_test_conf(dispatcher_test_conf_fn):
    yield yaml.load(open(dispatcher_test_conf_fn))['dispatcher']


def start_dispatcher(rootdir, test_conf_fn):
    clean_test_dispatchers()

    env = copy.deepcopy(dict(os.environ))
    print(("rootdir", str(rootdir)))
    env['PYTHONPATH'] = str(rootdir) + ":" + str(rootdir) + "/tests:" + env.get('PYTHONPATH', "")
    print(("pythonpath", env['PYTHONPATH']))

    fn = os.path.join(__this_dir__, "../bin/run_osa_cdci_server.py")
    if os.path.exists(fn):
        cmd = [
                 "python", 
                 fn
              ]
    else:
        cmd = [
                 "run_osa_cdci_server.py"
              ]
        
    cmd += [ 
            "-d",
            "-conf_file", test_conf_fn,
            "-debug",
            #"-use_gunicorn" should not be used, as current implementation of follow_output is specific to flask development server
          ] 

    print(f"\033[33mcommand: {cmd}\033[0m")

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        env=env,
    )

    url_store=[None]
    def follow_output():
        url_store[0] = None
        for line in iter(p.stdout):
            line = line.decode()

            NC = '\033[0m'
            if 'ERROR' in line:
                C = '\033[31m'
            else:
                C = '\033[34m'

            print(f"{C}following server: {line.rstrip()}{NC}" )
            m = re.search(r"Running on (.*?) \(Press CTRL\+C to quit\)", line)
            if m:
                url_store[0] = m.group(1)[:-1]  # alaternatively get from configenv
                print(f"{C}following server: found url:{url_store[0]}")

            if re.search("\* Debugger PIN:.*?", line):
                url_store[0] = url_store[0].replace("0.0.0.0", "127.0.0.1")
                print(f"{C}following server: server ready, url {url_store[0]}")


    thread = Thread(target=follow_output, args=())
    thread.start()

    started_waiting = time.time()
    while url_store[0] is None:
        print("waiting for server to start since", time.time() - started_waiting)
        time.sleep(0.2)
    time.sleep(0.5)

    service=url_store[0]

    return dict(
        url=service, 
        pid=p.pid
        )        

@pytest.fixture
def dispatcher_long_living_fixture(pytestconfig, dispatcher_test_conf_fn, dispatcher_debug):
    dispatcher_state_fn = "/tmp/dispatcher-test-fixture-state-{}.json".format(
        hashlib.md5(open(dispatcher_test_conf_fn, "rb").read()).hexdigest()[:8]
        )

    if os.path.exists(dispatcher_state_fn):
        dispatcher_state = json.load(open(dispatcher_state_fn))
        logger.info("found dispatcher state: %s", dispatcher_state)

        try:
            r = requests.get(dispatcher_state['url'] + "/run_analysis")
            logger.info("dispatcher returns: %s, %s", r.status_code, r.text)
            if r.status_code == 200:
                logger.info("dispatcher is live and responsive")
                yield dispatcher_state['url']                
        except requests.exceptions.ConnectionError as e:
            logger.warning("dispatcher connection failed %s", e)        
        
        logger.warning("dispatcher is dead or unresponsive")

    dispatcher_state = start_dispatcher(pytestconfig.rootdir, dispatcher_test_conf_fn)
    json.dump(dispatcher_state, open(dispatcher_state_fn, "w"))
    yield dispatcher_state['url']


@pytest.fixture
def empty_products_files_fixture(default_params_dict):
    #TODO: avoid copypaste in empty_products_user_files_fixture
    # generate job_id
    job_id = make_hash(InstrumentQueryBackEnd.restricted_par_dic(default_params_dict))
    # generate random session_id
    session_id = u''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    scratch_params = dict(
        job_id=job_id,
        session_id= session_id
    )
    DispatcherJobState.remove_scratch_folders(job_id=job_id)
    DispatcherJobState.remove_download_folders()
    scratch_dir_path = f'scratch_sid_{session_id}_jid_{job_id}'
    # set the scratch directory
    os.makedirs(scratch_dir_path)

    with open(scratch_dir_path + '/test.fits.gz', 'wb') as fout:
        scratch_params['content'] = os.urandom(20)
        fout.write(scratch_params['content'])

    with open(scratch_dir_path + '/analysis_parameters.json', 'w') as outfile:
        my_json_str = json.dumps(default_params_dict, indent=4)
        outfile.write(u'%s' % my_json_str)

    yield scratch_params


@pytest.fixture
def empty_products_user_files_fixture(default_params_dict, default_token_payload):
    sub = default_token_payload['sub']
    
    # generate job_id related to a certain user    
    job_id = make_hash(
            {
                **InstrumentQueryBackEnd.restricted_par_dic(default_params_dict),
                 "sub": sub
            }
        )

    # generate random session_id
    session_id = u''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    scratch_params = dict(
        job_id=job_id,
        session_id= session_id
    )
    DispatcherJobState.remove_scratch_folders(job_id=job_id)
    DispatcherJobState.remove_download_folders()
    
    scratch_dir_path = f'scratch_sid_{session_id}_jid_{job_id}'
    # set the scratch directory
    os.makedirs(scratch_dir_path)

    with open(scratch_dir_path + '/test.fits.gz', 'wb') as fout:
        scratch_params['content'] = os.urandom(20)
        fout.write(scratch_params['content'])

    with open(scratch_dir_path + '/analysis_parameters.json', 'w') as outfile:
        my_json_str = json.dumps(default_params_dict, indent=4)
        outfile.write(u'%s' % my_json_str)

    yield scratch_params


@pytest.fixture
def dispatcher_live_fixture(pytestconfig, dispatcher_test_conf_fn, dispatcher_debug):
    dispatcher_state = start_dispatcher(pytestconfig.rootdir, dispatcher_test_conf_fn)

    service = dispatcher_state['url']
    pid = dispatcher_state['pid']

    yield service
        
    print(("child:", pid))
    import os,signal
    kill_child_processes(pid,signal.SIGINT)
    os.kill(pid, signal.SIGINT)


@pytest.fixture
def dispatcher_live_fixture_no_debug_mode(pytestconfig, dispatcher_test_conf_fn, dispatcher_nodebug):
    dispatcher_state = start_dispatcher(pytestconfig.rootdir, dispatcher_test_conf_fn)

    service = dispatcher_state['url']
    pid = dispatcher_state['pid']

    yield service

    print(("child:", pid))
    import os, signal
    kill_child_processes(pid, signal.SIGINT)
    os.kill(pid, signal.SIGINT)


dispatcher_dummy_product_pack_state_fn = "/tmp/dispatcher-dummy-product-pack-ready"


def clean_test_dispatchers():
    for fn in glob.glob("/tmp/dispatcher-test-fixture-state*json"):
        dispatcher_state = json.load(open(fn))
        pid = dispatcher_state['pid']

        try:
            print("child:", pid)
            kill_child_processes(pid,signal.SIGINT)
            os.kill(pid, signal.SIGINT)
        except Exception as e:
            print("unable to cleanup dispatcher", dispatcher_state)

        os.remove(fn)

    if os.path.exists(dispatcher_dummy_product_pack_state_fn):
        os.remove(dispatcher_dummy_product_pack_state_fn)


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):    
    request.addfinalizer(clean_test_dispatchers)
    


def dispatcher_fetch_dummy_products(dummy_product_pack: str, reuse=False):
    url_base = "https://www.isdc.unige.ch/~savchenk" # TODO: to move somewhere to github
    url = f"{url_base}/dispatcher-plugin-integral-data-dummy_prods-{dummy_product_pack}.tgz"

    if reuse:
        if os.path.exists(dispatcher_dummy_product_pack_state_fn):
            logging.info("dispatcher_dummy_product_pack_state_fn: %s found, returning", dispatcher_dummy_product_pack_state_fn)
            return
    
    temp_handle, temp_file_name = tempfile.mkstemp(suffix=f"dummy_product_pack-{dummy_product_pack}")    
    
    with os.fdopen(temp_handle, "wb") as f:        
        logging.info("\033[32mdownloading %s\033[0m", url)
        response = requests.get(url)

        if response.status_code != 200:
            raise RuntimeError(f"can not file dummy_pack {dummy_product_pack} at {url}")

        logging.info("\033[32mfound content length %s\033[0m", len(response.content))
        
        #map(f.write, response.iter_content(1024))

        f.write(response.content)

    dummy_base_dir = os.getcwd()
    shutil.unpack_archive(temp_file_name, extract_dir=dummy_base_dir, format="gztar")
    logging.info("\033[32munpacked to %s\033[0m", dummy_base_dir)

    os.remove(temp_file_name)

    open(dispatcher_dummy_product_pack_state_fn, "w").write("%s"%time.time())


class DispatcherJobState:
    """
    manages state stored in scratch_* directories
    """

    @staticmethod
    def remove_scratch_folders(job_id=None):
        if job_id is None:
            dir_list = glob.glob('scratch_*')
        else:
            dir_list = glob.glob(f'scratch_*_jid_{job_id}*')
        for d in dir_list:
            shutil.rmtree(d)

    @staticmethod
    def remove_download_folders(id=None):
        if id is None:
            dir_list = glob.glob('download_*')
        else:
            dir_list = glob.glob(f'download_{id}')
        for d in dir_list:
            shutil.rmtree(d)

    @classmethod
    def from_run_analysis_response(cls, r):
        return cls(
            session_id = r.json()['session_id'],
            job_id = r.json()['job_monitor']['job_id']
        )
    
    def __init__(self, session_id, job_id) -> None:
        self.session_id = session_id
        self.job_id = job_id
    
    @property
    def scratch_dir(self):
        return glob.glob(f'scratch_sid_{self.session_id}_jid_{self.job_id}*')[0]
    

    @property
    def job_monitor_json_fn(self):
        job_monitor_json_fn = f'{self.scratch_dir}/job_monitor.json'
        assert os.path.exists(job_monitor_json_fn) 

        return job_monitor_json_fn

    @property
    def email_history_folder(self) -> str:
        return f'{self.scratch_dir}/email_history'

    def assert_email(self, state, number=1, comment=""):
        list_email_files = glob.glob(self.email_history_folder + f'/email_{state}_*.email')
        assert len(list_email_files) == number, f"expected {number} emails, found {len(list_email_files)}: {list_email_files} in {self.email_history_folder}; {comment}"

    def load_job_state_record(self, state, message):
        return json.load(open(f'{self.scratch_dir}/job_monitor_{state}_{message}_.json'))

    def load_emails(self):
        return [ open(fn).read() for fn in glob.glob(f"{self.email_history_folder}/*") ]