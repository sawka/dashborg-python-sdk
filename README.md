# Dashborg Python SDK

Modern internal tools defined, controlled, and deployed directly from backend code.  No JavaScript.
* Define your UI in HTML
* Define handlers in Go/Python
* Run your program to deploy your app

Dashborg was built to be the simplest way to create web-based internal from backend code.  You define your UI and interact with it *completely* within your backend code.  You get a fully hosted dashboard, without all of the overhead of messing with JavaScript, Babel, Webpack, React/Angular/Vue, UI frameworks, UI component libraries, Web Hosting, Load Balancing, HTTPS/Security/WAF, and User Accounts and Permissions.

## Documentation

* Doc Site: https://docs.dashborg.net/
* Tutorials: https://docs.dashborg.net/tutorials/t1/
* Playground: https://console.dashborg.net/acc/421d595f-9e30-4178-bcc3-b853f890fb8e/default/playground

## Key Features

* **No Javascript** - No context switching.  Write your dashboards using pure HTML and backend code.  No JavaScript environment to set up, no messing with NPM, Yarn, Webpack, Babel, React, Angular, etc.
* **No Open Ports** - No webhooks, firewall configuration, IP whitelists, or server hosting required for your backend.
* **No Server Hosting** - You get a secure, internet accessible frontend out of the box.  No web server configuration, domain name, load balancer, WAF setup and configuration required.
* **No Shared Passwords** - No incoming connections to your infrastructure.  Dashborg does not need your database passwords or API keys.  It does not access any 3rd party service on your behalf.
* **Built For Real Developers** - Use the code/libraries/frameworks that you already use to write your tools -- no 3rd-party GUI tools to learn, or typing code into text boxes on a website.  Easy to get started, but powerful enough to build complex tools and interactions.
* **Secure** - All connections are secured using SSL public/private key encryption with client auth.  HTTPS on the frontend.  Secure your dashboards with a simple password or user accounts.  SSO coming soon.
* **Control** - Dashborg panels are 100% defined from your backend code.  That means you can version them in your own code repository, and run and test them in your current dev/staging/production environments.
* **Modern Frontend Controls** - Tables, Lists, Forms, Inputs, and Buttons all out of the box (with more to come).  No Javascript or CSS frameworks required.  All styled to look good and work together.

## Dashborg Hello World

First install the Dashborg SDK:

```
pip install dashborg-python-sdk
```

The code below is the complete code for your first Dashborg program.  Copy and paste it into a new file (demo.py).

```Python {linenos=table}
import asyncio
import dashborg

async def root_handler(req):
    req.no_auth()
    req.set_html("<panel><h1>Hello World</h1></panel>")

async def main():
    config = dashborg.Config(proc_name="demo", anon_acc=True)
    await dashborg.start_proc_client(config)
    await dashborg.register_panel_handler("default", "/", root_handler)
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
```

You should see output that looks similar to (note your account id, fingerprint, and link will be different):

<pre style="font-size:12px; line-height: normal; overflow-x: scroll;">
Dashborg created new self-signed keypair key:dashborg-client.key cert:dashborg-client.crt for new accountid:<span style="color:red">0eb2cc25-ba5b-47b3-b376-33dcdeec3618</span>
Dashborg KeyFile:dashborg-client.key CertFile:dashborg-client.crt SHA256:<span style="color:green">vNCWyMJAuM3iSr5hEsEohYRKJ7zSHiVD3zchSaeYR7Q=</span>
Dashborg Initialized Client AccId:<span style="color:red">0eb2cc25-ba5b-47b3-b376-33dcdeec3618</span> Zone:default ProcName:hello ProcRunId:4f4e8364-5d39-495f-8c9e-1009741b1b47
Dashborg Panel Link [default]: <span style="color: blue; font-weight: bold;">https://console.dashborg.net/acc/0eb2cc25-ba5b-47b3-b376-33dcdeec3618/default/default</span>

</pre>

Copy and paste the link (blue) into your browser and you should see your live dashboard!



