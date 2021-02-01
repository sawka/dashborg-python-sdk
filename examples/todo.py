import dashborg
import asyncio

class TodoModel:
    def __init__(self):
        self.todo_list = []
        self.next_id = 1

    async def root_handler(self, req):
        req.no_auth()
        await req.set_html_from_file("examples/todo.html")
        return

    async def GetTodoList(self, datareq):
        return self.todo_list

    async def AddTodo(self, req):
        newtodo = req.panel_state.get("newtodo")
        if newtodo is None or newtodo == "":
            return
        todo = {"Id": self.next_id, "Item": newtodo, "Done": False}
        self.next_id += 1
        self.todo_list.append(todo)
        req.invalidate_data("/GetTodoList")
        req.set_data("$.state.newtodo", None)
        return

    async def MarkTodoDone(self, req):
        if req.data is None:
            return
        todo_id = int(req.data)
        for t in self.todo_list:
            if t["Id"] == todo_id:
                t["Done"] = True
        req.invalidate_data("/GetTodoList")
        return

    async def RemoveTodo(self, req):
        if req.data is None:
            return
        todo_id = int(req.data)
        self.todo_list = [t for t in self.todo_list if t["Id"] != todo_id]
        req.invalidate_data("/GetTodoList")
        return
        

async def main():
    config = dashborg.Config(proc_name="todo", anon_acc=True, auto_keygen=True)
    await dashborg.start_proc_client(config)
    m = TodoModel()
    await dashborg.register_panel_class("todo", m)
    while True:
        await asyncio.sleep(1)

asyncio.run(main())


