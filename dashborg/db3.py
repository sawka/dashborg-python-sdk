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
import datetime
import logging
import inspect
import io
import functools
import traceback
import glob
import watchdog
import aiohttp
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as WatchdogObserver
from .dborgproto import dborgproto_pb2_grpc
from .dborgproto import dborgproto_pb2
from . import dbu
from .dbu import DashborgError
from . import dbcrypto
from typing import Callable

try:
    import dataclasses
except ImportError:
    # Python < 3.7
    dataclasses = None  # type: ignore

NotConnectedErr = DashborgError("Dashborg Client is not connected", err_code="NOCONN")
watchdog_observer = None


TLS_KEY_FILENAME = "dashborg-client.key"
TLS_CERT_FILENAME = "dashborg-client.crt"
DEFAULT_PROCNAME = "default"
DEFAULT_ZONENAME = "default"
DASHBORG_CONSOLE_HOST = "console.dashborg.net"
_DASHBORG_DEV_CONSOLE_HOST = "console.dashborg-dev.com:8080"
CLIENT_VERSION = "python-0.4.0"
USE_REQ_DEFAULT = object()
DEFAULT_GRPC_TIMEOUT = 10.0

EC_EOF = "EOF"
EC_UNKNOWN = "UNKNOWN"
EC_BADCONNID = "BADCONNID"
EC_ACCACCESS = "ACCACCESS"
EC_NOHANDLER = "NOHANDLER"
EC_UNAVAILABLE = "UNAVAILABLE"

# must be divisible by 3 (for base64 encoding)
BLOB_READ_SIZE = 3 * 340 * 1024
MAX_RRA_BLOB_SIZE = 3 * 1024 * 1024
STREAM_BLOCKSIZE = 1000000

_dblogger = logging.getLogger("dashborg")

class Config:
    def __init__(self, acc_id=None, anon_acc=None, zone_name=None, proc_name=None, proc_ikey=None, proc_tags=None, key_file_name=None, cert_file_name=None, auto_keygen=None, verbose=None, env=None, console_host=None, grpc_host=None, grpc_port=None, use_logger=False, allow_backend_calls=False, jwt_opts=None, no_jwt=False):
        self.acc_id = acc_id
        self.anon_acc = anon_acc
        self.zone_name = zone_name
        self.proc_name = proc_name
        self.proc_ikey = proc_ikey
        self.proc_tags = proc_tags
        self.key_file_name = key_file_name
        self.cert_file_name = cert_file_name
        self.auto_keygen = auto_keygen
        self.verbose = verbose
        self.env = env
        self.console_host = console_host
        self.grpc_host = grpc_host
        self.grpc_port = grpc_port
        self.use_logger = use_logger
        self.allow_backend_calls = allow_backend_calls
        self.jwt_opts = jwt_opts
        self.no_jwt = no_jwt
        self.setup_done = False
        self.json_opts = {"serializefn": dbu.serialize, "jsondumps": json.dumps, "jsondumpskwargs": {}}

    def _setup(self):
        if not self.setup_done:
            self._set_defaults()
            self._load_keys()
            self.setup_done = True

    def _set_defaults(self):
        self.acc_id = dbu.default_string(self.acc_id, os.environ.get("DASHBORG_ACCID"))
        self.zone_name = dbu.default_string(self.zone_name, os.environ.get("DASHBORG_ZONE"), DEFAULT_ZONENAME)
        self.env = dbu.default_string(self.env, os.environ.get("DASHBORG_ENV"), "prod")
        if self.env == "prod":
            self.console_host = dbu.default_string(self.console_host, os.environ.get("DASHBORG_CONSOLEHOST"), DASHBORG_CONSOLE_HOST)
        else:
            self.console_host = dbu.default_string(self.console_host, os.environ.get("DASHBORG_CONSOLEHOST"), _DASHBORG_DEV_CONSOLE_HOST)
        self.grpc_host = dbu.default_string(self.grpc_host, os.environ.get("DASHBORG_GRPCHOST"))
        if self.grpc_port is None and os.environ.get("DASHBORG_GRPCPORT") is not None:
            env_val = _parse_int(os.environ.get("DASHBORG_GRPCPORT"))
            if env_val is not None:
                self.grpc_port = env_val
        cmd_name = None
        if len(sys.argv) > 0:
            cmd_name = sys.argv[0]
        self.proc_name = dbu.default_string(self.proc_name, os.environ.get("DASHBORG_PROCNAME"), cmd_name, DEFAULT_PROCNAME)
        self.proc_ikey = dbu.default_string(self.proc_ikey, os.environ.get("DASHBORG_PROCIKEY"))
        self.key_file_name = dbu.default_string(self.key_file_name, os.environ.get("DASHBORG_KEYFILE"), TLS_KEY_FILENAME)
        self.cert_file_name = dbu.default_string(self.cert_file_name, os.environ.get("DASHBORG_CERTFILE"), TLS_CERT_FILENAME)
        if os.environ.get("DASHBORG_VERBOSE") is not None:
            self.verbose = True
        if os.environ.get("DASHBORG_USELOGGER") is not None:
            self.use_logger = True
        if self.jwt_opts is None:
            self.jwt_opts = {}

    def _load_keys(self):
        if self.auto_keygen:
            self._maybe_make_keys()
        if not os.path.isfile(self.key_file_name):
            raise RuntimeError(f"Dashborg key file does not exist file:{self.key_file_name}")
        if not os.path.isfile(self.cert_file_name):
            raise RuntimeError(f"Dashborg cert file does not exist file:{self.cert_file_name}")
        cert_info = dbcrypto.read_cert_info(self.cert_file_name)
        if self.acc_id is not None and cert_info["acc_id"] != self.acc_id:
            raise RuntimeError(f"Dashborg AccId read from certificate:{cert_info['acc_id']} does not match AccId in config:{self.acc_id}")
        self.acc_id = cert_info["acc_id"]
        print(f"Dashborg KeyFile:{self.key_file_name} CertFile:{self.cert_file_name} SHA256:{cert_info['pk256']}")


    def _maybe_make_keys(self):
        if self.key_file_name is None or self.cert_file_name is None:
            raise ValueError("Empty/Invalid Key or Cert filenames")
        has_key = os.path.isfile(self.key_file_name)
        has_cert = os.path.isfile(self.cert_file_name)
        if has_key and has_cert:
            return
        if has_key or has_cert:
            raise RuntimeError(f"Cannot make key:{self.key_file_name} cert:{self.cert_file_name}, one file already exists")
        acc_id = self.acc_id
        if acc_id is None:
            acc_id = str(uuid.uuid4())
        dbcrypto.create_key_pair(self.key_file_name, self.cert_file_name, acc_id)
        print(f"Dashborg created new self-signed keypair key:{self.key_file_name} cert:{self.cert_file_name} for new accountid:{acc_id}")

    def make_account_jwt(self, jwt_opts=None):
        self._setup()
        if jwt_opts is None:
            jwt_opts = self.jwt_opts
        return dbcrypto.make_account_jwt(self.key_file_name, self.acc_id, jwt_opts)

async def connect_client(config: Config) -> 'Client':
    config._setup()
    client = Client(config)
    await client._connect_grpc()
    print(f"Dashborg Initialized Client AccId:{config.acc_id} Zone:{config.zone_name} ProcName:{config.proc_name} ProcRunId:{client.proc_run_id}")
    await client._send_connect_client_message(is_reconnect=False)
    asyncio.create_task(client._run_request_stream_loop())
    return client

class Client:
    def __init__(self, config):
        self.cvar = asyncio.Condition()
        self.start_ts = dbu.dashts()
        self.proc_run_id = str(uuid.uuid4())
        self.handler_map = {}    # (panel_name, handler_type, path) -> _HandlerVal
        self.linkrt_map = {}     # path -> LinkRuntime/AppRuntime
        self.conn_id = None
        self.config = config
        self.conn = None
        self.db_service = None
        self.acc_info = {}
        self.exit_err = None

    def _get_acc_host(self) -> str:
        if not self.is_connected():
            raise NotConnectedErr
        cname = self.acc_info.get("acccname")
        if cname:
            if self.config.env != "prod":
                return f"https://{cname}:8080"
            return f"https://{cname}"
        return f"https://acc-{self.config.acc_id}.{self.config.console_host}"

    async def _connect_grpc(self):
        if self.conn is not None:
            await self.conn.close()
        if self.config.grpc_host is None:
            await self._get_grpc_server()
        addr = self.config.grpc_host + ":" + str(self.config.grpc_port)
        if self.config.verbose:
            print(f"Dashborg Connect gRPC ({addr})")
        # todo backoff config
        # todo connect params
        private_key = open(self.config.key_file_name, "rb").read()
        cert = open(self.config.cert_file_name, "rb").read()
        servercert = bytes(dbcrypto.DASHBORG_CERT, "utf-8")
        creds = grpc.ssl_channel_credentials(root_certificates=servercert, private_key=private_key, certificate_chain=cert)
        options = (("grpc.ssl_target_name_override", "5fdaf1d1-b524-4361-adcb-325d0e8ab7ee"),
                   ("grpc.keepalive_time_ms", 5000),
                   ("grpc.keepalive_timeout_ms", 5000),
                   ("grpc.keepalive_permit_without_calls", True),
                   ("grpc.max_reconnect_backoff_ms", 60000),
                   ("grpc.min_reconnect_backoff_ms", 1000),
                   ("grpc.initial_reconnect_backoff_ms", 1000),
                   ("grpc.server_handshake_timeout_ms", 10000),
                   ("grpc.max_receive_message_length", 10000000))
        # "grpc.enable_retries"
        self.conn = grpc.aio.secure_channel(target=addr, credentials=creds, options=options)
        self.db_service = dborgproto_pb2_grpc.DashborgServiceStub(self.conn)

    async def _get_grpc_server(self):
        url = f"https://{self.config.console_host}/grpc-server"
        http_timeout = aiohttp.ClientTimeout(total=2.0)
        async with aiohttp.ClientSession(timeout=http_timeout) as session:
            async with session.get(url, params={"accid": self.config.acc_id}) as resp:
                if not resp.ok:
                    raise DashborgError(f"HTTP Error getting Dashborg grpc-server status:{resp.status_code} reason:{resp.reason}")
                jsonresp = await resp.json()
                if not jsonresp.get("success"):
                    raise DashborgError(f"Cannot get gRPC Server Host (error response): {jsonresp.get('error')}")
                if not jsonresp.get("data"):
                    raise DashborgError(f"Cannot get gRPC Server Host (empty response)")
                grpcdata = jsonresp.get("data")
                if grpcdata.get("grpcserver") is None or grpcdata.get("grpcport") is None:
                    raise DashborgError(f"Cannot get gRPC Server Host (bad response)")
                self.config.grpc_host = grpcdata.get("grpcserver")
                self.config.grpc_port = int(grpcdata.get("grpcport"))

    def _conn_meta(self):
        return (("dashborg-connid", self.conn_id), ("dashborg-clientversion", CLIENT_VERSION),)

    async def _send_connect_client_message(self, is_reconnect=False):
        conn_msg = dborgproto_pb2.ConnectClientMessage()
        conn_msg.Ts = dbu.dashts()
        conn_msg.ProcRunId = self.proc_run_id
        conn_msg.AccId = self.config.acc_id
        conn_msg.ZoneName = self.config.zone_name
        conn_msg.AnonAcc = self.config.anon_acc
        conn_msg.ProcName = self.config.proc_name
        if self.config.proc_tags is not None:
            for k in self.config.proc_tags.keys():
                conn_msg.ProcTags[k] = self.config.proc_tags[k]
        conn_msg.HostData["HostName"] = socket.gethostname()
        conn_msg.HostData["Pid"] = str(os.getpid())
        conn_msg.StartTs = self.start_ts
        try:
            rtn = await self.db_service.ConnectClient(conn_msg, metadata=self._conn_meta(), timeout=DEFAULT_GRPC_TIMEOUT)
            dbu.handle_rtn_status(rtn.Status)
            self.conn_id = rtn.ConnId
            self.acc_info = json.loads(rtn.AccInfoJson)
            if not is_reconnect:
                if self.config.verbose:
                    self._log_info(f"Dashborg Client Connected, AccId:{self.config.acc_id} Zone:{self.config.zone_name} ConnId:{self.conn_id} AccType:{self.acc_info.get('acctype')}")
                else:
                    self._log_info(f"Dashborg Client Connected, AccId:{self.config.acc_id} Zone:{self.config.zone_name}")
            else:
                self._log_info(f"Dashborg Client ReConnected, AccId:{self.config.acc_id} Zone:{self.config.zone_name} ConnId:{self.conn_id}")
        except grpc.RpcError as e:
            self.conn_id = None
            raise DashborgError(e.details(), err_code="RPC", err=e)

    async def _send_force_connect_request(self):
        try:
            await self.db_service.SetPath(dborgproto_pb2.SetPathMessage(Ts=dbu.dashts()), timeout=1.0)
        except Exception as e:
            pass

    async def _run_request_stream_loop(self):
        needs_wait = False
        num_waits = 0
        try:
            while True:
                s = self.conn.get_state()
                if s == grpc.ChannelConnectivity.SHUTDOWN:
                    self._log_info(f"Dashborg stopping request loop, channel shutdown")
                    raise DashborgError("gRPC channel in SHUTDOWN state, exiting")
                if s == grpc.ChannelConnectivity.CONNECTING or s == grpc.ChannelConnectivity.TRANSIENT_FAILURE:
                    self._log_info(f"Dashborg waiting for gRPC connection")
                    await asyncio.sleep(1)
                    needs_wait = False
                    await self._send_force_connect_request()
                    continue
                if needs_wait:
                    self._log_info(f"Dashborg run_request_stream_loop needs_wait")
                    await asyncio.sleep(1)
                if self.conn_id == None:
                    await self._send_connect_client_message(is_reconnect=True)
                    needs_wait = (self.conn_id is None)
                    continue
                ec = await self._run_request_stream()
                self._log_info(f"Dashborg run_request_stream finished ec:{ec}")
                if ec == EC_BADCONNID:
                    self.conn_id = None
                    continue
                needs_wait = True
        except Exception as e:
            if self.exit_err is None:
                self.exit_err = e
        finally:
            if self.exit_err is None:
                self.exit_err = DashborgError("run request stream loop exited")
            self._log_error(f"Dashborg stopping request loop, exit error:{self.exit_err}")
            async with self.cvar:
                self.cvar.notify_all()

    async def _run_request_stream(self):
        try:
            self._log_info("Dashborg gRPC RequestStream starting")
            ending_ec = None
            req_counter = 0
            stream_msg = dborgproto_pb2.RequestStreamMessage(Ts=dbu.dashts())
            msgs = self.db_service.RequestStream(stream_msg, metadata=self._conn_meta())
            async for msg in msgs:
                if msg.Status.ErrCode == "BADCONNID":
                    ending_ec = EC_BADCONNID
                    self._log_info("Dashborg gRPC RequestStream BADCONNID")
                    break
                if msg.Status.Err:
                    ending_ec = EC_UNKNOWN
                    _log_info(f"Dashborg gRPC RequestStrem error:{msg.Status.Err} code:{msg.Status.ErrCode}")
                    break
                self._log_info(f"Dashborg gRPC request {dbu._request_msg_str(msg)}")
                req_counter += 1
                asyncio.create_task(self._dispatch_request(msg))
            if ending_ec is None:
                self._log_info("Dashborg gRPC RequestStream end of iteration")
                return EC_EOF
            return ending_ec
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                return EC_UNAVAILABLE
            self._log_info(f"Dashborg gRPC error {e}")
            return EC_UNKNOWN
        finally:
            self._log_info("Dashborg gRPC RequestStream done")

    async def _send_response_proto_rpc(self, msg):
        try:
            if not self.is_connected():
                raise NotConnectedErr
            resp = await self.db_service.SendResponse(msg, metadata=self._conn_meta(), timeout=DEFAULT_GRPC_TIMEOUT)
            dbu.handle_rtn_status(resp.Status)
        except Exception as e:
            self._log_error("Dashborg Exception sending response: {str(e)}")

    async def _send_request_response(self, preq, rtnval, is_app_request):
        if preq.is_done:
            return
        preq.is_done = True
        self._log_info(f"send_request_response {preq.path} => rtn:{rtnval}")
        msg = _make_response_msg(preq, rtnval, is_app_request)
        await self._send_response_proto_rpc(msg)

    async def _dispatch_request(self, reqmsg):
        preq = AppRequest(reqmsg=reqmsg, client=self)
        rtnval = None
        try:
            rtpath = dbu.path_no_frag(preq.path)
            rt = self.linkrt_map.get(rtpath)
            if rt is None:
                raise DashborgError("No Linked Runtime")
            rtnval = await rt.run_handler(preq)
        except Exception as e:
            self._log_error(f"Dashborg Exception in Handler {dbu.simplify_path(reqmsg.Path)} | {str(e)}")
            if preq.err is None:
                preq.err = e
            self._log_error(traceback.format_exc())
        finally:
            await self._send_request_response(preq, rtnval, reqmsg.AppRequest)
        pass
            

    def is_connected(self) -> bool:
        if self.config is None:
            return False
        if self.exit_err is not None:
            return False
        if self.conn is None:
            return False
        if self.conn_id is None:
            return False
        return True

    def global_fs_client(self) -> 'FSClient':
        return FSClient(self)

    def app_client(self) -> 'AppClient':
        return AppClient(self)

    def _log_info(self, *args):
        if self.config.use_logger:
            _dblogger.info(*args)
        elif self.config.verbose:
            print(*args)

    def _log_error(self, *args):
        if self.config.use_logger:
            _dblogger.error(*args)
        else:
            print(*args)

    async def _set_raw_path(self, path, fileopts, stream=None, runtime=None):
        try:
            await self._set_raw_path_wrap(path, fileopts, stream=stream, runtime=runtime)
            self._log_info(f"Dashborg SetPath {path} => {fileopts.short_str()}")
        except Exception as e:
            self._log_info(f"Dashborg SetPath ERROR {path} => {fileopts.short_str()} | {e}")
            raise e

    async def _set_raw_path_wrap(self, path, fileopts, stream=None, runtime=None, upload_timeout=60.0):
        if not self.is_connected():
            raise NotConnectedErr
        dbu.parse_full_path(path, allow_frag=False)
        if fileopts is None:
            raise ValueError("SetRawPath fileopts must be set")
        if not isinstance(fileopts, FileOpts):
            raise TypeError("set_raw_path fileopts must type dashborg.FileOpts")
        if fileopts.filetype == "static" and stream is None:
            raise ValueError("set_raw_path requires a stream when filetype=static")
        if fileopts.filetype != "static" and stream is not None:
            raise ValueError("set_raw_path does not allow a stream unless filetype=static")
        if not fileopts.is_link_type() and runtime is not None:
            raise ValueError(f"set_raw_path filetype is {fileopts.filetype}, no runtime allowed")
        if fileopts.allowedroles is None:
            fileopts.allowedroles = ["user"]
        fileopts_json = dbu.tojson(fileopts)
        msg = dborgproto_pb2.SetPathMessage(
            Ts=dbu.dashts(),
            Path=path,
            HasBody=(stream is not None),
            ConnectRuntime=(runtime is not None),
            FileOptsJson=fileopts_json,
        )
        uploadId = None
        uploadKey = None
        try:
            rtn = await self.db_service.SetPath(msg, metadata=self._conn_meta(), timeout=DEFAULT_GRPC_TIMEOUT)
            dbu.handle_rtn_status(rtn.Status)
            if rtn.BlobFound:
                if fileopts.is_link_type() and runtime is not None:
                    self._connect_link_runtime(path, runtime)
                return
            if rtn.BlobUploadId == "" or rtn.BlobUploadKey == "":
                raise DashborgError.validate_err("Invalid server response, no UploadId/UploadKey specified")
            uploadId = rtn.BlobUploadId
            uploadKey = rtn.BlobUploadKey
        except grpc.RpcError as e:
            raise DashborgError(e.details(), err_code="RPC", err=e)

        headers = {}
        headers["Content-Type"] = "application/octet-stream"
        headers["X-Dashborg-AccId"] = self.config.acc_id
        headers["X-Dashborg-UploadId"] = uploadId
        headers["X-Dashborg-UploadKey"] = uploadKey
        http_timeout = aiohttp.ClientTimeout(total=upload_timeout)
        async with aiohttp.ClientSession(timeout=http_timeout) as session:
            async with session.post(f"https://{self.config.console_host}/api2/raw-upload", data=stream, headers=headers) as resp:
                if not resp.ok:
                    raise DashborgError(f"HTTP Error calling raw-upload status:{resp.status_code} reason:{resp.reason}")
                jsonresp = await resp.json()
                if not jsonresp.get("success"):
                    msg = jsonresp.get("error")
                    if msg is None:
                        msg = "Unknown Error"
                    raise DashborgError(msg, err_code=jsonresp.get("errcode"), perm_err=jsonresp.get("permerr"))
        
    def _connect_link_runtime(self, path, runtime):
        if runtime is None or not isinstance(runtime, (LinkRuntime, AppRuntime)):
            raise TypeError("runtime must be type LinkRuntime/AppRuntime")
        dbu.parse_full_path(path)
        self.linkrt_map[path] = runtime

    def _unlink_runtime(self, path):
        self.linkrt_map.pop(path, None)

    def _reconnect_links(self):
        linkpaths = self.linkrt_map.copy().keys()
        for path in linkpaths:
            try:
                msg = dborgproto_pb2.ConnectLinkMessage(Ts=dbu.dashts(), Path=path)
                self.db_service.ConnectLink(msg, metadata=self._conn_meta(), timeout=DEFAULT_GRPC_TIMEOUT)
                self._log_info(f"Dashborg Client ReConnected link: {dbu.simplify_path(path)}")
            except Exception as e:
                self._log_error(f"Dashborg Client Error reconnecting link: {e}")

    async def _file_info(self, path, diropts):
        if not self.is_connected():
            raise NotConnectedErr
        dbu.parse_full_path(path, allow_frag=False)
        msg = dborgproto_pb2.FileInfoMessage(Ts=dbu.dashts(), Path=path)
        if diropts is not None:
            msg.DirOptsJson = json.dumps(diropts)
        resp = await self.db_service.FileInfo(msg, metadata=self._conn_meta(), timeout=DEFAULT_GRPC_TIMEOUT)
        dbu.handle_rtn_status(resp.Status)
        if resp.FileInfoJson is None or resp.FileInfoJson == "":
            return []
        return json.loads(resp.FileInfoJson)

    async def _remove_path(self, path, remove_app=False):
        if not self.is_connected():
            raise NotConnectedErr
        dbu.parse_full_path(path, allow_frag=False)
        msg = dborgproto_pb2.RemovePathMessage(Ts=dbu.dashts(), Path=path, RemoveFullApp=remove_app)
        resp = await self.db_service.RemovePath(msg, metadata=self._conn_meta(), timeout=DEFAULT_GRPC_TIMEOUT)
        dbu.handle_rtn_status(resp.Status)
        if remove_app:
            print(f"DashborgClient removed app {path.split('/')[-1]}")
        else:
            print(f"DashborgClient removed path {path}")

    async def shutdown(self, exit_err=None):
        if exit_err is None:
            exit_err = DashborgError("Client.shutdown() method called")
        if self.exit_err is None:
            self.exit_err = exit_err
        try:
            self.conn.close()
        except:
            pass
        async with self.cvar:
            self.cvar.notify_all()

    async def wait_for_shutdown(self):
        async with self.cvar:
            while True:
                await self.cvar.wait()
                if self.exit_err is not None:
                    break
        return self.exit_err

class FileOpts:
    def __init__(self, filetype: str = None, sha256: str = None, size: int = None, mimetype: str = None, allowedroles: list = ["user"], editroles: list = None, display: str = None, metadata_json: str = None, metadata=None, description: str = None, mkdirs: bool = False, hidden: bool = False, appconfig: str = None):
        self.filetype = filetype
        self.sha256 = sha256
        self.size = size
        self.mimetype = mimetype
        self.allowedroles = allowedroles
        self.editroles = editroles
        self.display = display
        if metadata is not None:
            self.metadata = dbu.tojson(metadata)
        else:
            self.metadata = metadata_json
        self.mkdirs = mkdirs
        self.hidden = hidden
        self.appconfig = appconfig

    def short_str(self):
        mimetype = ""
        if self.mimetype is not None:
            mimetype = ":" + self.mimetype
        return f"{self.filetype}{mimetype}"

    def is_link_type(self):
        return self.filetype == "rt-link" or self.filetype == "rt-app-link"

    def validate(self):
        pass

class FSClient:
    def __init__(self, client, root_path=""):
        self.client = client
        self.root_path = root_path
        
    async def set_raw_path(self, path: str, fileopts: FileOpts, stream=None, runtime=None):
        if path is None or path == "" or path[0] != '/':
            raise ValueError("Path must begin with '/'")
        await self.client._set_raw_path(self.root_path+path, fileopts, stream=stream, runtime=runtime)

    async def set_json_path(self, path: str, data, fileopts: FileOpts = None, *, serializefn=None, jsondumps=None, raw_json=None, jsondumpskwargs=None):
        json_data = dbu.tojson(data, serializefn=serializefn, jsondumps=jsondumps, raw_json=raw_json, jsondumpskwargs=jsondumpskwargs)
        stream = io.StringIO(json_data)
        if fileopts is None:
            fileopts = FileOpts()
        await update_fileopts_from_stream(stream, fileopts)
        if fileopts.mimetype is None:
            fileopts.mimetype = "application/json"
        fileopts.filetype = "static"
        await self.set_raw_path(path, fileopts, stream=stream)

    async def set_static_path(self, path, fileopts: FileOpts, *, strval: str = None, bytesval: bytes = None, stream=None, file_name: str = None, watch: bool = False):
        if watch and file_name is None:
            raise ValueError("set_static_path: can only set watch with a file_name")
        if file_name is not None:
            stream = await aiofiles.open(file_name, "rb")
        elif stream is not None:
            pass
        elif strval is not None:
            stream = io.StringIO(strval)
        elif bytesval is not None:
            stream = io.BytesIO(bytesval)
        if stream is None:
            raise ValueError("set_static_path: Must provide strval, bytesval, file_name or stream")
        if fileopts is None:
            raise ValueError("set_static_path: Must provide fileopts (set at least mimetype)")
        if not isinstance(fileopts, FileOpts):
            raise TypeError("set_static_path: fileopts must be type dashborg.FileOpts")
        fileopts.filetype = "static"
        await update_fileopts_from_stream(stream, fileopts)
        await self.set_raw_path(path, fileopts, stream=stream)
        if watch:
            async def watch_callback():
                await self.set_static_path(path, fileopts, file_name=file_name)
                return
            watch_file(file_name, asyncio.get_running_loop(), watch_callback)

    async def link_runtime(self, path: str, runtime, fileopts: FileOpts = None):
        if fileopts is None:
            fileopts = FileOpts()
        fileopts.filetype = "rt-link"
        if runtime is None:
            raise ValueError("Must pass a runtime to link_runtime()")
        if not isinstance(runtime, LinkRuntime):
            raise TypeError(f"Must pass a type LinkRuntime to link_runtime() type={type(runtime)}")
        await self.set_raw_path(path, fileopts, runtime=runtime)

    async def link_app_runtime(self, path: str, runtime, fileopts: FileOpts = None):
        if fileopts is None:
            fileopts = FileOpts()
        fileopts.filetype = "rt-app-link"
        if runtime is None:
            raise ValueError("Must pass a runtime to link_app_runtime()")
        if not isinstance(runtime, AppRuntime):
            raise TypeError(f"Must pass a type AppRuntime to link_app_runtime() type={type(runtime)}")
        await self.set_raw_path(path, fileopts, runtime=runtime)

    def make_path_url(self, path: str, jwt_opts: dict = None, no_jwt: bool = False):
        dbu.parse_full_path(self.root_path+path)
        path_link = self.client._get_acc_host() + "/@fs" + self.root_path + path
        if no_jwt:
            return path_link
        jwt_token = self.client.config.make_account_jwt(jwt_opts)
        return f"{path_link}?jwt={jwt_token}"

    async def file_info(self, path: str):
        if path is None or path == "" or path[0] != "/":
            raise ValueError("file_info: Invalid Path, must begin with '/'")
        finfos = await self.client._file_info(self.root_path+path, None)
        if len(finfos) == 0:
            return None
        return finfos[0]

    async def dir_info(self, path: str, role_list: list = ["*"], show_hidden: bool = False, recursive: bool = False):
        if path is None or path == "" or path[0] != "/":
            raise ValueError("file_info: Invalid Path, must begin with '/'")
        diropts = {
            "rolelist": role_list,
            "showhidden": show_hidden,
            "recursive": recursive,
        }
        finfos = await self.client._file_info(self.root_path+path, diropts)
        return finfos

    async def remove_path(self, path: str):
        if path is None or path == "" or path[0] != "/":
            raise ValueError("file_info: Invalid Path, must begin with '/'")
        await self.client._remove_path(fs.root_path+path)
    

class AppClient:
    def __init__(self, client: Client):
        if not isinstance(client, Client):
            raise TypeError("Invalid Client passed to AppClient")
        self.client = client

    def new_app(self, app_name: str):
        return App(app_name, client=self.client)

    def new_app_from_config(self, app_config: dict):
        return App(app_config["appname"], client=self.client, config=app_config)

    async def load_app(self, app_name: str, create: bool = False):
        app_path = app_path_from_name(app_name)
        finfo = await self.client.global_fs_client().file_info(app_path)
        if finfo is None:
            return self.new_app(app_name) if create else None
        if finfo["filetype"] != "app" or not finfo.get("appconfig"):
            raise ValueError(f"file at path {app_path} is not a valid app, filetype={finfo['filetype']}")
        app_config = json.loads(finfo.get("appconfig"))
        return self.new_app_from_config(app_config)

    async def write_app(self, app: 'App', connect: bool = False):
        app_config = app.get_app_config()
        if connect and app.has_external_runtime():
            raise ValueError(f"App has an external runtime path '{app.get_runtime_path()}', cannot connect")
        if connect and app_config.get("runtimepath") is None:
            raise ValueError(f"App has undefined runtime path, cannot connect")
        if connect and app.runtime is None:
            raise ValueError(f"App has undefined runtime, cannot connect")
        roles = app_config["allowedroles"]
        fs = app.client.global_fs_client()
        app_config_json = json.dumps(app_config)
        await fs.set_raw_path(app.get_app_path(), FileOpts(filetype="app", mimetype="application/x-dashborg+json", allowedroles=roles, appconfig=app_config_json))
        html_path = app_config.get("htmlpath")
        if (html_path is not None) and app._has_static_html():
            html_fileopts = FileOpts(mimetype="text/html", allowedroles=roles)
            await fs.set_static_path(html_path, html_fileopts, strval=app.html_str, file_name=app.html_file_name, stream=app.html_stream, watch=app.html_watch)
        if connect:
            runtime_path = app_config.get("runtimepath")
            runtime_fileopts = FileOpts(allowedroles=roles)
            await fs.link_app_runtime(runtime_path, app.runtime, fileopts=runtime_fileopts)
        app_name = app_config.get("appname")
        app_link = self.make_app_url(app_name)
        print(f"Dashborg App Link [{app_name}]: {app_link}")

    def make_app_url(self, app_name: str, jwt_opts: dict = None, no_jwt: bool = None):
        if app_name is None or app_name == "":
            raise ValueError("app_name must be set / not empty")
        app_link = self.client._get_acc_host() + dbu.make_app_path(app_name, zone_name=self.client.config.zone_name)
        if no_jwt is None:
            no_jwt = self.client.config.no_jwt
        if no_jwt:
            return app_link
        jwt_token = self.client.config.make_account_jwt()
        return f"{app_link}?jwt={jwt_token}"

    async def remove_app(self, app_name: str):
        app_path = app_path_from_name(app_name)
        await self.client._remove_path(app_path, remove_app=True)
    

async def update_fileopts_from_stream(stream, fileopts):
    if fileopts is None or not isinstance(fileopts, FileOpts):
        raise ValueError("FileOpts must be passed to update_fileopts_from_stream (set at least mimetype)")
    if not callable(getattr(stream, "seekable", None)) or not stream.seekable():
        raise ValueError("Stream must be seekable to set sha256 hash in FileOpts")
    await dbu.async_eval(stream.seek(0, 0))
    sha_val, size = await dbcrypto.compute_sha256_stream(stream)
    await dbu.async_eval(stream.seek(0, 0))
    fileopts.filetype = "static"
    fileopts.sha256 = sha_val
    fileopts.size = size

class _HandlerVal:
    def __init__(self, name, handlerfn, opts):
        self.handlerfn = handlerfn
        self.handler_info = {}
        self.name = name
        self.pure_handler = opts.pure_handler
        self.hidden = opts.hidden
        self.display = opts.display
        self.form_display = opts.form_display
        self.results_display = opts.results_display
        self.description = opts.description

    def get_handler_info(self):
        rtn = {}
        rtn["name"] = self.name
        if self.pure_handler:
            rtn["pure"] = True
        if self.hidden:
            rtn["hidden"] = True
        if self.display is not None:
            rtn["display"] = self.display
        if self.form_display is not None:
            rtn["formdisplay"] = self.form_display
        if self.results_display is not None:
            rtn["resultsdisplay"] = self.results_display
        if self.description is not None:
            rtn["description"] = self.description
        _add_handler_typeinfo(self.name, self.handlerfn, rtn)
        return rtn

    def to_dict(self):
        return self.get_handler_info()

class _BaseRuntime:
    def __init__(self, is_app_runtime):
        self.handlers = {}
        self.is_app_runtime = is_app_runtime
        self.handler("@typeinfo", self._typeinfo_handler, pure_handler=True, hidden=True)
        pass

    def _typeinfo_handler(self, req):
        rtn = []
        for handler_name, hval in self.handlers.items():
            hinfo = hval.get_handler_info()
            if hinfo.get("hidden"):
                continue
            rtn.append(hinfo)
        return rtn

    def _make_handlerval(self, handler_name, handlerfn, opts: 'HandlerOpts' = None, pure_handler: bool = None, hidden: bool = None, display: str = None):
        if not callable(handlerfn):
            raise TypeError("handlerfn must be callable")
        if not dbu.is_path_frag_valid(handler_name):
            raise ValueError("handler_name is not valid")
        if opts is None:
            opts = HandlerOpts()
        if not isinstance(opts, HandlerOpts):
            raise TypeError("opts must be type HandlerOpts")
        if pure_handler is not None:
            opts.pure_handler = pure_handler
        if hidden is not None:
            opts.hidden = hidden
        if display is not None:
            opts.display = display
        hval = _HandlerVal(handler_name, handlerfn, opts)
        return hval

    def handler(self, handler_name: str, handlerfn: Callable, opts: 'HandlerOpts' = None, pure_handler: bool = None, hidden: bool = None, display: str = None):
        hval = self._make_handlerval(handler_name, handlerfn, opts=opts, pure_handler=pure_handler, hidden=hidden, display=display)
        self.handlers[handler_name] = hval

    async def run_handler(self, req):
        (_, _, pathfrag) = dbu.parse_full_path(req.path)
        if pathfrag is None:
            pathfrag = "@default"
        hval = self.handlers.get(pathfrag)
        if hval is None:
            raise DashborgError(f"No handler found for '{pathfrag}'", err_code="NOHANDLER")
        if req.request_method == "GET" and not hval.pure_handler:
            raise DashborgError(f"GET/data request to non-pure handler '{pathfrag}'")
        hargs = _make_handler_args(hval.handlerfn, hval.get_handler_info(), req)
        hrtn = hval.handlerfn(*hargs)
        hrtn = await dbu.async_eval(hrtn)
        return hrtn


class LinkRuntime(_BaseRuntime):
    def __init__(self):
        super().__init__(is_app_runtime=False)

class AppRuntime(_BaseRuntime):
    def __init__(self):
        super().__init__(is_app_runtime=True)
        self.page_handlers = {}
        self.handler("@pageinit", self._page_init_handler, hidden=True, pure_handler=True)

    def html_handler(self, handlerfn: Callable, **kwargs):
        self.handler("@html", handlerfn, **kwargs)

    def init_handler(self, handlerfn: Callable, **kwargs):
        self.handler("@init", handlerfn, **kwargs)

    def page_handler(self, page_name: str, handlerfn: Callable):
        hval = self._make_handlerval(f"@pageinit-{page_name}", handlerfn)
        self.page_handlers[page_name] = hval

    async def _page_init_handler(self, req, page_name):
        hval = self.page_handlers.get(page_name)
        if hval is None:
            return
        hargs = _make_handler_args(hval.handlerfn, hval.get_handler_info(), req)
        hrtn = hval.handlerfn(*hargs)
        hrtn = await dbu.async_eval(hrtn)
        return hrtn


# def test(fn):
#     @functools.wraps(fn)
#     def wrapper(*args, **kwargs):
#         return fn(*args, **kwargs)
#     return wrapper


class AppRequest:
    def __init__(self, *, reqmsg=None, client=None):
        if not isinstance(reqmsg, dborgproto_pb2.RequestMessage):
            raise TypeError("RequestMessage required")
        if not isinstance(client, Client):
            raise TypeError("AppRequest requires Client")
            
        self.start_time = datetime.datetime.now()
        self.req_id = reqmsg.ReqId
        self.request_type = reqmsg.RequestType
        self.request_method = reqmsg.RequestMethod
        self.path = reqmsg.Path
        self.app_name = dbu.app_name_from_path(reqmsg.Path)
        self.fe_client_id = reqmsg.FeClientId
        self.data_json = reqmsg.JsonData
        self.app_state_json = reqmsg.AppStateData
        self.auth_data_json = reqmsg.AuthData
        self.client = client
        self.data = None
        self.app_state = None
        self.err = None
        self.rr_actions = []
        self.is_done = False
        self.is_app_request = reqmsg.AppRequest
        self.auth_atom = None
        if reqmsg.AuthData:
            self.auth_atom = json.loads(reqmsg.AuthData)
        self.app_state = None
        if reqmsg.AppStateData:
            self.app_state = json.loads(reqmsg.AppStateData)
        self.data = None
        if reqmsg.JsonData:
            self.data = json.loads(reqmsg.JsonData)
        self.json_opts = client.config.json_opts

    def set_data(self, path: str, data):
        if not self.is_app_request:
            raise RuntimeError(f"Cannot call set_data, path={path}, in pure_handler (only for app requests)")
        if self.is_done:
            raise RuntimeError(f"Cannot call set_data, path={path}, Request is already done")
        jsondata = dbu.tojson(data, **self.json_opts)
        rr = dborgproto_pb2.RRAction(
            Ts=dbu.dashts(),
            ActionType="setdata",
            Selector=path,
            JsonData=jsondata,
        )
        self.rr_actions.append(rr)

    def invalidate_data(self, path_regexp_str: str):
        if self.is_done:
            raise RuntimeError(f"Cannot call invalidate_data(), path={path}, Request is already done")
        rr = dborgproto_pb2.RRAction(Ts=dbu.dashts(), ActionType="invalidate", Selector=path_regexp_str)
        self.rr_actions.append(rr)

    def set_html_page(self, html_page: str):
        self.set_data("$state.dashborg.htmlpage", html_page)

    def nav_to_page(self, page_name: str, params=None):
        rr = dborgproto_pb2.RRAction(
            Ts=dbu.dashts(),
            ActionType="navto",
            Selector=page_name,
        )
        if params is not None:
            json_data = dbu.tojson(params, **self.json_opts)
            rr.JsonData = json_data
        self.rr_actions.append(rr)

    def get_page_name(self):
        return dbu.recursive_get(self.app_state, "dashborg", "apppage")
        

def _err_to_errortype(e):
    if e is None:
        return None
    if isinstance(e, DashborgError):
        return dborgproto_pb2.ErrorType(Err=str(e), ErrCode=e.err_code, PermErr = e.perm_err)
    if isinstance(e, ValueError) or isinstance(e, TypeError):
        return dborgproto_pb2.ErrorType(Err=str(e), ErrCode="NOTVALID", PermErr = True)
    return dborgproto_pb2.ErrorType(Err=str(e))

def _make_response_msg(preq, rtnval, is_app_request):
    msg = dborgproto_pb2.SendResponseMessage(
        Ts = dbu.dashts(),
        ReqId = preq.req_id,
        RequestType = preq.request_type,
        Path = preq.path,
        FeClientId = preq.fe_client_id,
        ResponseDone = True,
    )
    if preq.err is not None:
        if preq.err is not None:
            msg.Err.CopyFrom(_err_to_errortype(preq.err))
        return msg
    try:
        rtn_rra = []
        if rtnval is not None:
            rtn_rra = _rtnval_to_rra(rtnval, preq.json_opts)
        if is_app_request:
            msg.Actions.extend(preq.rr_actions)
        msg.Actions.extend(rtn_rra)
        return msg
    except Exception as e:
        msg.Err.CopyFrom(_err_to_errortype(e))
        return msg

class BlobReturn:
    def __init__(self, mimetype: str, stream):
        if not mimetype or not isinstance(mimetype, str):
            raise TypeError("BlobReturn mimetype must be a str")
        if not dbu.is_mimetype_valid(mimetype):
            raise ValueError("BlobReturn invalid mimetype")
        if stream is None:
            raise TypeError("BlobReturn stream must be set")
        self.mimetype = mimetype
        self.stream = stream
        

def _rtnval_to_rra(rtnval, json_opts=None):
    if rtnval is None:
        return []
    if json_opts is None:
        json_opts = {}
    if isinstance(rtnval, BlobReturn):
        return _blobreturn_to_rra(rtnval)
    jsondata = dbu.tojson(rtnval, serializefn=json_opts.get("serializefn"), jsondumps=json_opts.get("jsondumps"), jsondumpskwargs=json_opts.get("jsondumpskwargs"))
    rr = dborgproto_pb2.RRAction(
        Ts = dbu.dashts(),
        ActionType = "setdata",
        Selector = "@rtn",
        JsonData = jsondata,
    )
    return [rr]

def _blobreturn_to_rra(blob):
    first = True
    total_size = 0
    rra = []
    while True:
        buf = blob.stream.read(BLOB_READ_SIZE)
        if buf is None or len(buf) == 0:
            break
        if isinstance(buf, str):
            buf = buf.encode("utf-8")
        if not isinstance(buf, bytes):
            raise ValueError("BlobReturn stream.read() must produce str or bytes")
        total_size += len(buf)
        rr = dborgproto_pb2.RRAction(
            Ts = dbu.dashts(),
            Selector = "@rtn",
            BlobBytes = buf,
        )
        if first:
            rr.ActionType = "blob"
            rr.BlobMimeType = blob.mimetype
            first = False
        else:
            rr.ActionType = "blobext"
        rra.append(rr)
    if total_size > MAX_RRA_BLOB_SIZE:
        raise ValueError("BlobReturn too large, max-size:{MAX_RRA_BLOB_SIZE}, blob-size:{total_size}")
    return rra

class App:
    def __init__(self, app_name, *, client, config=None):
        if not isinstance(client, Client):
            raise TypeError("client must be type=dashborg.Client")
        if config is None:
            config = {}
        self.client = client
        self.app_name = app_name
        self.app_title = config.get("apptitle")
        self.app_vis_type = config.get("appvistype")
        self.app_vis_order = config.get("appvisorder")
        if "allowedroles" in config:
            self.allowed_roles = config.get("allowedroles")
        else:
            self.allowed_roles = ["user"]
        self.offline_access = config.get("offlineaccess", False)
        self.init_required = config.get("initrequired", False)
        self.pages_enabled = config.get("pagesenabled", False)
        self.runtime = AppRuntime()
        self._clear_html_opts()
        # set runtime_path
        self.runtime_ext_path = None
        config_runtime_path = config.get("runtimepath")
        if config_runtime_path != self._default_runtime_path():
            self.runtime_ext_path = config_runtime_path
        # set htmlpath
        config_html_path = config.get("htmlpath")
        if config_html_path == self.get_runtime_path() + ":@html":
            self.html_from_runtime = True
        elif config_html_path != self.get_app_path() + "/_/html":
            self.html_ext_path = config_html_path

    def get_app_config(self) -> dict:
        rtn = {
            "appname": self.app_name,
            "clientversion": CLIENT_VERSION,
            "allowedroles": self.allowed_roles,
            "initrequired": self.init_required,
            "offlineaccess": self.offline_access,
            "htmlpath": self.get_html_path(),
            "runtimepath": self.get_runtime_path(),
        }
        if self.app_title is not None:
            rtn["apptitle"] = self.app_title
        if self.app_vis_type is not None:
            rtn["appvistype"] = self.app_vis_type
        if self.app_vis_order is not None:
            rtn["appvisorder"] = self.app_vis_order
        if self.pages_enabled:
            rtn["pagesenabled"] = True
        return rtn

    def get_app_path(self) -> str:
        return f"/_/apps/{self.app_name}"

    def get_html_path(self) -> str:
        if self.html_from_runtime:
            return self.get_runtime_path() + "/_/runtime:@html"
        if self.html_ext_path is not None:
            return self.html_ext_path
        return self.get_app_path() + "/_/html"

    def _default_runtime_path(self):
        return self.get_app_path() + "/_/runtime"

    def has_external_runtime(self) -> bool:
        return self.get_runtime_path() != self._default_runtime_path()

    def get_runtime_path(self) -> str:
        if self.runtime_ext_path is not None:
            return self.runtime_ext_path
        return self.get_app_path() + "/_/runtime"

    def _clear_html_opts(self):
        self.html_watch = False
        self.html_str = None
        self.html_file_name = None
        self.html_from_runtime = False
        self.html_ext_path = None
        self.html_stream = None

    def set_init_required(self, init_required: bool):
        """If True, loading the app will call the init handler.  
        An error returned from the init handler will cause the app to not load. 
        If init_required is set, your app will not be available offline
        """
        self.init_required = init_required

    def set_pages_enabled(self, enabled: bool):
        """Set to True to enable app paging"""
        self.pages_enabled = enabled

    def set_allowed_roles(self, *roles: str):
        """Sets allowed roles"""
        self.allowed_roles = roles

    def set_app_title(self, title: str):
        """Sets app title"""
        self.app_title = title

    def set_app_visibility(self, vis_type: str, vis_order: float = 0.0):
        """Sets app visibility.
        vis_type -- either "hidden", "default", or "visible". 
        vis_order -- the order apps are shown.  negative values are okay.  0/None is special and will always sort to the end.
        """
        self.app_vis_type = vis_type
        self.app_vis_order = vis_order

    def set_html(self, *, html: str = None, file_name: str = None, ext_path: str = None, runtime=False, stream=None, watch: bool = False):
        """Sets the app's HTML.  The HTML options are exclusive, only set one (except for watch).  HTML is not
        sent to the Dashborg server until write_app() is called

        html      -- a string with the HTML content
        file_name -- a file path to read the HTML content from
        ext_path  -- a Dashborg path to read the HTML content from
        runtime   -- set to True to read the HTML from /@app:@html (runtime's html_handler)
        stream    -- a stream (async or regular) to read the HTML from
        watch     -- only valid with the file_name parameter.  if set, the HTML will be re-uploaded whenever a change is detected in the file.
        """
        if watch and file_name is None:
            raise ValueError("set_html: can only set watch with a file_name")
        self._clear_html_opts()
        if file_name is not None:
            self.html_file_name = file_name
            self.html_watch = watch
            return
        if html is not None:
            self.html_str = html
            return
        if path is not None:
            self.html_ext_path = path
            return
        if runtime:
            self.html_from_runtime = True
            return
        if stream:
            self.html_stream = stream
            return

    def _has_static_html(self):
        return (self.html_str is not None) or (self.html_file_name is not None) or (self.html_stream is not None)

    def app_fs_client(self) -> 'FSClient':
        if not dbu.is_app_name_valid(self.app_name):
            raise ValueError(f"Invalid app_name '{self.app_name}'")
        return FSClient(self.client, root_path=self.get_app_path())

class _WatchdogHandler(FileSystemEventHandler):
    def __init__(self, file_path, loop, callback_fn):
        self.file_path = file_path
        self.loop = loop
        self.callback_fn = callback_fn
    
    def on_modified(self, event):
        if event.src_path != self.file_path:
            return
        print(f"modified callback:{self.callback_fn} iscoroutine:{inspect.iscoroutinefunction(self.callback_fn)}")
        if inspect.iscoroutinefunction(self.callback_fn):
            cor = self.callback_fn()
            asyncio.run_coroutine_threadsafe(cor, self.loop)
        else:
            self.loop.call_soon_threadsafe(self.callback_fn)


def watch_file(file_name, loop, callback_fn):
    global watchdog_observer
    if watchdog_observer is None:
        watchdog_observer = WatchdogObserver()
        watchdog_observer.start()
    esc_file_name = glob.escape(os.path.abspath(file_name))
    dir_name = os.path.dirname(esc_file_name)
    handler = _WatchdogHandler(esc_file_name, loop, callback_fn)
    watchdog_observer.schedule(handler, dir_name, recursive=False)

class HandlerOpts:
    def __init__(self, *, hidden=False, pure_handler=False, description=None, display=None, form_display=None, results_display=None):
        self.hidden = hidden
        self.pure_handler = pure_handler
        self.display = display
        self.form_display = form_display
        self.results_display = results_display
        self.description = description

def _add_handler_typeinfo(name, hfn, hinfo):
    sig = inspect.signature(hfn)
    if hinfo.get("description") is None:
        hinfo["description"] = inspect.getdoc(hfn)
    if sig.return_annotation != inspect.Signature.empty:
        hinfo["rtntype"] = _make_typeinfo(None, sig.return_annotation)
    params = list(sig.parameters.values())
    hinfo["paramstype"] = []
    _check_first_params(params, hinfo)
    for p in params:
        tinfo = _make_typeinfo(p)
        hinfo["paramstype"].append(tinfo)

def _check_first_params(params, hinfo):
    if len(params) == 0:
        return
    p = params[0]
    if p.name == "req" or p.annotation == AppRequest:
        params.pop(0)
        hinfo["reqparam"] = True
    if len(params) == 0:
        return
    p = params[0]
    if p.name == "appstate" or p.name == "app_state":
        if hinfo.get("pure"):
            raise ValueError(f"Invalid handlerfn, 'pure' functions cannot accept an app_state parameter")
        params.pop(0)
        hinfo["appstateparam"] = True
        

def _make_typeinfo(param, atype=None):
    rtn = {}
    if param is not None:
        rtn["name"] = param.name
        if param.default != inspect.Parameter.empty:
            rtn["optional"] = True
        atype = param.annotation
    if atype is not None and atype != inspect.Parameter.empty:
        if atype == int:
            rtn["type"] = "int"
        elif atype == str:
            rtn["type"] = "string"
        elif atype == float:
            rtn["type"] = "float"
        elif atype == bool:
            rtn["type"] = "bool"
        elif atype == list or atype == tuple:
            rtn["type"] = "array"
        elif atype == dict:
            rtn["type"] = "map"
        else:
            raise ValueError(f"Invalid type annotation for JSON unmarshalling: {atype}")
    return rtn

def _make_handler_args(hfn, hinfo, req):
    args = []
    if hinfo.get("reqparam"):
        args.append(req)
    if hinfo.get("appstateparam"):
        args.append(req.app_state)
    sig = inspect.signature(hfn)
    num_args = len(sig.parameters)
    data_array = []
    if req.data is None:
        data_array = []
    elif isinstance(req.data, list):
        data_array = req.data
    else:
        data_array = [req.data]
    if len(args) + len(data_array) > num_args:
        data_array = data_array[0:num_args-len(args)]
    args.extend(data_array)
    return args

def app_path_from_name(app_name):
    return f"/_/apps/{app_name}"

