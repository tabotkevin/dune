import io
import os
import random
import string

import pytest
import yaml
from marshmallow import Schema, fields
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.testclient import TestClient as StarletteTestClient

import dyne
from dyne.routes import Route, WebSocketRoute
from dyne.templates import Templates


def test_api_basic_route(api):
    @api.route("/")
    def home(req, resp):
        resp.text = "hello world!"


def test_route_repr():
    def home(req, resp):
        """Home page"""
        resp.text = "Hello !"

    route = Route("/", home)

    assert route.__repr__() == f"<Route '/'={home!r}>"

    assert route.endpoint_name == home.__name__
    assert route.description == home.__doc__


def test_websocket_route_repr():
    def chat_endpoint(ws):
        """Chat"""
        pass

    route = WebSocketRoute("/", chat_endpoint)

    assert route.__repr__() == f"<Route '/'={chat_endpoint!r}>"

    assert route.endpoint_name == chat_endpoint.__name__
    assert route.description == chat_endpoint.__doc__


def test_route_eq():
    def home(req, resp):
        resp.text = "Hello !"

    assert Route("/", home) == Route("/", home)

    def chat(ws):
        pass

    assert WebSocketRoute("/", home) == WebSocketRoute("/", home)


"""
def test_api_basic_route_overlap(api):
    @api.route("/")
    def home(req, resp):
        resp.text = "hello world!"

    with pytest.raises(AssertionError):

        @api.route("/")
        def home2(req, resp):
            resp.text = "hello world!"
"""


def test_class_based_view_registration(api):
    @api.route("/")
    class ThingsResource:
        def on_request(req, resp):
            resp.text = "42"


def test_class_based_view_parameters(api):
    @api.route("/{greeting}")
    class Greeting:
        pass

    resp = api.session().get("http://;/Hello")
    assert resp.status_code == api.status_codes.HTTP_405


def test_requests_session(api):
    assert api.session()
    assert api.requests


def test_requests_session_works(api):
    TEXT = "spiral out"

    @api.route("/")
    def hello(req, resp):
        resp.text = TEXT

    assert api.requests.get("/").text == TEXT


def test_status_code(api):
    @api.route("/")
    def hello(req, resp):
        resp.text = "keep going"
        resp.status_code = dyne.status_codes.HTTP_416

    assert api.requests.get("http://;/").status_code == dyne.status_codes.HTTP_416


def test_json_media(api):
    dump = {"life": 42}

    @api.route("/")
    def media(req, resp):
        resp.media = dump

    r = api.requests.get("http://;/")

    assert "json" in r.headers["Content-Type"]
    assert r.json() == dump


def test_yaml_media(api):
    dump = {"life": 42}

    @api.route("/")
    def media(req, resp):
        resp.media = dump

    r = api.requests.get("http://;/", headers={"Accept": "yaml"})

    assert "yaml" in r.headers["Content-Type"]
    assert yaml.load(r.content, Loader=yaml.FullLoader) == dump


def test_graphql_schema_query_querying(api, schema):
    api.add_route("/", dyne.ext.GraphQLView(schema=schema, api=api))

    r = api.requests.get("http://;/?q={ hello }", headers={"Accept": "json"})
    assert r.json() == {"data": {"hello": "Hello stranger"}}


def test_argumented_routing(api):
    @api.route("/{name}")
    def hello(req, resp, *, name):
        resp.text = f"Hello, {name}."

    r = api.requests.get(api.url_for(hello, name="sean"))
    assert r.text == "Hello, sean."


def test_mote_argumented_routing(api):
    @api.route("/{greeting}/{name}")
    def hello(req, resp, *, greeting, name):
        resp.text = f"{greeting}, {name}."

    r = api.requests.get(api.url_for(hello, greeting="hello", name="lyndsy"))
    assert r.text == "hello, lyndsy."


def test_request_and_get(api):
    @api.route("/")
    class ThingsResource:
        def on_request(self, req, resp):
            resp.headers.update({"DEATH": "666"})

        def on_get(self, req, resp):
            resp.headers.update({"LIFE": "42"})

    r = api.requests.get(api.url_for(ThingsResource))
    assert "DEATH" in r.headers
    assert "LIFE" in r.headers


def test_class_based_view_status_code(api):
    @api.route("/")
    class ThingsResource:
        def on_request(self, req, resp):
            resp.status_code = dyne.status_codes.HTTP_416

    assert api.requests.get("http://;/").status_code == dyne.status_codes.HTTP_416


def test_query_params(api, url):
    @api.route("/")
    def route(req, resp):
        resp.media = {"params": req.params}

    r = api.requests.get(api.url_for(route), params={"q": "q"})
    assert r.json()["params"] == {"q": "q"}

    r = api.requests.get(url("/?q=1&q=2&q=3"))
    assert r.json()["params"] == {"q": "3"}


# Requires https://github.com/encode/starlette/pull/102
def test_form_data(api):
    @api.route("/", methods=["POST"])
    async def route(req, resp):
        resp.media = {"form": await req.media("form")}

    dump = {"q": "q"}
    r = api.requests.post(api.url_for(route), data=dump)
    assert r.json()["form"] == dump


def test_async_function(api):
    content = "The Emerald Tablet of Hermes"

    @api.route("/")
    async def route(req, resp):
        resp.text = content

    r = api.requests.get(api.url_for(route))
    assert r.text == content


def test_media_parsing(api):
    dump = {"hello": "sam"}

    @api.route("/")
    def route(req, resp):
        resp.media = dump

    r = api.requests.get(api.url_for(route))
    assert r.json() == dump

    r = api.requests.get(api.url_for(route), headers={"Accept": "application/x-yaml"})
    assert r.text == "hello: sam\n"


def test_background(api):
    @api.route("/")
    def route(req, resp):
        @api.background.task
        def task():
            import time

            time.sleep(3)

        task()
        api.text = "ok"

    r = api.requests.get(api.url_for(route))
    assert r.status_code == 200


def test_multiple_routes(api):
    @api.route("/1")
    def route1(req, resp):
        resp.text = "1"

    @api.route("/2")
    def route2(req, resp):
        resp.text = "2"

    r = api.requests.get(api.url_for(route1))
    assert r.text == "1"

    r = api.requests.get(api.url_for(route2))
    assert r.text == "2"


def test_graphql_schema_json_query(api, schema):
    api.add_route("/", dyne.ext.GraphQLView(schema=schema, api=api), methods=["POST"])

    r = api.requests.post("http://;/", json={"query": "{ hello }"})
    assert r.status_code == 200


def test_graphiql(api, schema):
    api.add_route("/", dyne.ext.GraphQLView(schema=schema, api=api))

    r = api.requests.get("http://;/", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "GraphiQL" in r.text


def test_json_uploads(api):
    @api.route("/", methods=["POST"])
    async def route(req, resp):
        resp.media = await req.media()

    dump = {"complicated": "times"}
    r = api.requests.post(api.url_for(route), json=dump)
    assert r.json() == dump


def test_yaml_uploads(api):
    @api.route("/", methods=["POST"])
    async def route(req, resp):
        resp.media = await req.media()

    dump = {"complicated": "times"}
    r = api.requests.post(
        api.url_for(route),
        content=yaml.dump(dump),
        headers={"Content-Type": "application/x-yaml"},
    )
    assert r.json() == dump


def test_form_uploads(api):
    @api.route("/", methods=["POST"])
    async def route(req, resp):
        resp.media = await req.media()

    dump = {"complicated": "times"}
    r = api.requests.post(api.url_for(route), data=dump)
    assert r.json() == dump

    # requests with boundary
    files = {"complicated": (None, "times")}
    r = api.requests.post(api.url_for(route), files=files)
    assert r.json() == {"complicated": "times"}


def test_json_downloads(api):
    dump = {"testing": "123"}

    @api.route("/")
    def route(req, resp):
        resp.media = dump

    r = api.requests.get(
        api.url_for(route), headers={"Content-Type": "application/json"}
    )
    assert r.json() == dump


def test_yaml_downloads(api):
    dump = {"testing": "123"}

    @api.route("/")
    def route(req, resp):
        resp.media = dump

    r = api.requests.get(
        api.url_for(route), headers={"Content-Type": "application/x-yaml"}
    )
    assert yaml.safe_load(r.content) == dump


def test_schema_generation_explicit():
    import marshmallow

    import dyne
    from dyne.ext.schema import Schema as OpenAPISchema

    api = dyne.API()

    schema = OpenAPISchema(
        app=api,
        title="Web Service",
        version="1.0",
        openapi="3.0.2",
        openapi_route="/schema.yaml",
    )

    @schema.schema("Pet")
    class PetSchema(marshmallow.Schema):
        name = marshmallow.fields.Str()

    @api.route("/")
    def route(req, resp):
        """A cute furry animal endpoint.
        ---
        get:
            description: Get a random pet
            responses:
                200:
                    description: A pet to be returned
                    schema:
                        $ref: "#/components/schemas/Pet"
        """
        resp.media = PetSchema().dump({"name": "little orange"})

    r = api.requests.get("http://;/schema.yaml")
    dump = yaml.safe_load(r.content)

    assert dump
    assert dump["openapi"] == "3.0.2"


def test_schema_generation():
    from marshmallow import Schema, fields

    import dyne

    api = dyne.API(
        title="Web Service",
        openapi="3.0.2",
        openapi_route="/schema.yaml",
    )

    @api.schema("Pet")
    class PetSchema(Schema):
        name = fields.Str()

    @api.route("/")
    def route(req, resp):
        """A cute furry animal endpoint.
        ---
        get:
            description: Get a random pet
            responses:
                200:
                    description: A pet to be returned
                    schema:
                        $ref: "#/components/schemas/Pet"
        """
        resp.media = PetSchema().dump({"name": "little orange"})

    r = api.requests.get("http://;/schema.yaml")
    dump = yaml.safe_load(r.content)

    assert dump
    assert dump["openapi"] == "3.0.2"


def test_documentation_explicit():
    import marshmallow

    import dyne
    from dyne.ext.schema import Schema as OpenAPISchema

    description = "This is a sample server for a pet store."
    terms_of_service = "http://example.com/terms/"
    contact = {
        "name": "API Support",
        "url": "http://www.example.com/support",
        "email": "support@example.com",
    }
    license = {
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    }

    api = dyne.API(allowed_hosts=["testserver", ";"])

    schema = OpenAPISchema(
        app=api,
        title="Web Service",
        version="1.0",
        openapi="3.0.2",
        docs_route="/doc",
        description=description,
        terms_of_service=terms_of_service,
        openapi_route="/schema.yaml",
        contact=contact,
        license=license,
    )

    @schema.schema("Pet")
    class PetSchema(marshmallow.Schema):
        name = marshmallow.fields.Str()

    @api.route("/")
    def route(req, resp):
        """A cute furry animal endpoint.
        ---
        get:
            description: Get a random pet
            responses:
                200:
                    description: A pet to be returned
                    schema:
                        $ref: "#/components/schemas/Pet"
        """
        resp.media = PetSchema().dump({"name": "little orange"})

    r = api.requests.get("/doc")
    assert "html" in r.text


def test_documentation():
    from marshmallow import Schema, fields

    import dyne

    description = "This is a sample server for a pet store."
    terms_of_service = "http://example.com/terms/"
    contact = {
        "name": "API Support",
        "url": "http://www.example.com/support",
        "email": "support@example.com",
    }
    license = {
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    }

    api = dyne.API(
        title="Web Service",
        version="1.0",
        openapi="3.0.2",
        docs_route="/docs",
        description=description,
        terms_of_service=terms_of_service,
        contact=contact,
        license=license,
        allowed_hosts=["testserver", ";"],
    )

    @api.schema("Pet")
    class PetSchema(Schema):
        name = fields.Str()

    @api.route("/")
    def route(req, resp):
        """A cute furry animal endpoint.
        ---
        get:
            description: Get a random pet
            responses:
                200:
                    description: A pet to be returned
                    schema:
                        $ref: "#/components/schemas/Pet"
        """
        resp.media = PetSchema().dump({"name": "little orange"})

    r = api.requests.get("/docs")
    assert "html" in r.text


def test_mount_wsgi_app(api, flask):
    @api.route("/")
    def hello(req, resp):
        resp.text = "hello"

    api.mount("/flask", flask)

    r = api.requests.get("http://;/flask")
    assert r.status_code == 200


def test_async_class_based_views(api):
    @api.route("/")
    class Resource:
        async def on_post(self, req, resp):
            resp.text = await req.text

    data = "frame"
    r = api.requests.post(api.url_for(Resource), content=data)
    assert r.text == data


def test_cookies(api):
    @api.route("/")
    def home(req, resp):
        resp.media = {"cookies": req.cookies}
        resp.cookies["sent"] = "true"
        resp.set_cookie(
            "hello",
            "world",
            expires=123,
            path="/",
            max_age=123,
            secure=False,
            httponly=True,
        )

    client = api.requests
    client.cookies = {"hello": "universe"}
    r = client.get(api.url_for(home))
    assert r.json() == {"cookies": {"hello": "universe"}}
    assert "sent" in r.cookies
    assert "hello" in r.cookies

    r = api.requests.get(api.url_for(home))
    assert r.json() == {"cookies": {"hello": "world", "sent": "true"}}


@pytest.mark.xfail
def test_sessions(api):
    @api.route("/")
    def view(req, resp):
        resp.session["hello"] = "world"
        resp.media = resp.session

    r = api.requests.get(api.url_for(view))
    assert api.session_cookie in r.cookies

    r = api.requests.get(api.url_for(view))
    assert (
        r.cookies[api.session_cookie]
        == '{"hello": "world"}.r3EB04hEEyLYIJaAXCEq3d4YEbs'
    )
    assert r.json() == {"hello": "world"}


def test_template_string_rendering(api):
    @api.route("/")
    def view(req, resp):
        resp.content = api.template_string("{{ var }}", var="hello")

    r = api.requests.get(api.url_for(view))
    assert r.text == "hello"


def test_template_rendering(template_path):
    api = dyne.API(templates_dir=template_path.dirpath())

    @api.route("/")
    def view(req, resp):
        resp.content = api.template(template_path.basename, var="hello")

    r = api.requests.get(api.url_for(view))
    assert r.text == "hello"


def test_template(api, template_path):
    templates = Templates(directory=template_path.dirpath())

    @api.route("/{var}/")
    def view(req, resp, var):
        resp.html = templates.render(template_path.basename, var=var)

    r = api.requests.get("/test/")
    assert r.text == "test"


def test_template_async(api, template_path):
    templates = Templates(directory=template_path.dirpath(), enable_async=True)

    @api.route("/{var}/async")
    async def view_async(req, resp, var):
        resp.html = await templates.render_async(template_path.basename, var=var)

    r = api.requests.get("/test/async")
    assert r.text == "test"


def test_file_uploads(api):
    @api.route("/", methods=["POST"])
    async def upload(req, resp):
        files = await req.media("files")
        result = {}
        result["hello"] = files["hello"]["content"].decode("utf-8")
        resp.media = {"files": result}

    world = io.BytesIO(b"world")
    data = {"hello": ("hello.txt", world, "text/plain")}
    r = api.requests.post(api.url_for(upload), files=data)
    assert r.json() == {"files": {"hello": "world"}}

    @api.route("/not_file", methods=["POST"])
    async def upload_not_file(req, resp):
        files = await req.media("files")
        result = {}
        result["not-a-file"] = files["not-a-file"].decode("utf-8")
        resp.media = {"files": result}

    world = io.BytesIO(b"world")
    data = {"not-a-file": b"data only"}
    with pytest.raises(Exception) as err:  # noqa: F841
        r = api.requests.post(api.url_for(upload_not_file), files=data)


def test_500(api):
    @api.route("/")
    def view(req, resp):
        raise ValueError

    dumb_client = dyne.api.TestClient(
        api, base_url="http://;", raise_server_exceptions=False
    )
    r = dumb_client.get(api.url_for(view))
    assert r.status_code == dyne.status_codes.HTTP_500


def test_404(api):
    r = api.requests.get("/foo")

    assert r.status_code == dyne.status_codes.HTTP_404


def test_websockets_text(api):
    payload = "Hello via websocket!"

    @api.route("/ws", websocket=True)
    async def websocket(ws):
        await ws.accept()
        await ws.send_text(payload)
        await ws.close()

    client = StarletteTestClient(api)
    with client.websocket_connect("ws://;/ws") as websocket:  # noqa: F811
        data = websocket.receive_text()
        assert data == payload


def test_websockets_bytes(api):
    payload = b"Hello via websocket!"

    @api.route("/ws", websocket=True)
    async def websocket(ws):
        await ws.accept()
        await ws.send_bytes(payload)
        await ws.close()

    client = StarletteTestClient(api)
    with client.websocket_connect("ws://;/ws") as websocket:  # noqa: F811
        data = websocket.receive_bytes()
        assert data == payload


def test_websockets_json(api):
    payload = {"Hello": "via websocket!"}

    @api.route("/ws", websocket=True)
    async def websocket(ws):
        await ws.accept()
        await ws.send_json(payload)
        await ws.close()

    client = StarletteTestClient(api)
    with client.websocket_connect("ws://;/ws") as websocket:  # noqa: F811
        data = websocket.receive_json()
        assert data == payload


def test_before_websockets(api):
    payload = {"Hello": "via websocket!"}

    @api.route("/ws", websocket=True)
    async def websocket(ws):
        await ws.send_json(payload)
        await ws.close()

    @api.before_request(websocket=True)
    async def before_request(ws):
        await ws.accept()
        await ws.send_json({"before": "request"})

    client = StarletteTestClient(api)
    with client.websocket_connect("ws://;/ws") as websocket:  # noqa: F811
        data = websocket.receive_json()
        assert data == {"before": "request"}
        data = websocket.receive_json()
        assert data == payload


def test_startup(api):
    who = [None]

    @api.route("/{greeting}")
    async def greet_world(req, resp, *, greeting):
        resp.text = f"{greeting}, {who[0]}!"

    @api.on_event("startup")
    async def run_startup():
        who[0] = "world"

    with api.requests as session:
        r = session.get("http://;/hello")
        assert r.text == "hello, world!"


def test_redirects(api, session):
    @api.route("/2")
    def two(req, resp):
        api.redirect(resp, location="/1")

    @api.route("/1")
    def one(req, resp):
        resp.text = "redirected"

    assert session.get("/2").url == "http://;/1"


def test_session_thoroughly(api, session):
    @api.route("/set")
    def set(req, resp):
        resp.session["hello"] = "world"
        api.redirect(resp, location="/get")

    @api.route("/get")
    def get(req, resp):
        resp.media = {"session": req.session}

    r = session.get(api.url_for(set))
    r = session.get(api.url_for(get))
    assert r.json() == {"session": {"hello": "world"}}


def test_before_response(api, session):
    @api.route("/get")
    def get(req, resp):
        resp.media = req.session

    @api.route(before_request=True)
    async def async_before_request(req, resp):
        resp.headers["x-pizza"] = "1"

    @api.route(before_request=True)
    def before_request(req, resp):
        resp.headers["x-pizza"] = "1"

    r = session.get(api.url_for(get))
    assert "x-pizza" in r.headers


@pytest.mark.parametrize("enable_hsts", [True, False])
@pytest.mark.parametrize("cors", [True, False])
def test_allowed_hosts(enable_hsts, cors):
    api = dyne.API(allowed_hosts=[";", "tenant.;"], enable_hsts=enable_hsts, cors=cors)

    @api.route("/")
    def get(req, resp):
        pass

    # Exact match
    r = api.requests.get(api.url_for(get))
    assert r.status_code == 200

    # Reset the session
    api._session = None
    r = api.session(base_url="http://tenant.;").get(api.url_for(get))
    assert r.status_code == 200

    # Reset the session
    api._session = None
    r = api.session(base_url="http://unkownhost").get(api.url_for(get))
    assert r.status_code == 400

    # Reset the session
    api._session = None
    r = api.session(base_url="http://unkown_tenant.;").get(api.url_for(get))
    assert r.status_code == 400

    api = dyne.API(allowed_hosts=["*.;"])

    @api.route("/")
    def get(req, resp):
        pass

    # Wildcard domains
    # Using http://;
    r = api.requests.get(api.url_for(get))
    assert r.status_code == 400

    # Reset the session
    api._session = None
    r = api.session(base_url="http://tenant1.;").get(api.url_for(get))
    assert r.status_code == 200

    # Reset the session
    api._session = None
    r = api.session(base_url="http://tenant2.;").get(api.url_for(get))
    assert r.status_code == 200


def create_asset(static_dir, name=None, parent_dir=None):
    if name is None:
        name = random.choices(string.ascii_letters, k=6)
        # :3
        ext = random.choices(string.ascii_letters, k=2)
        name = f"{name}.{ext}"

    if parent_dir is None:
        parent_dir = static_dir
    else:
        parent_dir = static_dir.mkdir(parent_dir)

    asset = parent_dir.join(name)
    asset.write("body { color: blue; }")
    return asset


@pytest.mark.parametrize("static_route", [None, "/static", "/custom/static/route"])
def test_staticfiles(tmpdir, static_route):
    static_dir = tmpdir.mkdir("static")

    asset1 = create_asset(static_dir)
    parent_dir = "css"
    asset2 = create_asset(static_dir, name="asset2", parent_dir=parent_dir)

    api = dyne.API(static_dir=str(static_dir), static_route=static_route)
    session = api.session()

    static_route = api.static_route

    # ok
    r = session.get(f"{static_route}/{asset1.basename}")
    assert r.status_code == api.status_codes.HTTP_200

    r = session.get(f"{static_route}/{parent_dir}/{asset2.basename}")
    assert r.status_code == api.status_codes.HTTP_200

    # Asset not found
    r = session.get(f"{static_route}/not_found.css")
    assert r.status_code == api.status_codes.HTTP_404

    # Not found on dir listing
    r = session.get(f"{static_route}")
    assert r.status_code == api.status_codes.HTTP_404

    r = session.get(f"{static_route}/{parent_dir}")
    assert r.status_code == api.status_codes.HTTP_404


def test_response_html_property(api):
    @api.route("/")
    def view(req, resp):
        resp.html = "<h1>Hello !</h1>"

        assert resp.content == "<h1>Hello !</h1>"
        assert resp.mimetype == "text/html"

    r = api.requests.get(api.url_for(view))
    assert r.content == b"<h1>Hello !</h1>"
    assert r.headers["Content-Type"] == "text/html"


def test_response_text_property(api):
    @api.route("/")
    def view(req, resp):
        resp.text = "<h1>Hello !</h1>"

        assert resp.content == "<h1>Hello !</h1>"
        assert resp.mimetype == "text/plain"

    r = api.requests.get(api.url_for(view))
    assert r.content == b"<h1>Hello !</h1>"
    assert r.headers["Content-Type"] == "text/plain"


def test_stream(api, session):
    async def shout_stream(who):
        for c in who.upper():
            yield c

    @api.route("/{who}")
    async def greeting(req, resp, *, who):
        resp.stream(shout_stream, who)

    r = session.get("/morocco")
    assert r.text == "MOROCCO"

    @api.route("/")
    async def home(req, resp):
        # Raise when it's not an async generator
        with pytest.raises(AssertionError):

            def foo():
                pass

            resp.stream(foo)

        with pytest.raises(AssertionError):

            async def foo():
                pass

            resp.stream(foo)

        with pytest.raises(AssertionError):

            def foo():
                yield "oopsie"

            resp.stream(foo)


def test_empty_req_text(api):
    content = "It's working"

    @api.route("/", methods=["POST"])
    async def home(req, resp):
        await req.text
        resp.text = content

    r = api.requests.post("/")
    assert r.text == content

    def test_api_request_state(api, url):
        class StateMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.test1 = 42
                request.state.test2 = "Foo"

                response = await call_next(request)
                return response

        api.add_middleware(StateMiddleware)

        @api.route("/")
        def home(req, resp):
            resp.text = "{}_{}".format(req.state.test2, req.state.test1)

        assert api.requests.get(url("/")).text == "Foo_42"


def test_path_matches_route(api):
    @api.route("/hello")
    def home(req, resp):
        resp.text = "hello world!"

    route = api.path_matches_route({"type": "http", "path": "/hello"})
    assert route.endpoint_name == "home"

    assert not api.path_matches_route({"type": "http", "path": "/foo"})


def test_route_without_endpoint(api):
    api.add_route("/")
    route = api.router.routes[0]
    assert route.endpoint_name == "schema_response"


def test_pydantic_input_request_validation(api):
    class ItemSchema(BaseModel):
        name: str

    class CookiesSchema(BaseModel):
        max_age: int
        is_cheap: bool

    @api.route("/create", methods=["POST"])
    @api.input(ItemSchema)
    async def create_item(req, resp, *, data):
        resp.text = "created"

        assert data == {"name": "Test Item"}

    # Cookies routes
    @api.route("/")
    @api.input(CookiesSchema, location="cookies")
    async def home_cookies(req, resp, *, cookies):
        resp.text = "Welcome"

        assert cookies == {"max_age": 123, "is_cheap": True}

    # Valid media
    data = {"name": "Test Item"}
    # resp_mock.media.return_value = data
    response = api.requests.post(api.url_for(create_item), json=data)
    assert response.status_code == api.status_codes.HTTP_200
    assert response.text == "created"

    # Valid  cookies
    client = api.requests
    client.cookies = {"max_age": "123", "is_cheap": "True"}
    response = client.get(api.url_for(home_cookies))
    assert response.status_code == api.status_codes.HTTP_200
    assert response.text == "Welcome"

    # Invalid Pydantic data
    data = {"name": [123]}  # Invalid data
    response = api.requests.post(api.url_for(create_item), json=data)
    assert response.status_code == api.status_codes.HTTP_400
    assert "error" in response.text


def test_marshmallow_input_request_validation(api):
    class ItemSchema(Schema):
        name = fields.Str()

    class QuerySchema(Schema):
        page = fields.Int(missing=1)
        limit = fields.Int(missing=10)

    class HeaderSchema(Schema):
        x_version = fields.String(data_key="X-Version", required=True)

    @api.route("/create", methods=["POST"])
    @api.input(ItemSchema)
    async def create_item(req, resp, *, data):
        resp.text = "created"

        assert data == {"name": "Test Item"}

    # Query(params) route
    @api.route("/items")
    @api.input(QuerySchema, location="query")
    async def get_items(req, resp, *, query):
        assert query == {"page": 2, "limit": 20}

        resp.media = {"items": [{"name": "Scooter"}]}

    # Headers routes
    @api.route("/item/{id}", methods=["POST"])
    @api.input(HeaderSchema, location="headers")
    async def item(req, resp, *, id, headers):
        """Header Pydantic"""
        assert headers == {"x_version": "2.4.5"}

        resp.media = {"name": "Samsung Galaxy"}

    # Valid data
    data = {"name": "Test Item"}
    response = api.requests.post(api.url_for(create_item), json=data)
    assert response.status_code == api.status_codes.HTTP_200
    assert response.text == "created"

    # Valid params(query)
    response = api.requests.get(api.url_for(get_items), params={"page": 2, "limit": 20})
    assert response.status_code == api.status_codes.HTTP_200
    assert response.json() == {"items": [{"name": "Scooter"}]}

    # Valid headers
    response = api.requests.post(
        api.url_for(item, id=1), headers={"X-Version": "2.4.5"}
    )
    assert response.status_code == api.status_codes.HTTP_200
    assert response.json() == {"name": "Samsung Galaxy"}

    # Invalid data
    data = {"name": [123]}  # Invalid data
    response = api.requests.post(api.url_for(create_item), json=data)
    assert response.status_code == api.status_codes.HTTP_400
    assert "error" in response.text


def test_endpoint_request_methods(api):
    @api.route("/{greeting}")
    async def greet(req, resp, *, greeting):  # defaults to get.
        resp.text = f"{greeting}, world!"

    @api.route("/me/{greeting}", methods=["POST"])
    async def greet_me(req, resp, *, greeting):
        resp.text = f"POST - {greeting}, world!"

    @api.route("/no/{greeting}")
    class NoGreeting:
        pass

    @api.route("/person/{greeting}")
    class GreetingResource:
        def on_get(self, req, resp, *, greeting):
            resp.text = f"GET person - {greeting}, world!"
            resp.headers.update({"X-Life": "41"})
            resp.status_code = api.status_codes.HTTP_201

        def on_post(self, req, resp, *, greeting):
            resp.text = f"POST person - {greeting}, world!"
            resp.headers.update({"X-Life": "42"})

        def on_request(self, req, resp, *, greeting):  # any request method.
            resp.text = f"any person - {greeting}, world!"
            resp.headers.update({"X-Life": "43"})

    resp = api.requests.get("http://;/Hello")
    assert resp.status_code == api.status_codes.HTTP_200
    assert resp.text == "Hello, world!"

    resp = api.requests.post("http://;/Hello")
    assert resp.status_code == api.status_codes.HTTP_405

    resp = api.requests.get("http://;/me/Hey")
    assert resp.status_code == api.status_codes.HTTP_405

    resp = api.requests.post("http://;/me/Hey")
    assert resp.status_code == api.status_codes.HTTP_200
    assert resp.text == "POST - Hey, world!"

    resp = api.requests.get("http://;/no/Hello")
    assert resp.status_code == api.status_codes.HTTP_405

    resp = api.requests.post("http://;/no/Hello")
    assert resp.status_code == api.status_codes.HTTP_405

    resp = api.requests.get("http://;/person/Hi")
    assert resp.text == "GET person - Hi, world!"
    assert resp.headers["X-Life"] == "41"
    assert resp.status_code == api.status_codes.HTTP_201

    resp = api.requests.post("http://;/person/Hi")
    assert resp.text == "POST person - Hi, world!"
    assert resp.headers["X-Life"] == "42"
    assert resp.status_code == api.status_codes.HTTP_200

    resp = api.requests.put("http://;/person/Hi")
    assert resp.text == "any person - Hi, world!"
    assert resp.headers["X-Life"] == "43"
    assert resp.status_code == api.status_codes.HTTP_200


def test_pydantic_response_schema_serialization(api):
    class Base(DeclarativeBase):
        pass

    # Define an example SQLAlchemy model
    class Book(Base):
        __tablename__ = "books"
        id = Column(Integer, primary_key=True)
        price = Column(Float)
        title = Column(String)

    # Create tables in the database
    engine = create_engine("sqlite:///py.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()

    book1 = Book(price=9.99, title="Harry Potter")
    book2 = Book(price=10.99, title="Pirates of the sea")
    session.add(book1)
    session.add(book2)
    session.commit()

    class BaseBookSchema(BaseModel):
        price: float
        title: str
        model_config = ConfigDict(from_attributes=True)

    class BookIn(BaseBookSchema): ...

    class BookOut(BaseBookSchema):
        id: int

    @api.route("/create", methods=["POST"])
    @api.input(BookIn)
    @api.output(BookOut)
    async def create_book(req, resp, *, data):
        """Create book"""

        book = Book(**data)
        session.add(book)
        session.commit()

        resp.obj = book

    @api.route("/all")
    @api.output(BookOut)
    async def all_books(req, resp):
        """Get all books"""

        resp.obj = session.query(Book)

    data = {"title": "Learning Responder", "price": 39.99}
    response = api.requests.post(api.url_for(create_book), json=data)
    assert response.status_code == api.status_codes.HTTP_200
    assert response.json() == {"id": 3, "price": 39.99, "title": "Learning Responder"}

    response = api.requests.get(api.url_for(all_books))
    assert response.status_code == api.status_codes.HTTP_200
    rs = response.json()
    assert len(rs) == 3
    ids = sorted([book["id"] for book in rs])
    prices = sorted([book["price"] for book in rs])
    titles = sorted([book["title"] for book in rs])
    assert ids == [1, 2, 3]
    assert prices == [9.99, 10.99, 39.99]
    assert titles == ["Harry Potter", "Learning Responder", "Pirates of the sea"]
    os.remove("py.db")


def test_marshmallow_response_schema_serialization(api):
    class Base(DeclarativeBase):
        pass

    # Define an example SQLAlchemy model
    class Book(Base):
        __tablename__ = "books"
        id = Column(Integer, primary_key=True)
        price = Column(Float)
        title = Column(String)

    # Create tables in the database
    engine = create_engine("sqlite:///ma.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()

    book1 = Book(price=9.99, title="Harry Potter")
    book2 = Book(price=10.99, title="Pirates of the sea")
    session.add(book1)
    session.add(book2)
    session.commit()

    class BookSchema(Schema):
        id = fields.Integer(dump_only=True)
        price = fields.Float()
        title = fields.Str()

        class Meta:
            model = Book

    @api.route("/create", methods=["POST"])
    @api.input(BookSchema)
    @api.output(BookSchema)
    async def create_book(req, resp, *, data):
        """Create book"""

        book = Book(**data)
        session.add(book)
        session.commit()

        resp.obj = book

    @api.route("/all")
    @api.output(BookSchema)
    async def all_books(req, resp):
        """Get all books"""

        resp.obj = session.query(Book)

    data = {"title": "Python Programming", "price": 11.99}
    response = api.requests.post(api.url_for(create_book), json=data)
    assert response.status_code == api.status_codes.HTTP_200
    assert response.json() == {"id": 3, "price": 11.99, "title": "Python Programming"}

    response = api.requests.get(api.url_for(all_books))
    assert response.status_code == api.status_codes.HTTP_200
    rs = response.json()
    assert len(rs) == 3
    ids = sorted([book["id"] for book in rs])
    prices = sorted([book["price"] for book in rs])
    titles = sorted([book["title"] for book in rs])
    assert ids == [1, 2, 3]
    assert prices == [9.99, 10.99, 11.99]
    assert titles == ["Harry Potter", "Pirates of the sea", "Python Programming"]
    os.remove("ma.db")
