# dashborg utility functions

import time
import json
import uuid
import io
import datetime
import re
import inspect
from functools import reduce

try:
    import dataclasses
except ImportError:
    # Python < 3.7
    dataclasses = None  # type: ignore

def dashts():
    return int(round(time.time()*1000))

def default_string(*args):
    for s in args:
        if s is not None and s != "":
            return s
    return None

class DashborgError(Exception):
    def __init__(self, msg, err_code=None, perm_err=False, err=None):
        self.msg = msg
        self.err_code = err_code
        self.perm_err = perm_err
        self.err = err

    def validate_err(msg, err=None):
        return DashborgError(msg, err_code="NOTVALID", perm_err=True, err=err)

def handle_rtn_status(rtnstatus):
    if rtnstatus.Success:
        return
    if rtnstatus.Err is not None and rtnstatus.Err != "":
        raise DashborgError(rtnstatus.Err, err_code=rtnstatus.ErrCode, perm_err=rtnstatus.PermErr)
    raise DashborgError("Unspecified Error")

def recursive_serialize(obj, sfn):
    obj = sfn(obj)
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool, bytes)):
        return obj
    elif isinstance(obj, dict):
        data = {}
        for (k, v) in obj.items():
            if not callable(v):
                data[k] = recursive_serialize(v, sfn)
        return data
    elif hasattr(obj, "__iter__"):
        return [recursive_serialize(v, sfn) for v in obj]
    return obj

def serialize(obj):
    if isinstance(obj, dict):
        return obj
    elif isinstance(obj, str):
        return obj
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif dataclasses and dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    elif isinstance(obj, datetime.datetime):
        return int(round(obj.timestamp()*1000))
    elif isinstance(obj, datetime.date):
        return str(obj)
    elif hasattr(obj, "to_dict"):
        return obj.to_dict()
    elif hasattr(obj, "__dict__"):
        data = {}
        for (k, v) in obj.__dict__.items():
            if not k.startswith("_"):
                data[k] = v
        return data
    elif hasattr(obj, '__slots__'):
        data = {}
        for name in getattr(obj, '__slots__'):
            if not name.startswith("_"):
                data[name] = getattr(obj, name)
        return data
    elif hasattr(obj, "_asdict"):
        return obj._asdict()
    elif hasattr(obj, "_ast"):
        return obj._ast()
    return obj

def tojson(data, *, serializefn=None, jsondumps=None, raw_json=None, jsondumpskwargs={}):
    if raw_json is not None:
        return str(raw_json)
    if jsondumps is None:
        jsondumps = json.dumps
    if serializefn is None:
        serializefn = serialize
    if jsondumpskwargs is None:
        jsondumpskwargs = {}
    data = recursive_serialize(data, serializefn)
    json_data = jsondumps(data, **jsondumpskwargs)
    return json_data

_FULLPATH_MAX = 120
_fullpath_re = re.compile(r"^(?:/@([a-zA-Z_][a-zA-Z0-9=_.-]*))?(/[a-zA-Z0-9._/-]*)?(?:[:](@?[a-zA-Z][a-zA-Z0-9_-]*))?$")

def parse_full_path(path, allow_frag=True):
    if path is None or path == "":
        raise ValueError("Path cannot be empty")
    if not isinstance(path, str):
        raise TypeError(f"Path must be a str type:{type(path)}")
    if path[0] != "/":
        raise ValueError("Path must start with '/'")
    if len(path) > _FULLPATH_MAX:
        raise ValueError("Path too long")
    match = _fullpath_re.match(path)
    if match is None:
        raise ValueError(f"Invalid path '{path}'")
    pathns, pathmain, pathfrag = match.group(1), match.group(2), match.group(3)
    if pathmain is None:
        pathmain = "/"
    if pathfrag is not None and not allow_frag:
        raise ValueError("Path does not allow path-fragment")
    return (pathns, pathmain, pathfrag)

_path_frag_re = re.compile(r"^@?[a-zA-Z_][a-zA-Z0-9_-]*$")

def is_path_frag_valid(s):
    if s is None or s == "" or len(s) > 30:
        return False
    match = _path_frag_re.match(s)
    return match is not None

def is_path_valid(s, allow_frag=True):
    try:
        parse_full_path(s, allow_frag=allow_frag)
        return True
    except (TypeError, ValueError):
        return False

def _request_msg_str(reqmsg):
    if not reqmsg.Path:
        return "[no-path]"
    return f"{reqmsg.RequestMethod:>4} {simplify_path(reqmsg.Path)}"

_path_app_name_re = re.compile(r"^/_/apps/([a-zA-Z][a-zA-Z0-9_.-]*)(?:/|$)")

def app_name_from_path(fullpath):
    match = _path_app_name_re.match(fullpath)
    if match is None:
        return None
    return match.group(1)

def _app_path_from_name(app_name):
    return f"/_/apps/{app_name}"
        
def simplify_path(fullpath, app_name=None):
    try:
        (pathns, path, pathfrag) = parse_full_path(fullpath, allow_frag=True)
        if pathns:
            return fullpath
        path_app_name = app_name_from_path(path)
        if path_app_name is None:
            return fullpath
        rtn_path = ""
        app_path = _app_path_from_name(path_app_name)
        path = path.replace(app_path, "", 1)
        if path_app_name == app_name:
            rtn_path = "/@app"
        else:
            rtn_path = f"/@app={path_app_name}"
        frag_str = ""
        if pathfrag:
            frag_str = ":" + pathfrag
        if path == "/_/runtime" and pathfrag:
            return rtn_path + frag_str
        return rtn_path + path + frag_str
    except:
        return fullpath

def path_no_frag(fullpath):
    (pathns, path, _) = parse_full_path(fullpath, allow_frag=True)
    ns_str = ""
    if pathns:
        ns_str = f"/@{pathns}"
    return ns_str + path

_mimetype_re = re.compile(r"^[a-z0-9.-]+/[a-zA-Z0-9._+-]+$")

def is_mimetype_valid(s):
    if s is None or len(s) > 80:
        return False
    match = _mimetype_re.match(s)
    return match is not None

_app_name_re = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*$")

def is_app_name_valid(s):
    if s is None or len(s) > 50:
        return False
    match = _app_name_re.match(s)
    return match is not None
    
def make_app_path(app_name, zone_name="default"):
    if zone_name == "default" and app_name == "default":
        return "/"
    if zone_name == "default":
        return f"/app/{app_name}"
    if app_name == "default":
        return f"/zone/{zone_name}"
    return f"/zone/{zone_name}/app/{app_name}"

def recursive_get(rootdict, *keys):
    if rootdict is None:
        return None
    return reduce(lambda d, key: d.get(key, {}), keys, rootdict)

async def async_eval(v):
    if inspect.isawaitable(v):
        return await v
    return v
