import grpc
import time
import uuid
import os
import sys
import asyncio
import socket
import json
import aiofiles
import aiofiles.os as aioos
import base64
import datetime
import logging
import inspect
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec as asymec
from .dborgproto import dborgproto_pb2_grpc
from .dborgproto import dborgproto_pb2
from hashlib import sha256

TLS_KEY_FILENAME = "dashborg-client.key"
TLS_CERT_FILENAME = "dashborg-client.crt"
DEFAULT_PROCNAME = "default"
DEFAULT_ZONENAME = "default"
DASHBORG_HOST = "grpc.api.dashborg.net"
DASHBORG_PORT = 7632
CLIENT_VERSION = "python-0.0.1"

EC_EOF = "EOF"
EC_UNKNOWN = "UNKNOWN"
EC_BADCONNID = "BADCONNID"
EC_ACCACCESS = "ACCACCESS"
EC_NOHANDLER = "NOHANDLER"
EC_UNAVAILABLE = "UNAVAILABLE"

DASHBORG_CERT = """
-----BEGIN CERTIFICATE-----
MIIBxDCCAUmgAwIBAgIFAv2DbD4wCgYIKoZIzj0EAwMwLzEtMCsGA1UEAxMkNWZk
YWYxZDEtYjUyNC00MzYxLWFkY2ItMzI1ZDBlOGFiN2VlMB4XDTIwMDEwMTAwMDAw
MFoXDTMwMDEwMTAwMDAwMFowLzEtMCsGA1UEAxMkNWZkYWYxZDEtYjUyNC00MzYx
LWFkY2ItMzI1ZDBlOGFiN2VlMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEhsrFNs6I
reL5fWAdQxzNrYRgJdf2zE2aeBj/o28mXR1iQRtAlBY9Jh9zQtZCnypK2MprKvqw
07f0YoquV17gOhumj7LIRhlZ9GANwra6VorRVtVVgKCpTmG8o/ulJ3o4ozUwMzAO
BgNVHQ8BAf8EBAMCB4AwEwYDVR0lBAwwCgYIKwYBBQUHAwIwDAYDVR0TAQH/BAIw
ADAKBggqhkjOPQQDAwNpADBmAjEAtW26nW+AHoa9VQiqmGJ8z/+265YUK6QkkQ+T
276zLFAdfAO+bOVK0MMjzr21v6aLAjEA6LknqHnEh+QDWWIm8vM1Jp/FtiJ0KT//
4qUptLIY0pSijwpt/TAZd4QG8M5IQ+T7
-----END CERTIFICATE-----
"""

_global_client = None
_dblogger = logging.getLogger("dashborg")

def dashts():
    return int(round(time.time()*1000))

def _default_string(*args):
    for s in args:
        if s is not None and s != "":
            return s
    return None

def _parse_int(v):
    try:
        return int(v)
    except:
        return None

class _HandlerVal:
    def __init__(self, fn, proto_hkey):
        self.handler_fn = fn
        self.proto_hkey = proto_hkey

class Config:
    def __init__(self, acc_id=None, anon_acc=None, zone_name=None, proc_name=None, proc_tags=None, key_file_name=None, cert_file_name=None, auto_keygen=None, verbose=None, env=None, dashborg_srv_host=None, dashborg_srv_port=None, use_logger=False):
        self.acc_id = acc_id
        self.anon_acc = anon_acc
        self.zone_name = zone_name
        self.proc_name = proc_name
        self.proc_tags = proc_tags
        self.key_file_name = key_file_name
        self.cert_file_name = cert_file_name
        self.auto_keygen = auto_keygen
        self.verbose = verbose
        self.env = env
        self.dashborg_srv_host = dashborg_srv_host
        self.dashborg_srv_port = dashborg_srv_port
        self.use_logger = use_logger

    def _set_defaults(self):
        self.acc_id = _default_string(self.acc_id, os.environ.get("DASHBORG_ACCID"))
        self.zone_name = _default_string(self.zone_name, os.environ.get("DASHBORG_ZONE"), DEFAULT_ZONENAME)
        self.env = _default_string(self.env, os.environ.get("DASHBORG_ENV"), "prod")
        if self.env == "prod":
            self.dashborg_srv_host = _default_string(self.dashborg_srv_host, os.environ.get("DASHBORG_PROCHOST"), DASHBORG_HOST)
        else:
            self.dashborg_srv_host = _default_string(self.dashborg_srv_host, os.environ.get("DASHBORG_PROCHOST"), "127.0.0.1")
        if self.dashborg_srv_port is None and os.environ.get("DASHBORG_PROCPORT") is not None:
            env_val = _parse_int(os.environ.get("DASHBORG_PROCPORT"))
            if env_val is not None:
                self.dashborg_srv_port = env_val
        if self.dashborg_srv_port is None:
            self.dashborg_srv_port = DASHBORG_PORT
        cmd_name = None
        if len(sys.argv) > 0:
            cmd_name = sys.argv[0]
        self.proc_name = _default_string(self.proc_name, os.environ.get("DASHBORG_PROCNAME"), cmd_name, DEFAULT_PROCNAME)
        self.key_file_name = _default_string(self.key_file_name, os.environ.get("DASHBORG_KEYFILE"), TLS_KEY_FILENAME)
        self.cert_file_name = _default_string(self.cert_file_name, os.environ.get("DASHBORG_CERTFILE"), TLS_CERT_FILENAME)
        if os.environ.get("DASHBORG_VERBOSE") is not None:
            self.verbose = True
        if os.environ.get("DASHBORG_USELOGGER") is not None:
            self.use_logger = True

    def _load_keys(self):
        if self.auto_keygen:
            self._maybe_make_keys()
        if not os.path.isfile(self.key_file_name):
            raise RuntimeError(f"Dashborg key file does not exist file:{self.key_file_name}")
        if not os.path.isfile(self.cert_file_name):
            raise RuntimeError(f"Dashborg cert file does not exist file:{self.cert_file_name}")
        cert_info = _read_cert_info(self.cert_file_name)
        if self.acc_id is not None and cert_info["acc_id"] != self.acc_id:
            raise RuntimeError(f"Dashborg AccId read from certificate:{cert_info['acc_id']} does not match AccId in config:{self.acc_id}")
        self.acc_id = cert_info["acc_id"]
        print(f"Dashborg KeyFile:{self.key_file_name} CertFile:{self.cert_file_name} SHA256:{cert_info['pk256']}")


    def _maybe_make_keys(self):
        if self.key_file_name is None or self.cert_file_name is None:
            raise RuntimeError("Empty/Invalid Key or Cert filenames")
        has_key = os.path.isfile(self.key_file_name)
        has_cert = os.path.isfile(self.cert_file_name)
        if has_key and has_cert:
            return
        if has_key or has_cert:
            raise RuntimeError(f"Cannot make key:{self.key_file_name} cert:{self.cert_file_name}, one file already exists")
        acc_id = self.acc_id
        if acc_id is None:
            acc_id = str(uuid.uuid4())
        _create_key_pair(self.key_file_name, self.cert_file_name, acc_id)
        print(f"Dashborg created new self-signed keypair key:{self.key_file_name} cert:{self.cert_file_name} for new accountid:{acc_id}")

def _create_key_pair(keyfile, certfile, acc_id):
    private_key = asymec.generate_private_key(asymec.SECP384R1, default_backend())
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                              format=serialization.PrivateFormat.PKCS8,
                                              encryption_algorithm=serialization.NoEncryption())
    with open(keyfile, "wb") as f:
        f.write(bytes("-----BEGIN EC PARAMETERS-----\n"
                      "BgUrgQQAIg==\n"
                      "-----END EC PARAMETERS-----\n", "utf-8"))
        f.write(private_bytes)
    cert_name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, acc_id)])
    builder = x509.CertificateBuilder()
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.subject_name(cert_name)
    builder = builder.issuer_name(cert_name)
    builder = builder.not_valid_before(datetime.datetime(2020, 1, 1))
    builder = builder.not_valid_after(datetime.datetime(2030, 1, 1))
    builder = builder.public_key(public_key)
    builder = builder.sign(private_key=private_key,
                           algorithm=hashes.SHA256(),
                           backend=default_backend())
    cert_bytes = builder.public_bytes(encoding=serialization.Encoding.PEM)
    with open(certfile, "wb") as f:
        f.write(cert_bytes)


def _read_cert_info(cert_file):
    cert_data = open(cert_file, "rb").read()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    subject = cert.subject
    cns = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    acc_id = cns[0].value
    pk = cert.public_key()
    pkbytes = pk.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pkdigest = sha256(pkbytes)
    pk256_base64 = base64.standard_b64encode(pkdigest.digest()).decode("ascii")
    return {"acc_id": acc_id, "pk256": pk256_base64}

class PanelRequest:
    def __init__(self, req_msg):
        self.panel_name = req_msg.PanelName
        self.req_id = req_msg.ReqId
        self.request_type = req_msg.RequestType
        self.fe_client_id = req_msg.FeClientId
        self.path = req_msg.Path
        self.err = None
        self.rr_actions = []
        self.is_done = False
        self.data = None
        self.panel_state = None
        self.auth_data = []
        self.auth_impl = False

    async def done(self):
        if self.is_done:
            return
        if not self.auth_impl and self._is_root_req():
            self.no_auth()
        await _global_client._send_request_response(self, True)

    def _append_rr(self, rr):
        self.rr_actions.append(rr)

    def _is_root_req(self):
        return self.request_type == "handler" and self.panel_name is not None and self.path == "/"

    async def _flush(self):
        if self.is_done:
            raise RuntimeError("Cannot flush(), PanelRequest is already done")
        await _global_client._send_request_response(self, False)
        return

    def _is_authenticated(self):
        raw_auth = self.auth_data
        return raw_auth is not None and len(raw_auth) > 0

    def no_auth(self):
        self.auth_impl = True
        if not self._is_authenticated():
            self._append_panelauth_rraction("noauth", "user")

    def dashborg_auth(self):
        self.auth_impl = True
        if self._is_authenticated():
            return True
        challenge = {"allowedauth": "dashborg"}
        self._append_panelauth_challenge(challenge)
        return False

    def password_auth(self, pw):
        self.auth_impl = True
        if self._is_authenticated():
            return True
        # check challenge-data
        challengedata = self.data.get("challengedata") if type(self.data) is dict else None
        if challengedata is not None and challengedata.get("password") == pw:
            self._append_panelauth_rraction("password", "user")
            return True

        # send challenge
        challenge = {"allowedauth": "challenge,dashborg"}
        cfield = {"label": "Panel Password", "name": "password", "type": "password"}
        challenge["challengefields"] = [cfield]
        if challengedata is not None and challengedata.get("submitted") == "1":
            chpw = challengedata.get("password")
            if chpw is None or chpw == "":
                challenge["challengeerror"] = "Password cannot be blank"
            else:
                challenge["challengeerror"] = "Invalid Password"
        self._append_panelauth_challenge(challenge)
        return False

    def _append_panelauth_rraction(self, authtype, authrole):
        ts = dashts() + (24 * 60 * 60 * 1000)
        aa = {"type": authtype, "auto": True, "ts": ts, "role": authrole}
        json_data = json.dumps(aa)
        rr_action = dborgproto_pb2.RRAction(Ts=dashts(), ActionType="panelauth", JsonData=json_data)
        self._append_rr(rr_action)
        return

    def _append_panelauth_challenge(self, challenge):
        json_data = json.dumps(challenge)
        rr_action = dborgproto_pb2.RRAction(Ts=dashts(), ActionType="panelauthchallenge", JsonData=json_data)
        self._append_rr(rr_action)
        pass

    def set_data(self, path, data):
        if self.is_done:
            raise RuntimeError(f"Cannot call set_data(), path={path}, PanelRequest is already done")
        json_data = json.dumps(data)
        rr_action = dborgproto_pb2.RRAction(Ts=dashts(), ActionType="setdata", Selector=path, JsonData=json_data)
        self._append_rr(rr_action)
        return

    def set_html(self, html):
        if self.is_done:
            raise RuntimeError(f"Cannot call set_html(), PanelRequest is already done")
        rr_action = dborgproto_pb2.RRAction(Ts=dashts(), ActionType="html", Html=html)
        self._append_rr(rr_action)
        return

    async def set_html_from_file(self, file_name):
        if self.is_done:
            raise RuntimeError(f"Cannot call set_html(), PanelRequest is already done")
        fd = await aiofiles.open(file_name, "r")
        html = await fd.read()
        self.set_html(html)
        return

    def invalidate_data(self, path):
        if self.is_done:
            raise RuntimeError(f"Cannot call invalidate_data(), path={path}, PanelRequest is already done")
        rr_action = dborgproto_pb2.RRAction(Ts=dashts(), ActionType="invalidate", Selector=path)
        self._append_rr(rr_action)
        return

def _make_handler_key(req_msg):
    htype = None
    if req_msg.RequestType == "data":
        htype = "data"
    elif req_msg.RequestType == "handler":
        htype = "handler"
    elif req_msg.RequestType == "panel":
        htype = "panel"
    elif req_msg.RequestType == "streamopen" or req_msg.RequestType == "streamclose":
        htype = "stream"
    else:
        raise RuntimeError(f"Invalid RequestMessage.RequestType [{req_msg.RequestType}]")
    path = req_msg.Path
    if path == "":
        path = None
    return (req_msg.PanelName, htype, path)

class Client:
    def __init__(self, config):
        self.cvar = asyncio.Condition()
        self.start_ts = dashts()
        self.proc_run_id = str(uuid.uuid4())
        self.handler_map = {}
        self.conn_id = None
        self.config = config
        self.conn = None
        self.db_service = None

    async def _wait_for_clear(self, wait_time=1.0):
        self.conn.close()
        await asyncio.sleep(wait_time)

    async def _connect_grpc(self):
        if self.conn is not None:
            await self.conn.close()
        if self.config.verbose:
            print(f"Dashborg Connect gRPC ({self.config.dashborg_srv_host})")
        addr = self.config.dashborg_srv_host + ":" + str(self.config.dashborg_srv_port)
        # todo backoff config
        # todo connect params
        private_key = open(self.config.key_file_name, "rb").read()
        cert = open(self.config.cert_file_name, "rb").read()
        servercert = bytes(DASHBORG_CERT, "utf-8")
        creds = grpc.ssl_channel_credentials(root_certificates=servercert, private_key=private_key, certificate_chain=cert)
        options = (("grpc.ssl_target_name_override", "5fdaf1d1-b524-4361-adcb-325d0e8ab7ee"),
                   ("grpc.keepalive_time_ms", 5000),
                   ("grpc.keepalive_permit_without_calls", 1),
                   ("grpc.max_reconnect_backoff_ms", 60000),
                   ("grpc.min_reconnect_backoff_ms", 1000),
                   ("grpc.initial_reconnect_backoff_ms", 1000),
                   ("grpc.server_handshake_timeout_ms", 10000),
                   ("grpc.max_receive_message_length", 10000000))
        # "grpc.enable_retries"
        self.conn = grpc.aio.secure_channel(target=addr, credentials=creds, options=options)
        self.db_service = dborgproto_pb2_grpc.DashborgServiceStub(self.conn)

    def _get_proc_handlers(self):
        rtn = []
        for k in self.handler_map.keys():
            h = self.handler_map.get(k)
            rtn.append(h.proto_hkey)
        return rtn

    async def _send_proc_message(self):
        proc_msg = dborgproto_pb2.ProcMessage()
        proc_msg.Ts = dashts()
        proc_msg.ProcRunId = self.proc_run_id
        proc_msg.AccId = self.config.acc_id
        proc_msg.ZoneName = self.config.zone_name
        proc_msg.AnonAcc = self.config.anon_acc
        proc_msg.ProcName = self.config.proc_name
        if self.config.proc_tags is not None:
            for k in self.config.proc_tags.keys():
                proc_msg.ProcTags[k] = self.config.proc_tags[k]
        proc_msg.HostData["HostName"] = socket.gethostname()
        proc_msg.HostData["Pid"] = str(os.getpid())
        proc_msg.StartTs = self.start_ts
        proc_msg.Handlers.extend(self._get_proc_handlers())
        proc_msg.ClientVersion = CLIENT_VERSION
        try:
            rtn = await self.db_service.Proc(proc_msg)
            if rtn.Success:
                self.conn_id = rtn.ConnId
                _log_info_config(self.config, f"Dashborg ProcClient connected connid:{self.conn_id}")
            else:
                _log_error(f"Dashborg Error calling Proc(), err:{rtn.Err} code:{rtn.ErrCode}")
                self.conn_id = None
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                _log_error(f"Dashborg service unavailable: {e.details()}")
            else:
                _log_error(f"Dashborg Error calling Proc() {e}")
            self.conn_id = None

    async def _run_request_stream_loop(self):
        needs_wait = False
        num_waits = 0
        while True:
            s = self.conn.get_state()
            if s == grpc.ChannelConnectivity.SHUTDOWN:
                _log_info(f"Dashborg stopping request loop, channel shutdown")
                return
            if s == grpc.ChannelConnectivity.CONNECTING or s == grpc.ChannelConnectivity.TRANSIENT_FAILURE:
                _log_info(f"Dashborg waiting for gRPC connection")
                await asyncio.sleep(1)
                needs_wait = False
                continue
            if needs_wait:
                _log_info(f"Dashborg run_request_stream_loop needs_wait")
                await asyncio.sleep(1)
            if self.conn_id == None:
                await self._send_proc_message()
                needs_wait = (self.conn_id is None)
                continue
            ec = await self._run_request_stream()
            _log_info(f"Dashborg run_request_stream finished ec:{ec}")
            if ec == EC_BADCONNID:
                self.conn_id = None
                continue
            needs_wait = True

    async def _dispatch_request(self, req_msg):
        if req_msg.Err is not None and req_msg.Err != "":
            _log_info(f"Dashborg dispatch_request got error request err:{req_msg.Err}")
            return
        _log_info(f"Dashborg gRPC got request panel={req_msg.PanelName}, type={req_msg.RequestType}, path={req_msg.Path}")
        preq = PanelRequest(req_msg)
        hkey = _make_handler_key(req_msg)
        hval = self.handler_map.get(hkey)
        if hval == None:
            preq.err = f"No Handler found for panel={req_msg.PanelName}, type={req_msg.RequestType}, path={req_msg.Path}"
            await preq.done()
            return
        try:
            if req_msg.JsonData is not None and req_msg.JsonData != "":
                data = json.loads(req_msg.JsonData)
                preq.data = data
            if req_msg.PanelStateData is not None and req_msg.PanelStateData != "":
                panel_state = json.loads(req_msg.PanelStateData)
                preq.panel_state = panel_state
            if req_msg.AuthData is not None and req_msg.AuthData != "":
                auth = json.loads(req_msg.AuthData)
                preq.auth_data = auth
            if not preq._is_root_req():
                if not preq._is_authenticated():
                    preq.err = "Request is not authenticated"
                    await preq.done()
                    return
        except json.JSONDecodeError as e:
            _log_info(f"Cannot json.loads request data err:{e}")
        try:
            rtnval = None
            if inspect.iscoroutinefunction(hval.handler_fn):
                timeout_val = req_msg.TimeoutMs / 1000.0 if req_msg.TimeoutMs > 0 else None
                if timeout_val is None or timeout_val > 60:
                    timeout_val = 60
                rtnval = await asyncio.wait_for(hval.handler_fn(preq), timeout_val)
            else:
                rtnval = hval.handler_fn(preq)
            if req_msg.RequestType == "data":
                rr_action = dborgproto_pb2.RRAction(Ts=dashts(), ActionType="setdata", JsonData=json.dumps(rtnval))
                preq._append_rr(rr_action)
        except Exception as e:
            preq.err = repr(e);
        finally:
            await preq.done()

    async def _run_request_stream(self):
        try:
            _log_info("Dashborg gRPC RequestStream starting")
            stream_msg = dborgproto_pb2.RequestStreamMessage(Ts=dashts())
            conn_meta = (("dashborg-connid", self.conn_id),)
            msgs = self.db_service.RequestStream(stream_msg, metadata=conn_meta)
            ending_ec = None
            req_counter = 0
            async for msg in msgs:
                if msg.ErrCode == dborgproto_pb2.EC_BADCONNID:
                    ending_ec = EC_BADCONNID
                    _log_info("Dashborg gRPC RequestStream BADCONNID")
                    break
                if msg.Err is not None and msg.Err != "":
                    ending_ec = EC_UNKNOWN
                    _log_info(f"Dashborg gRPC RequestStrem error:{msg.Err} code:{msg.ErrCode}")
                    break
                req_counter += 1
                asyncio.create_task(self._dispatch_request(msg))
            if ending_ec is None:
                _log_info("Dashborg gRPC RequestStream end of iteration")
                return EC_EOF
            return ending_ec
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                return EC_UNAVAILABLE
            _log_info(f"Dashborg gRPC error {e}")
            return EC_UNKNOWN
        finally:
            _log_info("Dashborg gRPC RequestStream done")

    async def _register_handler(self, proto_hkey, handler_fn):
        path = None if proto_hkey.Path == "" else proto_hkey.Path
        hkey = (proto_hkey.PanelName, proto_hkey.HandlerType, path)
        self.handler_map[hkey] = _HandlerVal(handler_fn, proto_hkey)
        if self.conn_id is None:
            return
        msg = dborgproto_pb2.RegisterHandlerMessage(Ts=dashts())
        msg.Handlers.append(proto_hkey)
        conn_meta = (("dashborg-connid", self.conn_id),)
        try:
            resp = await self.db_service.RegisterHandler(msg, metadata=conn_meta)
            if resp.Err is not None and resp.Err != "":
                _log_error(f"Dashborg RegisterHandler error:{resp.Err} code:{resp.ErrCode}")
                return
            _log_info(f"Dashborg RegisterHandler Success {hkey}")
        except grpc.RpcError as e:
            _log_error(f"Dashborg RegisterHandler Error-rpc: {e}")

    async def _send_request_response(self, req, done):
        if self.conn_id is None:
            raise RuntimeError("No Active ConnId for RequestResponse")
        msg = dborgproto_pb2.SendResponseMessage(
            Ts=dashts(),
            ReqId=req.req_id,
            RequestType=req.request_type,
            PanelName=req.panel_name,
            FeClientId=req.fe_client_id,
            ResponseDone=done,
            Err=req.err)
        msg.Actions.extend(req.rr_actions)
        conn_meta = (("dashborg-connid", self.conn_id),)
        try:
            resp = await self.db_service.SendResponse(msg, metadata=conn_meta)
            if resp.Err is not None and resp.Err != "":
                _log_error(f"Dashborg SendResponse error:{resp.Err}")
        except grpc.RpcError as e:
            _log_error(f"Dashborg SendResponse gRPC error:{e}")


async def start_proc_client(config):
    config._set_defaults()
    config._load_keys()
    client = Client(config)
    await client._connect_grpc()
    print(f"Dashborg Initialized Client AccId:{config.acc_id} Zone:{config.zone_name} ProcName:{config.proc_name} ProcRunId:{client.proc_run_id}")
    await client._send_proc_message()
    global _global_client
    _global_client = client
    asyncio.create_task(client._run_request_stream_loop())
    return

async def _wait_for_clear(wait_time=1.0):
    if _global_client is not None:
        await _global_client._wait_for_clear(wait_time)

def panel_link(panel_name):
    acc_id = _global_client.config.acc_id
    zone_name = _global_client.config.zone_name
    if _global_client.config.env != "prod":
        return f"http://console.dashborg.localdev:8080/acc/{acc_id}/{zone_name}/{panel_name}"
    return f"https://console.dashborg.net/acc/{acc_id}/{zone_name}/{panel_name}"

async def register_data_handler(panel_name, path, handler_fn):
    hkey = dborgproto_pb2.HandlerKey(PanelName=panel_name, HandlerType="data", Path=path)
    await _global_client._register_handler(hkey, handler_fn)

async def register_panel_handler(panel_name, path, handler_fn):
    hkey = dborgproto_pb2.HandlerKey(PanelName=panel_name, HandlerType="handler", Path=path)
    await _global_client._register_handler(hkey, handler_fn)
    if path == "/":
        print(f"Dashborg Panel Link [{panel_name}]: {panel_link(panel_name)}")

async def register_panel_class(panel_name, obj):
    methods = inspect.getmembers(obj, inspect.ismethod)
    for (name, m) in methods:
        sig = inspect.signature(m)
        if len(sig.parameters) != 1:
            continue
        firstparam = next(iter(sig.parameters))
        if firstparam == "req":
            if name == "root_handler":
                await register_panel_handler(panel_name, "/", m)
            else:
                await register_panel_handler(panel_name, "/" + name, m)
        elif firstparam == "datareq":
            await register_data_handler(panel_name, "/" + name, m)

def _log_info(*args):
    if _global_client is None:
        return
    if _global_client.config.use_logger:
        _dblogger.info(*args)
    elif _global_client.config.verbose:
        print(*args)

def _log_info_config(config, *args):
    if config is None:
        return
    if config.use_logger:
        _dblogger.info(*args)
    elif config.verbose:
        print(*args)

def _log_error(*args):
    if _global_client is not None and _global_client.config.use_logger:
        _dblogger.error(*args)
    else:
        print(args)


