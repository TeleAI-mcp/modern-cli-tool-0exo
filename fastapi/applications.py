"""
FastAPI applications.
"""
import warnings
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional, Sequence, Tuple, Union

from fastapi import routing
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.encoders import DictIntStrAny, SetIntStr
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.logger import logger
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.routing import APIRoute, APIRouter
from fastapi.types import ASGIApp, IncEx
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.types import Receive, Scope, Send


class FastAPI(Starlette):
    """
    The main FastAPI class.

    This class inherits from Starlette and adds all the functionality for building
    APIs with OpenAPI documentation, validation, serialization, etc.

    ## Example

    ```python
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/")
    async def read_root():
        return {"Hello": "World"}
    ```
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        routes: Optional[List[BaseRoute]] = None,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        openapi_url: Optional[str] = "/openapi.json",
        openapi_tags: Optional[List[Dict[str, Any]]] = None,
        servers: Optional[List[Dict[str, Union[str, Any]]]] = None,
        dependencies: Optional[Sequence[Depends]] = None,
        default_response_class: Type[Response] = Default(JSONResponse),
        docs_url: Optional[str] = "/docs",
        redoc_url: Optional[str] = "/redoc",
        swagger_ui_oauth2_redirect_url: Optional[str] = "/docs/oauth2-redirect",
        swagger_ui_init_oauth: Optional[Dict[str, Any]] = None,
        middleware: Optional[Sequence[Middleware]] = None,
        exception_handlers: Optional[Dict[Union[int, Type[Exception]], Any]] = None,
        on_startup: Optional[Sequence[Callable[[], Any]]] = None,
        on_shutdown: Optional[Sequence[Callable[[], Any]]] = None,
        terms_of_service: Optional[str] = None,
        contact: Optional[Dict[str, Union[str, Any]]] = None,
        license_info: Optional[Dict[str, Union[str, Any]]] = None,
        openapi_prefix: str = "",
        root_path: str = "",
        root_path_in_servers: bool = True,
        responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
        callbacks: Optional[List[Dict[str, Any]]] = None,
        webhooks: Optional[Dict[str, APIRouter]] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: bool = True,
        swagger_ui_parameters: Optional[Dict[str, Any]] = None,
        async: bool = True,
        **extra: Any,
    ) -> None:
        """
        Initialize a FastAPI application.

        ## Arguments

        * `debug`: Enable debug mode.
        * `routes`: A list of routes to serve incoming HTTP and WebSocket requests.
        * `title`: The title of the API.
        * `description`: A short description of the API.
        * `version`: The version of the API.
        * `openapi_url`: The URL where the OpenAPI schema will be served from.
        * `openapi_tags`: A list of tags used by OpenAPI.
        * `servers`: A list of servers used by OpenAPI.
        * `dependencies`: A list of global dependencies.
        * `default_response_class`: The default response class to be used.
        * `docs_url`: The URL where the Swagger UI will be served from.
        * `redoc_url`: The URL where the ReDoc documentation will be served from.
        * `swagger_ui_oauth2_redirect_url`: The OAuth2 redirect URL for Swagger UI.
        * `swagger_ui_init_oauth`: The OAuth2 configuration for Swagger UI.
        * `middleware`: A list of middleware to run for every request.
        * `exception_handlers`: A dictionary of exception handlers.
        * `on_startup`: A list of startup event handlers.
        * `on_shutdown`: A list of shutdown event handlers.
        * `terms_of_service`: The terms of service for the API.
        * `contact`: Contact information for the API.
        * `license_info`: License information for the API.
        * `openapi_prefix`: The prefix for the OpenAPI URL.
        * `root_path`: The root path where the API is mounted.
        * `root_path_in_servers`: Whether to include the root path in the servers list.
        * `responses`: Additional responses to be included in the OpenAPI schema.
        * `callbacks`: Callbacks for the OpenAPI schema.
        * `webhooks`: Webhooks for the OpenAPI schema.
        * `deprecated`: Whether the API is deprecated.
        * `include_in_schema`: Whether to include the API in the OpenAPI schema.
        * `swagger_ui_parameters`: Additional parameters for Swagger UI.
        * `async`: Whether to enable async mode.
        * `**extra`: Additional keyword arguments to pass to Starlette.
        """
        self._debug: bool = debug
        self.state: Dict[str, Any] = {}
        self.router: routing.APIRouter = routing.APIRouter(
            routes=routes,
            dependency_overrides_provider=self,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            default_response_class=default_response_class,
        )
        self.title = title
        self.description = description
        self.version = version
        self.terms_of_service = terms_of_service
        self.contact = contact
        self.license_info = license_info
        self.openapi_url = openapi_url
        self.openapi_tags = openapi_tags
        self.servers = servers or []
        self.root_path = root_path
        self.root_path_in_servers = root_path_in_servers
        self.openapi_prefix = openapi_prefix
        self.dependencies = list(dependencies or [])
        self.user_middleware: List[Middleware] = list(middleware or [])
        self.middleware_stack: ASGIApp = self.build_middleware_stack()
        self.exception_handlers: Dict[Union[int, Type[Exception]], Any] = (
            dict(exception_handlers or {})
        )
        self.routes: List[BaseRoute] = []
        self.routes.extend(self.router.routes)
        self.setup()
        self.openapi_schema: Optional[Dict[str, Any]] = None
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.swagger_ui_oauth2_redirect_url = swagger_ui_oauth2_redirect_url
        self.swagger_ui_init_oauth = swagger_ui_init_oauth
        self.swagger_ui_parameters = swagger_ui_parameters
        self.webhooks = webhooks
        self.include_in_schema = include_in_schema
        self.async_mode = async
        self.extra = extra
        self.responses = responses
        self.callbacks = callbacks
        self.deprecated = deprecated

        # Initialize Starlette
        super().__init__(
            debug=debug,
            routes=self.routes,
            middleware=self.user_middleware,
            exception_handlers=self.exception_handlers,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=self.router.lifespan_context,
        )

        # Setup OpenAPI
        if self.openapi_url:
            assert self.openapi_url.startswith("/"), "openapi_url should start with '/'"
            self.add_route(
                self.openapi_url,
                lambda r: self.openapi(r),
                include_in_schema=False,
            )

        # Setup docs
        if self.docs_url:
            assert self.docs_url.startswith("/"), "docs_url should start with '/'"
            self.add_route(
                self.docs_url,
                lambda r: self.docs(r),
                include_in_schema=False,
            )

        # Setup redoc
        if self.redoc_url:
            assert self.redoc_url.startswith("/"), "redoc_url should start with '/'"
            self.add_route(
                self.redoc_url,
                lambda r: self.redoc(r),
                include_in_schema=False,
            )

        # Setup swagger UI OAuth2 redirect
        if self.swagger_ui_oauth2_redirect_url:
            assert (
                self.swagger_ui_oauth2_redirect_url.startswith("/"
            ), "swagger_ui_oauth2_redirect_url should start with '/'"
            self.add_route(
                self.swagger_ui_oauth2_redirect_url,
                lambda r: self.swagger_ui_oauth2_redirect(r),
                include_in_schema=False,
            )

    def setup(self) -> None:
        """Setup the application."""
        self.add_exception_handler(StarletteHTTPException, self.http_exception)
        self.add_exception_handler(RequestValidationError, self.request_validation_exception)

    def build_middleware_stack(self) -> ASGIApp:
        """Build the middleware stack."""
        app = self.router
        for middleware in reversed(self.user_middleware):
            app = middleware.cls(app, **middleware.options)
        return app

    async def openapi(self, request: Request) -> JSONResponse:
        """Return the OpenAPI schema."""
        if self.openapi_schema:
            return JSONResponse(self.openapi_schema)
        self.openapi_schema = get_openapi(
            title=self.title,
            version=self.version,
            description=self.description,
            routes=self.routes,
            tags=self.openapi_tags,
            servers=self.servers,
            terms_of_service=self.terms_of_service,
            contact=self.contact,
            license_info=self.license_info,
            webhooks=self.webhooks,
        )
        return JSONResponse(self.openapi_schema)

    async def docs(self, request: Request) -> HTMLResponse:
        """Return the Swagger UI documentation."""
        return get_swagger_ui_html(
            openapi_url=self.openapi_url,
            title=self.title + " - Swagger UI",
            oauth2_redirect_url=self.swagger_ui_oauth2_redirect_url,
            init_oauth=self.swagger_ui_init_oauth,
            swagger_ui_parameters=self.swagger_ui_parameters,
        )

    async def redoc(self, request: Request) -> HTMLResponse:
        """Return the ReDoc documentation."""
        return get_redoc_html(
            openapi_url=self.openapi_url,
            title=self.title + " - ReDoc",
        )

    async def swagger_ui_oauth2_redirect(self, request: Request) -> HTMLResponse:
        """Return the Swagger UI OAuth2 redirect page."""
        return get_swagger_ui_oauth2_redirect_html()

    def add_exception_handler(
        self,
        exc_class_or_status_code: Union[int, Type[Exception]],
        handler: Callable[[Request, Any], Any],
    ) -> None:
        """Add an exception handler."""
        if isinstance(exc_class_or_status_code, int):
            self.exception_handlers[exc_class_or_status_code] = handler
        else:
            self.exception_handlers[exc_class_or_status_code] = handler

    async def http_exception(self, request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handle HTTP exceptions."""
        return http_exception_handler(request, exc)

    async def request_validation_exception(
        self, request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation exceptions."""
        return request_validation_exception_handler(request, exc)

    def include_router(
        self,
        router: APIRouter,
        *,
        prefix: str = "",
        tags: Optional[List[str]] = None,
        dependencies: Optional[Sequence[Depends]] = None,
        responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: bool = True,
        default_response_class: Type[Response] = Default(JSONResponse),
        callbacks: Optional[List[Dict[str, Any]]] = None,
        generate_unique_id_function: Optional[Callable[[APIRoute], str]] = Default(
            routing.generate_unique_id
        ),
    ) -> None:
        """Include a router in the application."""
        self.router.include_router(
            router,
            prefix=prefix,
            tags=tags,
            dependencies=dependencies,
            responses=responses,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            default_response_class=default_response_class,
            callbacks=callbacks,
            generate_unique_id_function=generate_unique_id_function,
        )

    def add_route(
        self,
        path: str,
        route: Union[BaseRoute, Callable[..., Any]],
        *,
        methods: Optional[List[str]] = None,
        name: Optional[str] = None,
        include_in_schema: bool = True,
    ) -> None:
        """Add a route to the application."""
        self.router.add_route(
            path, route, methods=methods, name=name, include_in_schema=include_in_schema
        )

    def add_websocket_route(
        self,
        path: str,
        route: Callable[..., Any],
        *,
        name: Optional[str] = None,
    ) -> None:
        """Add a WebSocket route to the application."""
        self.router.add_websocket_route(path, route, name=name)

    def add_middleware(
        self,
        middleware_class: type,
        **options: Any,
    ) -> None:
        """Add middleware to the application."""
        self.user_middleware.insert(0, Middleware(middleware_class, **options))
        self.middleware_stack = self.build_middleware_stack()

    def mount(
        self,
        path: str,
        app: ASGIApp,
        name: Optional[str] = None,
    ) -> None:
        """Mount an ASGI application."""
        self.router.mount(path, app, name=name)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Call the application."""
        scope["root_path"] = self.root_path
        await self.middleware_stack(scope, receive, send)
