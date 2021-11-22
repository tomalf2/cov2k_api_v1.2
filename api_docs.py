import pprint

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
        openapi_schema["paths"]["/combine/{full_path}"]["get"]["summary"] = "Chain endpoints"
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
        pprint.pprint(openapi_schema["paths"]["/aa_residue_changes"]["get"]["parameters"])

        # DESCRIPTION OF QUERY PARAMETERS
        #find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "aa_residue_id")["description"] = "NOOOOOOOOOOOOO"
        find_enpoint_parameter(openapi_schema, "/variants", "naming_id")["description"] = "Returns the Variant connected to a specific Naming"
        find_enpoint_parameter(openapi_schema, "/variants", "effect_id")["description"] = "Returns Variants connected to a specific Effect"
        find_enpoint_parameter(openapi_schema, "/variants", "context_id")["description"] = "Returns the Variant connected to a specific Context"


        find_enpoint_parameter(openapi_schema, "/namings", "variant_id")["description"] = "Returns Namings connected to a specific Variant"

        find_enpoint_parameter(openapi_schema, "/contexts", "variant_id")["description"] = "Returns Contexts connected to a specific Variant"
        find_enpoint_parameter(openapi_schema, "/contexts", "aa_positional_change_id")["description"] = "Returns Contexts that contain a specific Aa Positional Change (e.g., S:D614G)"
        find_enpoint_parameter(openapi_schema, "/contexts", "nuc_positional_mutation_id")["description"] = "Returns Contexts connected to a specific Nuc Positional Mutation (e.g., G1942T)"

        find_enpoint_parameter(openapi_schema, "/effects", "variant_id")["description"] = "Returns Effects connected to a specific Variant"
        find_enpoint_parameter(openapi_schema, "/effects", "aa_positional_change_id")["description"] = "Returns Effects of a specific Aa Positional Change (e.g., S:D614G)"
        find_enpoint_parameter(openapi_schema, "/effects", "evidence_id")["description"] = "Returns Effects contained in a specific Evidence"
        find_enpoint_parameter(openapi_schema, "/effects", "aa_change_group_id")["description"] = "Returns Effects connected to a specific Aa Change Group"

        find_enpoint_parameter(openapi_schema, "/evidences", "effect_id")["description"] = "Returns Evidences connected to a specific Effect"

        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "context_id")["description"] = "Returns Nuc Positional Mutations of a specific Context"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "nuc_annotation_id")["description"] = "Returns Nuc Positional Mutations contained in a specific Nuc Annotation"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "nuc_mutation_id")["description"] = "Returns the Nuc Positional Mutation corresponding to a specific data Nuc Mutation"

        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "context_id")["description"] = "Returns Aa Positional Changes of a specific Context"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "effect_id")["description"] = "Returns Aa Positional Changes that present a given Effect"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "protein_id")["description"] = "Returns Aa Positional Changes that present a given Effect"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "aa_change_group_id")["description"] = "Returns Aa Positional Changes that are part of a specific Aa Change Group"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "aa_residue_change_id")["description"] = "Returns Aa Positional Changes corresponding to (non positional) Aa Residue Changes"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "epitope_id")["description"] = "Returns Aa Positional Changes that fall in the interval of given Epitope"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "aa_change_id")["description"] = "Returns the Aa Positional Change corresponding to a specific data AA Change"

        find_enpoint_parameter(openapi_schema, "/aa_positional_change_id", "aa_residue_id")["description"] = "Returns Aa Change Groups that contain a given Aa Positional Change"
        find_enpoint_parameter(openapi_schema, "/effect_id", "aa_residue_id")["description"] = "Returns the Aa Change Group with a specified Effect"

        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "protein_id")["description"] = "Returns the Nuc Annotation corresponding to a given Protein"
        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "nuc_positional_mutation_id")["description"] = "Returns Nuc Annotations that contain a given Nuc Positional Mutation"

        find_enpoint_parameter(openapi_schema, "/proteins", "nuc_annotation_id")["description"] = "Returns the Protein corresponding to a given Nuc Annotation"
        find_enpoint_parameter(openapi_schema, "/proteins", "epitope_id")["description"] = "Returns the Protein to which a given Epitope belongs"
        find_enpoint_parameter(openapi_schema, "/proteins", "protein_region_id")["description"] = "Returns the Protein that contains a given Protein Region"
        find_enpoint_parameter(openapi_schema, "/proteins", "aa_positional_change_id")["description"] = "Returns the Protein on which the specified Aa Positional Change falls"
        find_enpoint_parameter(openapi_schema, "/proteins", "aa_change_id")["description"] = "Returns the Protein on which the specified data Aa Change falls"

        find_enpoint_parameter(openapi_schema, "/protein_regions", "protein_id")["description"] = "Returns Protein Regions that belong to the given Protein"

        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "aa_positional_change_id")["description"] = "Returns the AA Residue Change corresponding to a given Aa Positional Change"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "aa_residue_id")["description"] = "Returns AA Residue Changes that involve a given Aa Residue (either as reference or alternative)"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "reference")["description"] = "Returns AA Residue Changes that exhibit the given value as the reference AA Residue"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "alternative")["description"] = "Returns AA Residue Changes that exhibit the given value as the alternative AA Residue"


        find_enpoint_parameter(openapi_schema, "/aa_residues", "aa_residue_change_id")["description"] = "Returns AA Residues involved in the specified AA Residue Change (both, only reference, only alternative de pending on the called endpoint)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "aa_residue_change_id")[
            "description"] = "Returns AA Residues involved in the specified AA Residue Change (both, only reference, only alternative de pending on the called endpoint)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "aa_residue_change_id")[
            "description"] = "Returns AA Residues involved in the specified AA Residue Change (both, only reference, only alternative de pending on the called endpoint)"

        find_enpoint_parameter(openapi_schema, "/sequences", "nuc_mutation_id")["description"] = "Returns Sequences that exhibit the given Nuc Mutation"
        find_enpoint_parameter(openapi_schema, "/sequences", "aa_change_id")["description"] = "Returns Sequences that exhibit the given Aa Change"
        find_enpoint_parameter(openapi_schema, "/sequences", "host_sample_id")["description"] = "Returns Sequences sequenced from the given Host Sample"

        find_enpoint_parameter(openapi_schema, "/host_samples", "sequence_id")["description"] = "Returns the Host Sample of a given Sequence"

        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "sequence_id")["description"] = "Returns the Nuc Mutations of a given Sequence"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "nuc_positional_mutation_id")["description"] = "Returns the data Nuc Mutations corresponding to the given Nuc Positional Mutation"

        find_enpoint_parameter(openapi_schema, "/sequence_id", "aa_residue_id")["description"] = "Returns the Aa Changes of a given Sequence"
        find_enpoint_parameter(openapi_schema, "/protein_id", "aa_residue_id")["description"] = "Returns the Aa Changes contained in a given Protein"
        find_enpoint_parameter(openapi_schema, "/aa_positional_change_id", "aa_residue_id")["description"] = "Returns the Aa Changes corresponding to a given Aa Positional Change"

        find_enpoint_parameter(openapi_schema, "/epitopes", "assay_id")["description"] = "Returns the Epitopes of a given Assay"
        find_enpoint_parameter(openapi_schema, "/epitopes", "protein_id")["description"] = "Returns the Epitopes of a given Protein"
        find_enpoint_parameter(openapi_schema, "/epitopes", "aa_positional_change_id")["description"] = "Returns the Epitopes that contain a given Aa Positional Change in their range"

        find_enpoint_parameter(openapi_schema, "/assays", "epitope_id")["description"] = "Returns the Assay of a given Epitope"
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    return inner_f


def find_enpoint_parameter(docs: dict, in_endpoint: str, parameter_name: str):
    return next(x for x in docs["paths"][in_endpoint]["get"]["parameters"] if x["name"] == parameter_name)
