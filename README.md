# Dashborg Python SDK

Dashborg is a SDK that plugs directly into any backend service or script.  With a couple lines of code you can register any running function with the Dashborg service and then build secure, modern, interactive tools on top of those functions using a simple, JavaScript free, HTML template language.

Dashborg saves you time by handling all of the tedious details of frontend app creation and deployment (hosting, end-to-end security, authentication, transport, UI libraries, JavaScript frameworks, CSS frameworks, etc.).

Dashborg works great for debugging, introspecting the running state of servers, viewing/updating configuration values, bite-sized internal tools, status pages, and reports.

Dashborg is easy to get started with.  You can have your first app deployed in 5-minutes (no account/registration required).  Free tier covers most simple use cases.

* Doc Site: https://docs.dashborg.net
* SDK Reference: https://docs.dashborg.net/reference/python-reference/
* Example Code: https://github.com/sawka/dashborg-examples (python directory)

Questions? [Join the Dashborg Slack Channel](https://join.slack.com/t/dashborgworkspace/shared_invite/zt-uphltkhj-r6C62szzoYz7_IIsoJ8WPg)


## Dashborg Hello World

```
pip install dashborg-python-sdk
```

```Python
import dashborg
import asyncio

counter = 0

def test_fn():
    global counter
    counter += 1
    print(f"Calling TestFn counter={counter}")
    return {"message": "TestFn Output!", "counter": counter}

async def main():
    config = dashborg.Config(anon_acc=True, auto_keygen=True)
    client = await dashborg.connect_client(config)
    app = client.app_client().new_app("hello-world")
    app.set_html(file_name="hello-world.html", watch=True)
    app.runtime.handler("test-handler", test_fn, pure_handler=True)
    await client.app_client().write_app(app, connect=True)
    await client.wait_for_shutdown()
    
asyncio.run(main())

```

The HTML template to render your app (save as hello-world.html):
```HTML
<app ui="dashborg">
  <h1>Hello World</h1>
  <div class="row xcenter">
    <d-button onclickhandler="$.output = /@app:test-handler">Run Test Handler</d-button>
    <d-stat label="Counter" bind="$.output.counter" defaultvalue="0"/>
  </div>
  <hr/>
  <d-dataview bind="$.output"/>
</app>
```

Run your program.  A new public/private keypair will be created and used to secure your new Dashborg account.  You'll also see a secure link to your new application.  Click to view your application!

That's it.  You've created and deployed, secure, interactive web-app that is directly calling code running on your local machine!

## Adding BLOBs

Want to show an image, or add a CSV file your end users to download, here's how to do it:
```Python
    await client.global_fs_client().set_static_path("/image/myimage.jpg", file_name="./path-to-image.jpg", fileopts=dashborg.FileOpts(mimetype="image/jpeg"))
    await client.global_fs_client().set_static_path("/mydata.csv", file_name="./path-to-csv.csv", fileopts=dashborg.FileOpts(mimetype="text/csv"))
```

Show the image using a regular &lt;img&gt; tag in your HTML template.  Using the path prefix "/@raw/"
allows for raw http GET access to your uploaded content:
```
    <img src="/@raw/image/myimage.jpg" style="max-width: 500px;"/>
```

Download the CSV using a standard HTML download link:
```
    <a href="/@raw/mydata.csv" download>Download CSV</a>
```

Or use a Dashborg download control (defined in the standard Dashborg UI package) to make it look nice:
```
    <d-download path="/mydata.csv">Download CSV</d-download>
```

## Adding Static Data

Dashborg uses JSON to transfer data between your app and the Dashborg
service.  You can send any static JSON-compatible data (bool, str,
int, float, dict, list) to Dashborg using set\_json\_path().  Static
data is available to apps even when there is no backend connected.
For dynamic data, use a runtime handler.  Here we'll set favorite
color table to the path "/colors.json".  We used the app\_fs\_client()
instead of the global\_fs\_client().  That makes the data local to the
app and is accessible at /@app/colors.json:

```Python
colors = []
colors.append({"name": "Mike", "color": "blue", "hex": "#007fff"})
colors.append({"name": "Chris", "color": "red", "hex": "#ee0000"})
colors.append({"name": "Jenny", "color": "purple", "hex": "#a020f0"})
await app.app_fs_client().set_json_path("/colors.json", colors)

```

Load the data into our datamodel using the &lt;d-data&gt; tag.  Read from blob "colors", set it into the 
frontend data model at ```$.colors```:
```html
<d-data query="/@app/colors.json" output.bindpath="$.colors"/>
```

Show the first color name as text using ```<d-text>```.  Use the hex color to show a
small color square using a background-color style (attributes and styles are dynamic when they starts with ```*```):
```html
<div>
    <d-text bind="$.colors[0].name"/>'s favorite color is <d-text bind="$.colors[0].color"/>:
    <div style="display: inline-block; vertical-align: bottom; width: 18px; height: 18px; background-color: *$.colors[0].hex"/>
</div>
```

You can loop using the built-in ```<d-foreach>``` tag (each element is bound to ```.``` inside the loop):
```html
<ul class="ui bulleted list">
    <d-foreach bind="$.colors">
      <li class="item" style="height: 24px">
        <div class="row">
          <div><d-text bind=".name"/> - Favorite Color is <d-text bind=".color"/></div>
          <div style="width: 18px; height: 18px; background-color: * .hex"/>
        </div>
      </li>
    </d-foreach>
</ul>
```

Or use a Dashborg Table Control (@index is bound to the loop counter):
```html
<d-table bind="$.colors">
   <d-col label="#" bind="@index+1"/>
   <d-col label="Name" bind=".name"/>
   <d-col label="Color" bind=".color"/>
   <d-col label="Swatch">
       <div style="width: 50px; height: 50px; background-color: * .hex"/>
   </d-col>
</d-table>
```

## Security

All communication from your backend to the Dashborg service is done over HTTPS/gRPC.  Your account is authenticated
with a public/private keypair that can be auto-generated by the Dashborg SDK (AutoKeygen config setting).

The frontend is served over HTTPS, and each account is hosted on its own subdomain to prevent inter-account XSS attacks 
The Dashborg frontend offers pre-built authentication methods, with JWT tokens that are
created from your private-key (the default for new anonymous accounts), simple passwords, or user logins.

## Advanced Features

* Write your own Dashborg components to reuse among your applications
* Create staging/development zones to test your apps without affecting your production site
* Assign roles to users (and passwords), set a list of allowed roles per app per zone
* Navigate to the '/@fs' path on your Dashborg account to see all of your static data, applications, and handlers.

