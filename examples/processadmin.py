import dashborg
import asyncio
import os
import subprocess
import psutil
import uuid
import sys
import yaml
import argparse

def first_file_exists(*files):
    for file in files:
        if os.path.isfile(file):
            return file
    raise RuntimeError(f"Cannot find any files {files}")

class TaskDef:
    def __init__(self, *, cmd=None, pidfile=None, name=None, external_logfile=None, cwd=None):
        if name is None or cmd is None:
            raise RuntimeError("TaskDef must have a name and cmd")
        self.cmd = cmd
        self.pidfile = pidfile
        self.running_pid = None
        self.name = name
        self.external_logfile = external_logfile
        self.task_id = str(uuid.uuid4())
        self.cwd = cwd
        pass

    @classmethod
    def from_dict(cls, d):
        return cls(cmd=d.get("cmd"), pidfile=d.get("pidfile"), name=d.get("name"), cwd=d.get("cwd"), external_logfile=d.get("external_logfile"))

    def detach_run(self):
        print(f"running [[{self.cmd}]]")
        pidout = None
        if self.pidfile is not None:
            pidout = open(self.pidfile, "w")
        p = subprocess.Popen(self.cmd, shell=True, start_new_session=True, close_fds=True, cwd=self.cwd)
        self.running_pid = p.pid
        del p
        if pidout is not None:
            pidout.write(str(self.running_pid) + "\n")
            pidout.close()
        return

    def get_log_contents(self, maxlen = 5000):
        fname = self.external_logfile
        if fname is None:
            return None, 0
        try:
            fsize = os.stat(fname).st_size
            fd = open(fname, "r")
            if fsize > maxlen:
                fd.seek(fsize-maxlen)
            output = fd.read()
            pos = output.find("\n")
            if fsize > maxlen and pos > 0 and pos < len(output):
                output = output[pos+1:]
            return output, fsize
        except FileNotFoundError:
            return None, 0

    def get_pid(self):
        try:
            if self.running_pid:
                return self.running_pid
            elif self.pidfile is not None:
                fd = open(self.pidfile)
                return int(fd.read())
            return None
        except:
            return None

    def unlink_pid(self):
        self.running_pid = None
        if self.pidfile and os.path.exists(self.pidfile):
            os.remove(self.pidfile)

    def get_task_info(self):
        rtn = {}
        rtn["task_id"] = self.task_id
        rtn["pid"] = self.get_pid()
        rtn["name"] = self.name
        rtn["cmd"] = self.cmd
        rtn["external_logfile"] = self.external_logfile
        rtn["pidfile"] = self.pidfile
        rtn["cwd"] = self.cwd
        if rtn.get("pid") is not None:
            try:
                p = psutil.Process(rtn["pid"])
                rtn["status"] = p.status()
                rtn["cpu_times"] = p.cpu_times()
                rtn["memory_info"] = p.memory_info()
            except psutil.NoSuchProcess:
                rtn["no_proc"] = True
        else:
            rtn["no_proc"] = True    
        return rtn

    def get_running_task_info(self):
        rtn = {}
        rtn["pid"] = self.get_pid()
        rtn["task_id"] = self.task_id
        if rtn["pid"] is not None:
            try:
                p = psutil.Process(rtn["pid"])
                rtn["status"] = p.status()
                rtn["user"] = p.username()
                rtn["create_ts"] = p.create_time()
                rtn["name"] = p.name()
                rtn["executable"] = p.exe()
                rtn["cwd"] = p.cwd()
                rtn["cmdline"] = " ".join(p.cmdline())
                crtn = []
                children = p.children(recursive=True)
                print(children)
                for child in children:
                    crtn.append(f"pid={child.pid} status={child.status()} cmd={' '.join(child.cmdline())}")
                rtn["children"] = crtn
            except psutil.NoSuchProcess:
                rtn["no_proc"] = True
        else:
            rtn["no_proc"] = True
        return rtn

    def kill_task(self, dash9):
        pid = self.get_pid()
        p = psutil.Process(pid)
        children = p.children(recursive=True)
        if dash9:
            p.kill()
            for child in children:
                child.kill()
        else:
            p.terminate()
            for child in children:
                child.terminate()
        return p.wait(timeout=2.0)


class AdminModel:
    def __init__(self, *, demo_mode=None):
        self.tasks = []
        self.demo_mode = True if demo_mode is not None else False
        pass

    def add_task(self, task):
        self.tasks.append(task)

    def find_task(self, id):
        for task in self.tasks:
            if task.task_id == id:
                return task
        raise RuntimeError(f"Cannot Find Task Id {id} in tasks")
    
    async def root_handler(self, req):
        file = first_file_exists("examples/processadmin.html", "processadmin.html")
        await req.set_html_from_file(file)
        return

    async def get_tasks(self, req):
        rtn = []
        for task in self.tasks:
            rtn.append(task.get_task_info())
        return rtn

    async def run_task(self, req):
        task = self.find_task(req.data)
        task.detach_run()
        req.invalidate_data("/get-tasks")

    async def kill_task(self, req, dash9=False):
        try:
            task = self.find_task(req.data)
            task.kill_task(dash9)
            rti = task.get_running_task_info()
            if rti.get("no_proc"):
                task.unlink_pid()
                req.set_data("$.pidinfo", None)
                req.invalidate_data("/get-tasks")
            else:
                req.set_data("$.pidinfo", rti)
                sig = "KILL" if dash9 else "TERM"
                req.set_data("$.pidinfo.emsg", f"Process still running after {sig}")
        except Exception as e:
            req.set_data("$.error_modal", "Error killing task " + repr(e))

    async def kill_task_dash9(self, req):
        await self.kill_task(req, True)

    async def unlink_task(self, req):
        task = self.find_task(req.data)
        task.unlink_pid()
        req.set_data("$.pidinfo", None)
        req.invalidate_data("/get-tasks")

    async def get_task_info(self, req):
        task = self.find_task(req.data)
        req.set_data("$.taskinfo", None)
        info = task.get_task_info()
        req.set_data("$.taskinfo", info)
        return

    async def get_running_task_info(self, req):
        task = self.find_task(req.data)
        req.set_data("$.pidinfo", None)
        info = task.get_running_task_info()
        req.set_data("$.pidinfo", info)
        return

    async def get_task_output(self, req):
        task = self.find_task(req.data)
        output, fsize = task.get_log_contents(10000)
        if output is None:
            req.set_data("$.error_modal", "Logfile does not exist")
            return
        req.set_data("$.fileoutput.task_id", task.task_id)
        req.set_data("$.fileoutput.filename", task.external_logfile)
        req.set_data("$.fileoutput.size", fsize)
        req.set_data("$.fileoutput.content", output)
        return

    async def get_ps_output(self, req):
        p = subprocess.run("ps ax", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=2.0)
        req.set_data("$.psoutput", p.stdout.decode('ascii').splitlines())
        return
    
    pass

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="YAML task configuration file")
    parser.add_argument("--panel", help="Override Dashborg panel name (default=processadmin)")
    parser.add_argument("--demo", help="Demo Mode (disables unlink and kill -9)")
    args = parser.parse_args()
    m = AdminModel(demo_mode=args.demo)
    if args.config is not None:
        configfd = open(args.config)
        tasks_yaml = yaml.load(configfd, Loader=yaml.SafeLoader)
        for ty in tasks_yaml:
            task = TaskDef.from_dict(ty)
            m.add_task(task)
    else:
        # setup one fake task for testing
        t = TaskDef(
            cmd="ls -l > testoutput.log",
            name="Test 'ls' Command",
            external_logfile="testoutput.log",
            pidfile="test.pid")
        m.add_task(t)

    panel = args.panel if args.panel is not None else "processadmin"
    config = dashborg.Config(proc_name="processadmin", anon_acc=True, auto_keygen=True)
    await dashborg.start_proc_client(config)
    
    await dashborg.register_panel_handler(panel, "/", m.root_handler)
    await dashborg.register_panel_handler(panel, "/run-task", m.run_task)
    await dashborg.register_panel_handler(panel, "/get-task-output", m.get_task_output)
    await dashborg.register_panel_handler(panel, "/get-task-info", m.get_task_info)
    await dashborg.register_panel_handler(panel, "/get-running-task-info", m.get_running_task_info)
    await dashborg.register_panel_handler(panel, "/kill-task", m.kill_task)
    await dashborg.register_panel_handler(panel, "/kill-task-9", m.kill_task_dash9)
    await dashborg.register_panel_handler(panel, "/unlink-task", m.unlink_task)
    await dashborg.register_panel_handler(panel, "/get-ps-output", m.get_ps_output)
    await dashborg.register_data_handler(panel, "/get-tasks", m.get_tasks)
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
