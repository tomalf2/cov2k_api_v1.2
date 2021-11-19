from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi_doc(app: FastAPI):
    def inner_f():
        nonlocal app
        DOCS_TITLE = "CoV2K API"    # TODO change
        DOCS_VERSION = "1.2"        # TODO change
        openapi_schema = get_openapi(
            title=DOCS_TITLE,       # or app.title
            version=DOCS_VERSION,   # or app.version
            routes=app.routes
        )
        openapi_schema["info"] = {
            "title": DOCS_TITLE,
            "version": DOCS_VERSION,
            "description": "This RESTful API exposes one endpoint for each entity of CoV2K (e.g., for the Evidence entity we use the endpoint /evidences.\n For each endpoint, there are four possible uses: \ni) without parameters; ii) with a path parameter specifying the entity identifier;\n iii) with a query parameter specifying an attribute-value pair for that entity; iv) with a query parameter linking that entity to another entity through a relationship.",
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
        openapi_schema["paths"]["/combine"]["get"]["summary"] = "Chain endpoints"
        #openapi_schema["paths"]["/variants/{variant_id}"]["get"]["summary"] = "Get one "
        openapi_schema["paths"]["/namings/{naming_id}"]["get"]["summary"] = "Get one Naming"
        openapi_schema["paths"]["/contexts/{context_id}"]["get"]["summary"] = "Get one Context"
        openapi_schema["paths"]["/variants/{variant_id}"]["get"]["summary"] = "Get one Variant"
        openapi_schema["paths"]["/effects/{effect_id}"]["get"]["summary"] = "Get one Effect"
        openapi_schema["paths"]["/evidences/{evidence_id}"]["get"]["summary"] = "Get one Evidence"
        openapi_schema["paths"]["/nuc_positional_mutations/{nuc_positional_mutation_id}"]["get"]["summary"] = "Get one Nuc Positional Mutation"
        openapi_schema["paths"]["/aa_positional_changes/{aa_positional_change_id}"]["get"]["summary"] = "Get one Aa Positional Change"
        openapi_schema["paths"]["/aa_change_groups/{aa_change_group_id}"]["get"]["summary"] = "Get one Aa Change Group"
        openapi_schema["paths"]["/nuc_annotations/{nuc_annotation_id}"]["get"]["summary"] = "Get one Nuc Annotation"
        openapi_schema["paths"]["/proteins/{protein_id}"]["get"]["summary"] = "Get one Protein"
        openapi_schema["paths"]["/protein_regions/{protein_region_id}"]["get"]["summary"] = "Get one Protein Region"
        openapi_schema["paths"]["/aa_residue_changes/{aa_residue_change_id}"]["get"]["summary"] = "Get one Aa Residue Change"
        #openapi_schema["paths"]["/aa_residues"]["get"]["summary"] = "Get Aa Residues"
        openapi_schema["paths"]["/aa_residues_ref"]["get"]["summary"] = "Get reference Aa Residues"
        openapi_schema["paths"]["/aa_residues_alt"]["get"]["summary"] = "Get alternative Aa Residues"
        openapi_schema["paths"]["/aa_residues/{aa_residue_id}"]["get"]["summary"] = "Get one Aa Residue"
        openapi_schema["paths"]["/aa_residues_ref/{aa_residue_id}"]["get"]["summary"] = "Get one reference Aa Residue"
        openapi_schema["paths"]["/aa_residues_alt/{aa_residue_id}"]["get"]["summary"] = "Get one alternative Aa Residue"
        openapi_schema["paths"]["/sequences/{sequence_id}"]["get"]["summary"] = "Get one Sequence"
        openapi_schema["paths"]["/host_samples/{host_sample_id}"]["get"]["summary"] = "Get one Host Sample"
        openapi_schema["paths"]["/nuc_mutations/{nuc_mutation_id}"]["get"]["summary"] = "Get one Nuc Mutation"
        openapi_schema["paths"]["/aa_changes/{aa_change_id}"]["get"]["summary"] = "Get one Aa Change"
        openapi_schema["paths"]["/epitopes/{epitope_id}"]["get"]["summary"] = "Get one Epitope"
        openapi_schema["paths"]["/assays/{assay_id}"]["get"]["summary"] = "Get one Assay"
        #openapi_schema["paths"]["/variants"]["get"]["summary"] = "Summary/Name for Variants (QUERY PARAM)"
        #openapi_schema["paths"]["/effects"]["get"]["summary"] = "Summary/Name for Effects (QUERY PARAM)"
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    return inner_f
