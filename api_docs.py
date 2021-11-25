import pprint

from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi_doc(app: FastAPI):
    def inner_f():
        nonlocal app
        DOCS_TITLE = "CoV2K API"
        DOCS_VERSION = "1.2"
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
            "license": {
                "name": "Apache 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0.html"
            },
        }
        openapi_schema["paths"]["/combine/{full_path}"]["get"]["summary"] = "Chain endpoints"
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
        find_enpoint_parameter(openapi_schema, "/variants", "naming_id")["description"] = "Returns the Variant connected to a specific Naming"
        find_enpoint_parameter(openapi_schema, "/variants", "effect_id")["description"] = "Returns Variants connected to a specific Effect"
        find_enpoint_parameter(openapi_schema, "/variants", "context_id")["description"] = "Returns the Variant connected to a specific Context"

        find_enpoint_parameter(openapi_schema, "/namings", "variant_id")["description"] = "Returns Namings connected to a specific Variant"
        find_enpoint_parameter(openapi_schema, "/namings", "organization")["description"] = "Returns Namings of a specific organization"
        find_enpoint_parameter(openapi_schema, "/namings", "v_class")["description"] = "Returns Namings of a specific class (e.g., VoI or VuM)"

        find_enpoint_parameter(openapi_schema, "/contexts", "variant_id")["description"] = "Returns Contexts connected to a specific Variant"
        find_enpoint_parameter(openapi_schema, "/contexts", "aa_positional_change_id")["description"] = "Returns Contexts that contain a specific Aa Positional Change (e.g., S:D614G)"
        find_enpoint_parameter(openapi_schema, "/contexts", "nuc_positional_mutation_id")["description"] = "Returns Contexts connected to a specific Nuc Positional Mutation (e.g., G1942T)"
        find_enpoint_parameter(openapi_schema, "/contexts", "owner")["description"] = "Returns Contexts of a given owner"
        find_enpoint_parameter(openapi_schema, "/contexts", "rule_description")["description"] = "Returns Contexts with a given rule description"

        find_enpoint_parameter(openapi_schema, "/effects", "variant_id")["description"] = "Returns Effects connected to a specific Variant"
        find_enpoint_parameter(openapi_schema, "/effects", "aa_positional_change_id")["description"] = "Returns Effects of a specific Aa Positional Change (e.g., S:D614G)"
        find_enpoint_parameter(openapi_schema, "/effects", "evidence_id")["description"] = "Returns Effects contained in a specific Evidence"
        find_enpoint_parameter(openapi_schema, "/effects", "aa_change_group_id")["description"] = "Returns Effects connected to a specific Aa Change Group"
        find_enpoint_parameter(openapi_schema, "/effects", "type")["description"] = "Returns Effects of a type (e.g., infectivity, viral_transmission...)"
        find_enpoint_parameter(openapi_schema, "/effects", "lv")["description"] = "Returns Effects of a certain level (lower, higher, null)"
        find_enpoint_parameter(openapi_schema, "/effects", "method")["description"] = "Returns Effects documented with a specific method (epidemiological, experimental, computational, inferred)"

        find_enpoint_parameter(openapi_schema, "/evidences", "effect_id")["description"] = "Returns Evidences connected to a specific Effect"
        find_enpoint_parameter(openapi_schema, "/evidences", "citation")["description"] = "Returns Evidences of a given citation (e.g., McCallum et al. (2021))"
        find_enpoint_parameter(openapi_schema, "/evidences", "type")["description"] = "Returns Evidences of a specific type (e.g., published or preprint)"
        find_enpoint_parameter(openapi_schema, "/evidences", "uri")["description"] = "Returns Evidence with a given URI"
        find_enpoint_parameter(openapi_schema, "/evidences", "publisher")["description"] = "Returns Evidences of a specified publisher (bioRxiv or Nature...)"

        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "context_id")["description"] = "Returns Nuc Positional Mutations of a specific Context"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "nuc_annotation_id")["description"] = "Returns Nuc Positional Mutations contained in a specific Nuc Annotation"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "nuc_mutation_id")["description"] = "Returns the Nuc Positional Mutation corresponding to a specific data Nuc Mutation"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "reference")["description"] = "Returns the Nuc Positional Mutations with a given reference base"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "position")["description"] = "Returns the Nuc Positional Mutations occurring in a certain position of the reference sequence"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "alternative")["description"] = "Returns the Nuc Positional Mutations with a given alternative base"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "type")["description"] = "Returns the Nuc Positional Mutations of a given type (INS, DEL, SUB)"
        find_enpoint_parameter(openapi_schema, "/nuc_positional_mutations", "length")["description"] = "Returns the Nuc Positional Mutations of a given length (deletions and substitutions are always long 1)"

        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "context_id")["description"] = "Returns Aa Positional Changes of a specific Context"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "effect_id")["description"] = "Returns Aa Positional Changes that present a given Effect"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "protein_id")["description"] = "Returns Aa Positional Changes that present a given Effect"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "aa_change_group_id")["description"] = "Returns Aa Positional Changes that are part of a specific Aa Change Group"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "aa_residue_change_id")["description"] = "Returns Aa Positional Changes corresponding to (non positional) Aa Residue Changes"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "epitope_id")["description"] = "Returns Aa Positional Changes that fall in the interval of given Epitope"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "aa_change_id")["description"] = "Returns the Aa Positional Change corresponding to a specific data AA Change"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "reference")["description"] = "Returns the Aa Positional Changes with a given reference residue"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "position")["description"] = "Returns the Aa Positional Change occurring in a given position of the protein"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "alternative")["description"] = "Returns the Aa Positional Change with a given alternative residue"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "type")["description"] = "Returns the Aa Positional Change of a given type (INS, DEL, SUB)"
        find_enpoint_parameter(openapi_schema, "/aa_positional_changes", "length")["description"] = "Returns the Aa Positional Change of a given length (deletions and substitutions are always long 1)"

        find_enpoint_parameter(openapi_schema, "/aa_change_groups", "aa_positional_change_id")["description"] = "Returns Aa Change Groups that contain a given Aa Positional Change"
        find_enpoint_parameter(openapi_schema, "/aa_change_groups", "effect_id")["description"] = "Returns the Aa Change Group with a specified Effect"

        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "protein_id")["description"] = "Returns the Nuc Annotation corresponding to a given Protein"
        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "nuc_positional_mutation_id")["description"] = "Returns Nuc Annotations that contain a given Nuc Positional Mutation"
        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "name")["description"] = "Returns the Nuc Annotation with the specified name"
        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "start_on_ref")["description"] = "Returns Nuc Annotations starting in the specified coordinate"
        find_enpoint_parameter(openapi_schema, "/nuc_annotations", "stop_on_ref")["description"] = "Returns Nuc Annotations ending in the specified coordinate"

        find_enpoint_parameter(openapi_schema, "/proteins", "nuc_annotation_id")["description"] = "Returns the Protein corresponding to a given Nuc Annotation"
        find_enpoint_parameter(openapi_schema, "/proteins", "epitope_id")["description"] = "Returns the Protein to which a given Epitope belongs"
        find_enpoint_parameter(openapi_schema, "/proteins", "protein_region_id")["description"] = "Returns the Protein that contains a given Protein Region"
        find_enpoint_parameter(openapi_schema, "/proteins", "aa_positional_change_id")["description"] = "Returns the Protein on which the specified Aa Positional Change falls"
        find_enpoint_parameter(openapi_schema, "/proteins", "aa_change_id")["description"] = "Returns the Protein on which the specified data Aa Change falls"
        find_enpoint_parameter(openapi_schema, "/proteins", "aa_length")["description"] = "Returns the Protein with a given length"
        find_enpoint_parameter(openapi_schema, "/proteins", "aa_sequence")["description"] = "Returns the Protein with the specified sequence of amino acid residues"

        find_enpoint_parameter(openapi_schema, "/protein_regions", "protein_id")["description"] = "Returns Protein Regions that belong to the given Protein"
        find_enpoint_parameter(openapi_schema, "/protein_regions", "name")["description"] = "Returns Protein Regions with a specified name"
        find_enpoint_parameter(openapi_schema, "/protein_regions", "type")["description"] = "Returns Protein Regions with a specified type (chain, topo_dom, domain...)"
        find_enpoint_parameter(openapi_schema, "/protein_regions", "category")["description"] = "Returns Protein Regions of a specific category"
        find_enpoint_parameter(openapi_schema, "/protein_regions", "start_on_protein")["description"] = "Returns Protein Regions that start on the specified coordinate"
        find_enpoint_parameter(openapi_schema, "/protein_regions", "stop_on_protein")["description"] = "Returns Protein Regions that end on the specified coordinate"

        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "aa_positional_change_id")["description"] = "Returns the AA Residue Change corresponding to a given Aa Positional Change"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "aa_residue_id")["description"] = "Returns AA Residue Changes that involve a given Aa Residue (either as reference or alternative)"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "reference")["description"] = "Returns AA Residue Changes that exhibit the given value as the reference AA Residue"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "alternative")["description"] = "Returns AA Residue Changes that exhibit the given value as the alternative AA Residue"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "grantham_distance")["description"] = "Returns AA Residue Changes that exhibit the given value as the Grantham distance"
        find_enpoint_parameter(openapi_schema, "/aa_residue_changes", "type")["description"] = "Returns AA Residue Changes of the given type (radical or conservative)"

        find_enpoint_parameter(openapi_schema, "/aa_residues", "aa_residue_change_id")["description"] = "Returns AA Residues involved in the specified AA Residue Change (both, only reference, only alternative de pending on the called endpoint)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "aa_residue_change_id")["description"] = "Returns AA Residues involved in the specified AA Residue Change (both, only reference, only alternative de pending on the called endpoint)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "aa_residue_change_id")["description"] = "Returns AA Residues involved in the specified AA Residue Change (both, only reference, only alternative de pending on the called endpoint)"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "molecular_weight")["description"] = "Returns AA Residues with specific molecular weight value"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "isoelectric_point")["description"] = "Returns AA Residues with specific isoelectric point value"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "hydrophobicity")["description"] = "Returns AA Residues with the specified hydrophobicity value"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "potential_side_chain_h_bonds")["description"] = "Returns AA Residues with a given number of potential side chain h bonds"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "polarity")["description"] = "Returns AA Residues with given polarity (Polar or Nonpolar)"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "r_group_structure")["description"] = "Returns AA Residues with the specified r group structure (Aromatic or Aliphatic)"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "charge")["description"] = "Returns AA Residues with the given charge value (null, Uncharged, Positive or Negative charge)"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "essentiality")["description"] = "Returns AA Residues with the specified essentiality value (Essential or Non essential)"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "side_chain_flexibility")["description"] = "Returns AA Residues with the specified side chain flexibility value (High, Moderate, Low)"
        find_enpoint_parameter(openapi_schema, "/aa_residues", "chemical_group_in_the_side_chain")["description"] = "Returns AA Residues with the specified chemical group in the side chain (e.g.. Methylene)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "molecular_weight")["description"] = "Returns reference AA Residues with specific molecular weight value"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "isoelectric_point")["description"] = "Returns reference AA Residues with specific isoelectric point value"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "hydrophobicity")["description"] = "Returns reference AA Residues with the specified hydrophobicity value"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "potential_side_chain_h_bonds")["description"] = "Returns reference AA Residues with a given number of potential side chain h bonds"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "polarity")["description"] = "Returns reference AA Residues with given polarity (Polar or Nonpolar)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "r_group_structure")["description"] = "Returns reference AA Residues with the specified r group structure (Aromatic or Aliphatic)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "charge")["description"] = "Returns reference AA Residues with the given charge value (null, Uncharged, Positive or Negative charge)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "essentiality")["description"] = "Returns reference AA Residues with the specified essentiality value (Essential or Non essential)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "side_chain_flexibility")["description"] = "Returns reference AA Residues with the specified side chain flexibility value (High, Moderate, Low)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_ref", "chemical_group_in_the_side_chain")["description"] = "Returns reference AA Residues with the specified chemical group in the side chain (e.g.. Methylene)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "molecular_weight")["description"] = "Returns alternative AA Residues with specific molecular weight value"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "isoelectric_point")["description"] = "Returns alternative AA Residues with specific isoelectric point value"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "hydrophobicity")["description"] = "Returns alternative AA Residues with the specified hydrophobicity value"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "potential_side_chain_h_bonds")["description"] = "Returns alternative AA Residues with a given number of potential side chain h bonds"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "polarity")["description"] = "Returns alternative AA Residues with given polarity (Polar or Nonpolar)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "r_group_structure")["description"] = "Returns alternative AA Residues with the specified r group structure (Aromatic or Aliphatic)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "charge")["description"] = "Returns alternative AA Residues with the given charge value (null, Uncharged, Positive or Negative charge)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "essentiality")["description"] = "Returns alternative AA Residues with the specified essentiality value (Essential or Non essential)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "side_chain_flexibility")["description"] = "Returns alternative AA Residues with the specified side chain flexibility value (High, Moderate, Low)"
        find_enpoint_parameter(openapi_schema, "/aa_residues_alt", "chemical_group_in_the_side_chain")["description"] = "Returns alternative AA Residues with the specified chemical group in the side chain (e.g.. Methylene)"

        find_enpoint_parameter(openapi_schema, "/sequences", "nuc_mutation_id")["description"] = "Returns Sequences that exhibit the given Nuc Mutation"
        find_enpoint_parameter(openapi_schema, "/sequences", "aa_change_id")["description"] = "Returns Sequences that exhibit the given Aa Change"
        find_enpoint_parameter(openapi_schema, "/sequences", "host_sample_id")["description"] = "Returns Sequences sequenced from the given Host Sample"
        find_enpoint_parameter(openapi_schema, "/sequences", "accession_id")["description"] = "Returns the Sequence that corresponds to the given accession_id"
        find_enpoint_parameter(openapi_schema, "/sequences", "source_database")["description"] = "Returns Sequences from the specified source database (COG-UK or GenBank)"
        find_enpoint_parameter(openapi_schema, "/sequences", "length")["description"] = "Returns Sequences with the specified length"
        find_enpoint_parameter(openapi_schema, "/sequences", "n_percentage")["description"] = "Returns Sequences that show the specified N%"
        find_enpoint_parameter(openapi_schema, "/sequences", "gc_percentage")["description"] = "Returns Sequences that show the specified GC%"

        find_enpoint_parameter(openapi_schema, "/host_samples", "sequence_id")["description"] = "Returns the Host Sample of a given Sequence"
        find_enpoint_parameter(openapi_schema, "/host_samples", "continent")["description"] = "Returns the Host Sample collected in the specified continent"
        find_enpoint_parameter(openapi_schema, "/host_samples", "country")["description"] = "Returns the Host Sample collected in the specified country"
        find_enpoint_parameter(openapi_schema, "/host_samples", "region")["description"] = "Returns the Host Sample collected in the specified region"
        find_enpoint_parameter(openapi_schema, "/host_samples", "collection_date")["description"] = "Returns the Host Samples collected in a specific date"
        find_enpoint_parameter(openapi_schema, "/host_samples", "host_species")["description"] = "Returns the Host Samples of a given host species"

        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "sequence_id")["description"] = "Returns the Nuc Mutations of a given Sequence"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "nuc_positional_mutation_id")["description"] = "Returns the data Nuc Mutations corresponding to the given Nuc Positional Mutation"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "reference")["description"] = "Returns the data Nuc Mutations with a given reference base"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "position")["description"] = "Returns the data Nuc Mutations occurring in a given position of the full sequence"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "alternative")["description"] = "Returns the data Nuc Mutations with a given alternative base"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "type")["description"] = "Returns the data Nuc Mutations of a given type (DEL, INS, SUB)"
        find_enpoint_parameter(openapi_schema, "/nuc_mutations", "length")["description"] = "Returns the data Nuc Mutations of a given length"

        find_enpoint_parameter(openapi_schema, "/aa_changes", "sequence_id")["description"] = "Returns the Aa Changes of a given Sequence"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "protein_id")["description"] = "Returns the Aa Changes contained in a given Protein"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "aa_positional_change_id")["description"] = "Returns the Aa Changes corresponding to a given Aa Positional Change"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "reference")["description"] = "Returns the Aa Changes with a given reference residue"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "position")["description"] = "Returns the Aa Changes occurring in a given position"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "alternative")["description"] = "Returns the Aa Changes with a given alternative residue"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "type")["description"] = "Returns the Aa Changes of a given type (INS, DEL, SUB)"
        find_enpoint_parameter(openapi_schema, "/aa_changes", "length")["description"] = "Returns the Aa Changes of a given length (DEL and SUB are long 1 residue)"

        find_enpoint_parameter(openapi_schema, "/epitopes", "assay_id")["description"] = "Returns the Epitopes of a given Assay"
        find_enpoint_parameter(openapi_schema, "/epitopes", "protein_id")["description"] = "Returns the Epitopes of a given Protein"
        find_enpoint_parameter(openapi_schema, "/epitopes", "aa_positional_change_id")["description"] = "Returns the Epitopes that contain a given Aa Positional Change in their range"
        find_enpoint_parameter(openapi_schema, "/epitopes", "host_species")["description"] = "Returns the Epitopes proposed for a given host species (e.g. human)"
        find_enpoint_parameter(openapi_schema, "/epitopes", "epitope_start")["description"] = "Returns the Epitopes with a given start coordinate"
        find_enpoint_parameter(openapi_schema, "/epitopes", "epitope_stop")["description"] = "Returns the Epitopes  with a given stop coordinate"

        find_enpoint_parameter(openapi_schema, "/assays", "epitope_id")["description"] = "Returns the Assay of a given Epitope"
        find_enpoint_parameter(openapi_schema, "/assays", "assay_type")["description"] = "Returns the Assays with given type of assay (T/B cell or MHC ligand)"
        find_enpoint_parameter(openapi_schema, "/assays", "mhc_class")["description"] = "Returns the Assays with a given MHC class"
        find_enpoint_parameter(openapi_schema, "/assays", "hla_restriction")["description"] = "Returns the Assays restricted to a given HLA (Human Leukocyte Antigen system)"

        app.openapi_schema = openapi_schema
        return app.openapi_schema
    return inner_f


def find_enpoint_parameter(docs: dict, in_endpoint: str, parameter_name: str):
    return next(x for x in docs["paths"][in_endpoint]["get"]["parameters"] if x["name"] == parameter_name)
