from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi_doc(app: FastAPI):
    def inner_f():
        nonlocal app
        DOCS_TITLE = "NEW TITLE"    # TODO change
        DOCS_VERSION = "1.2"        # TODO change
        openapi_schema = get_openapi(
            title=DOCS_TITLE,       # or app.title
            version=DOCS_VERSION,   # or app.version
            routes=app.routes
        )
        openapi_schema["info"] = {
            "title": DOCS_TITLE,
            "version": DOCS_VERSION,
            "description": "My custom API description",
            # "termsOfService": "http://programming-languages.com/terms/",
            # "contact": {
            #     "name": "Get Help with this API",
            #     "url": "http://www.programming-languages.com/help",
            #     "email": "support@programming-languages.com"
            # },
            # "license": {
            #     "name": "Apache 2.0",
            #     "url": "https://www.apache.org/licenses/LICENSE-2.0.html"
            # },
        }
        openapi_schema["paths"]["/variants"]["get"]["summary"] = "Summary/Name for Variants (QUERY PARAM)"
        openapi_schema["paths"]["/variants/{variant_id}"]["get"]["summary"] = "Summary/Name for Variant (PATH PARAM)"
        openapi_schema["paths"]["/effects"]["get"]["summary"] = "Summary/Name for Effects (QUERY PARAM)"
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    return inner_f
