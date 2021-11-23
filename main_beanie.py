import base64
import pprint
import re
import warnings
from enum import Enum
from typing import Optional, List, Callable

import bson.errors
import uvicorn
from fastapi import FastAPI, Request, status, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute, APIRouter
from starlette.responses import PlainTextResponse

from dal.kb_beanie.model import *
from dal.kb_beanie.projections import *
from dal.data_sqlalchemy.model import *
from dal.data_sqlalchemy.convert_prot_names import *
from api_exceptions import MyExceptions
from loguru import logger
from os.path import sep
from api_docs import custom_openapi_doc
from dal.data_sqlalchemy.model import _session_factory

import queries

app = FastAPI()


# Fixes MAX query parameter num to 1
# Logs and handles unexpected errors
@app.middleware("http")
async def log_request(request, call_next):
    ignored_params = 1 if request.query_params.get("page") is not None else 0
    ignored_params += 1 if request.query_params.get("limit") is not None else 0
    if len(request.query_params) - ignored_params <= 1:
        # try:
        return await call_next(request)
        # except:
            # return log_and_give_bad_request_response()
    else:
        return PlainTextResponse(status_code=status.HTTP_400_BAD_REQUEST
                                 , content=f"The API accepts only one query parameter at a time")


def log_and_raise_http_bad_request(additional_msg=None):
    logger.exception(additional_msg)
    raise HTTPException(detail="Something went wrong", status_code=status.HTTP_400_BAD_REQUEST)


def log_and_give_bad_request_response(additional_msg=None):
    logger.exception(additional_msg)
    PlainTextResponse("Something went wrong", status_code=status.HTTP_400_BAD_REQUEST)


all_available_entities = {'variants', 'namings', 'contexts', 'effects', 'evidences', 'nuc_positional_mutations',
                          'aa_positional_changes', 'nuc_annotations', 'proteins',
                          'protein_regions', 'aa_residue_changes', 'aa_residues', 'aa_residues_ref',
                          'aa_residues_alt',
                          'sequences', 'host_samples', 'nuc_mutations', 'aa_changes', 'epitopes', 'assays'}


class QueryTypes(Enum):
    PATH_PARM = 1
    QUERY_PARAM = 2
    NO_PARAM = 0


@app.get("/combine/{full_path:path}")
async def combine(full_path: str, request: Request, limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """The relationships of the abstract model can be combined (chained) one after the other through the /combine endpoint,
e.g., /combine/evidences/effects?aa_positional_change_id=S:L452R
extracts the evidences reporting effects on the Spike mutation L452R.\n
Pagination applies to the combination result and is mandatory
if the combination result refers to a data entity.\n
A basic error handling mechanism prohibits users to build combinations with cycles
(i.e., strings with repeated entities are illegal)."""
    # clean full_path
    while len(full_path) > 0 and full_path[-1] == '/':
        full_path = full_path[:-1]
    if len(full_path) == 0:
        raise MyExceptions.compose_request_no_entity_specified

    # check that first entity is valid (others are checked later)
    call_list = full_path.split('/')
    call_list = [x for x in call_list if x]
    if call_list[0] not in all_available_entities:
        raise MyExceptions.compose_request_unrecognised_command

    # remove page and limit from query params

    # find query type and detect unrecognised entities
    query_type = None
    path_param = None
    only_pagination_query_params = True if set(request.query_params.keys()).issubset(['limit', 'page']) else False
    if not request.query_params or only_pagination_query_params:
        # check for unrecognised entities (last one can be path parameter)
        if not set(call_list[:-1]).issubset(all_available_entities):
            raise MyExceptions.compose_request_unrecognised_command
        if call_list[-1] in all_available_entities:
            query_type = QueryTypes.NO_PARAM
        else:
            path_param = call_list[-1]
            call_list = call_list[:-1]
            query_type = QueryTypes.PATH_PARM
    else:
        if not set(call_list).issubset(all_available_entities):
            raise MyExceptions.compose_request_unrecognised_command
        query_type = QueryTypes.QUERY_PARAM

    # check for entity cycles
    if len(call_list) > len(set(call_list)):
        raise MyExceptions.compose_request_path_cycle_detected

    # description = {
    #     "cleaned path": full_path,
    #     "entities requested": split_entities,
    #     "query_type": query_type.name,
    #     "query params": request.query_params,
    #     "path param": path_param,
    #     "header params": request.headers
    # }

    async def make_request(entity_name, path_param, query_params):
        try:
            return await Entity2Request.make_function_call(entity_name, path_param, query_params)
        except TypeError as e:
            logger.exception("")
            if 'unexpected keyword argument' in e.args[0]:
                raise MyExceptions.compose_request_unrecognised_query_parameter
            else:
                log_and_raise_http_bad_request()
        except:
            logger.exception("")
            log_and_raise_http_bad_request()

    this_call = call_list.pop()
    final_result = set()
    # grab query parameters w/o pagination ones
    # ALL REQUESTS ARE PERFORMED WITHOUT PAGINATION
    # pagination is done "in_code" at the end
    if request.query_params and not only_pagination_query_params:
        query_param_keyword = list(filter(lambda k: k != "page" and k != "limit", request.query_params.keys()))[0]
        query_param_values = list(request.query_params.values())
    else:
        query_param_keyword = None
        query_param_values = None

    # but it could be that the last request have to be repeated as many times as len(query_param_values)
    # let's handle also this case later on
    in_code_pagination = queries.OptionalPagination(limit, page)

    while this_call:
        next_call_query_parameter_values = set()
        next_call_query_parameter_keyword = Entity2Request.get_id_of_entity(this_call)

        print(f"calling {this_call} with\n"
              f"\tpath param {path_param}\n"
              f"\tquery_param_keyword {query_param_keyword}\n"
              f"\tquery_param_values {query_param_values}\n")

        if query_param_values:
            # repeated queries at the last stage can bypass the limit on the cardinality of the result ==> we
            # mimic paging in python
            for qpv in query_param_values:
                single_call_result: list = await make_request(this_call, path_param, {query_param_keyword: qpv})

                if len(call_list) == 0:     # build result
                    # make distinct of result
                    try:
                        single_call_result = [frozenset(x.items()) for x in single_call_result]
                    except:
                        logger.exception("")
                    final_result.update(single_call_result)

                    # if reached pagination limit limit, stop it
                    if len(final_result) > in_code_pagination.last_idx:
                        break
                else:
                    next_call_query_parameter_values.update([x[next_call_query_parameter_keyword]
                                                             for x in single_call_result])
        else:  # only the first call can be path parameter or no-parameter
            single_call_result: list = await make_request(this_call, path_param, dict())
            path_param = None
            if len(call_list) == 0:
                # build result
                final_result.update(single_call_result)
            else:
                next_call_query_parameter_values.update([x[next_call_query_parameter_keyword]
                                                         for x in single_call_result])

        # kill intermediate requests that generate too high cardinality results or with no intermediate results
        if len(next_call_query_parameter_values) > 10000:
            raise MyExceptions.compose_request_intermediate_result_too_large(this_call)
        elif len(next_call_query_parameter_values) == 0:
            break

        # set up next call
        query_param_keyword = next_call_query_parameter_keyword
        query_param_values = sorted(next_call_query_parameter_values)   # these are just values (int or string) no need to specify a string
        try:
            this_call = call_list.pop()
        except IndexError:
            this_call = None

    # Result
    final_result = [dict(x) for x in final_result]          # revert result set to list
    if in_code_pagination.is_set and len(final_result) > in_code_pagination.skip:       # cut result with pagination (sorting and slicing)
        final_result = sorted(
            final_result,
            key=lambda x: x[next_call_query_parameter_keyword]
        )[in_code_pagination.first_idx:in_code_pagination.last_idx]
    return final_result


@app.on_event("startup")
async def startup():
    db_name, db_user, db_psw, db_port = read_connection_parameters_csv(f".{sep}postgresql_db_conn_params.csv")
    config_db_engine(db_name, db_user, db_psw, db_port)
    app.openapi = custom_openapi_doc(app)
    await init_db_model()


@app.on_event("shutdown")
async def shutdown():
    await dispose_db_engine()


@app.get("/variants")
async def get_variants(naming_id: Optional[str] = None
                       , effect_id: Optional[str] = None
                       , context_id: Optional[str] = None
                       , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)
                       ):
    """
    The term variant is commonly used for the clusters that become predominant (highly prevalent) in given locations
    at given times (described by the Variant entity).\n
    The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Variant entity.\n
    Variants are linked to their Namings, Contexts, and Effects.\n
    Different results can be obtained by exploiting the query parameters as described below.\n
    Pagination is supported and optional (with limit and page parameters).
    """
    return await queries.get_variants(naming_id, effect_id, context_id, limit, page)


@app.get("/variants/{variant_id}")
async def get_variant(variant_id: str):
    """The endpoint allows to retrieve one Variant instance, corresponding to the specified identifier."""
    return await queries.get_variant(variant_id)


@app.get("/namings")
async def get_namings(variant_id: Optional[str] = None
                      , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Each variant carries several names (naming_id)
and classes (v_class, e.g., VoI for Variant of Interest or VuM for Variant under Monitoring)
assigned by different organizations (Naming entity).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Naming entity.\n
Namings are linked to their Variants.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_namings(variant_id, limit, page)


@app.get("/namings/{naming_id}")
async def get_naming(naming_id: str):
    """The endpoint allows to retrieve one Naming instance, corresponding to the specified identifier."""
    # '''
    # [{$match: {
    #   "aliases.name": "21H"
    # }}, {$project: {
    #   aliases: 1
    # }}, {$unwind: {
    #   path: "$aliases",
    #   preserveNullAndEmptyArrays: false
    # }}, {$match: {
    #   "aliases.name": "21H"
    # }}, {$group: {
    #   _id: "$aliases"
    # }}, {$project: {
    #   _id: 0,
    #   naming_id: "$_id.name",
    #   org: "$_id.org",
    #   v_class: "$_id.v_class"
    # }}]
    # '''
    return await queries.get_naming(naming_id)


@app.get("/contexts")
async def get_contexts(variant_id: Optional[str] = None
                       , aa_positional_change_id: Optional[str] = None
                       , nuc_positional_mutation_id: Optional[str] = None
                       , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """The variant is associated to several nucleotide mutations and amino acid changes (Context entity) by different
    organizations or computational rules over data (we refer to this as the owner),
    clarified by a rule_description.\n
    The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Context entity.\n
Contexts are linked to their Variants, Aa Positional Changes, and Nuc Positional Mutations.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_contexts(variant_id, aa_positional_change_id, nuc_positional_mutation_id, limit, page)


@app.get("/contexts/{context_id}")
async def get_context(context_id: str):
    """The endpoint allows to retrieve one Context instance, corresponding to the specified identifier."""
    return await queries.get_context(context_id)


@app.get("/effects")
async def get_effects(variant_id: Optional[str] = None
                      , aa_positional_change_id: Optional[str] = None
                      , evidence_id: Optional[str] = None
                      , aa_change_group_id: Optional[str] = None
                      , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """The phenotype of SARS-CoV-2 can be strongly affected by given amino acid changes that arise on new viruses.
The Effect entity is specified by a type, referring to:\n
i) epidemiological impacts (including, e.g., viral transmission, infectivity, disease severity and fatality rate);\n
ii) immunological impacts (including, e.g., sensitivity to monoclonal antibodies and binding affinity to hosts' receptors - yielding to vaccine escape);\n
iii) protein kinetics impacts (such as protein flexibility and stability);\n
iv) treatments impact (e.g., vaccine efficacy and drug resistance).\n
The presence of the change may yield
an increase or decrease of the impact (encoded in the level attribute);
the effect is usually reported as a result of a scientific study that used a given method (clinical, experimental, computational or inferred).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Effect entity.\n
Effects are linked to their Evidences and can be linked to the corresponding Variants, individual Aa Positional Changes,or AA Change Groups.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_effects(variant_id, aa_positional_change_id, evidence_id, aa_change_group_id, limit, page)


@app.get("/effects/{effect_id}")
async def get_effect(effect_id: Optional[str] = None):
    """The endpoint allows to retrieve one Effect instance, corresponding to the specified identifier."""
    return await queries.get_effect(effect_id)


@app.get("/evidences")
async def get_evidences(effect_id: Optional[str] = None
                        , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Each effect is reported through written documents (Evidence entity), which could be
publications, preprints, or curated sources (type of evidence),
characterized by  citation, uri, and publisher (e.g., preprint servers such as bioRxiv or medRxiv, forums such as Virological, or any other academic literature editor).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Evidence entity.\n
Evidences are linked to their Effects.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_evidences(effect_id, limit, page)


@app.get("/evidences/{evidence_id}")
async def get_evidence(evidence_id: str):
    """The endpoint allows to retrieve one Evidence instance, corresponding to the specified identifier."""
    return await queries.get_evidence(evidence_id)


@app.get("/nuc_positional_mutations")
async def get_nuc_positional_mutations(context_id: Optional[str] = None
                                       , nuc_annotation_id: Optional[str] = None
                                       , nuc_mutation_id: Optional[str] = None
                                       , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Mutations occur at specific positions of the SARS-CoV-2 nucleotide sequence (Nuc positional mutation entity), causing deletions,
    insertions or - most frequently - substitutions (difference encoded by the type attribute).
They have a position, where the reference nucleotide is changed into an alternative, affecting a certain length of the sequence. For instance,
A23403G indicates that - in the 23403rd nucleotide of the sequence - a single base of Adenine  has been changed into a Guanine.\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Nuc Positional Mutation entity.\n
Nuc Positional Mutations are linked to Contexts and Nuc Annotations.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_nuc_positional_mutations(context_id, nuc_annotation_id, nuc_mutation_id, limit, page)


@app.get("/nuc_positional_mutations/{nuc_positional_mutation_id}")
async def get_nuc_positional_mutation(nuc_positional_mutation_id: str):
    """The endpoint allows to retrieve one Nuc Positional Mutation instance, corresponding to the specified identifier."""
    return await queries.get_nuc_positional_mutation(nuc_positional_mutation_id)


@app.get("/aa_positional_changes")
async def get_aa_positional_changes(context_id: Optional[str] = None
                                    , effect_id: Optional[str] = None
                                    , protein_id: Optional[str] = None
                                    , aa_change_group_id: Optional[str] = None
                                    , aa_residue_change_id: Optional[str] = None
                                    , epitope_id: Optional[str] = None
                                    , aa_change_id: Optional[str] = None
                                    # , reference: Optional[str] = None
                                    # , alternative: Optional[str] = None
                                    , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)
                                    ):
    """Non-synonymous nucleotide mutations cause amino acid changes within specific proteins (AA positional change entity, occurring in a  position where a reference residue has been changed into an alternative residue linked to a specific  protein_id for a given length);
these have a major influence on the protein functionalities. When type is a deletion, the alternative residue is encoded with a dash.
Insertions only have a position and an alternative string of arbitrary length.
Amino acid changes are denoted by strings, e.g., S:D614G denotes the substitution, at the 614 position of the Spike protein, of the amino acid Aspartic Acid (D) with the amino acid Glycine (G).  \n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Aa Positional Change entity.\n
A Positional Changes are linked to Contexts, Effects, Proteins, Aa Change Groups, Aa Residue Changes, Epitopes, and Aa Changes.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_aa_positional_changes(context_id, effect_id, protein_id, aa_change_group_id,
                                                   aa_residue_change_id, epitope_id, aa_change_id, limit, page)


@app.get("/aa_positional_changes/{aa_positional_change_id}")
async def get_aa_positional_change(aa_positional_change_id: str):
    """The endpoint allows to retrieve one Aa Positional Change instance, corresponding to the specified identifier."""
    return await queries.get_aa_positional_changes(aa_positional_change_id)


@app.get('/aa_change_groups')
async def get_aa_change_groups(aa_positional_change_id: Optional[str] = None
                               , effect_id: Optional[str] = None
                               , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """As several changes may jointly produce stronger effects, it is also important to group changes (Aa Change Groups entity).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Aa Change group entity.\n
Aa Positional Changes are linked to Effects.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_aa_change_groups(aa_positional_change_id, effect_id, limit, page)


@app.get('/aa_change_groups/{aa_change_group_id}')
async def get_aa_change_group(aa_change_group_id: str):
    """The endpoint (without parameters) allows to retrieve one Aa Change Group instance, corresponding to the specified identifier."""
    return await queries.get_aa_change_group(aa_change_group_id)


@app.get("/nuc_annotations")
async def get_nuc_annotations(protein_id: Optional[str] = None
                              , nuc_positional_mutation_id: Optional[str] = None
                              # , pos: Optional[int] = None
                              , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)
                              ):
    """The structure of SARS-CoV-2 sequences is modeled by defining a rich set of annotations, e.g., regions identified with a name with start_on_ref and stop_on_ref positions on the reference sequence (entity Nuc. annotation).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Nuc. Annotation entity.\n
Nuc. Annotations are linked to Proteins and Nuc. Positional Mutations.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_nuc_annotations(protein_id, nuc_positional_mutation_id, limit, page)


@app.get("/nuc_annotations/{nuc_annotation_id}")
async def get_nuc_annotation(nuc_annotation_id):
    """The endpoint allows to retrieve one Nuc Annotation instance, corresponding to the specified identifier."""
    return await queries.get_nuc_annotation(nuc_annotation_id)


@app.get("/proteins")
async def get_proteins(nuc_annotation_id: Optional[str] =  Query(None, description="Returns the Protein corresponding to a given Nuc Annotation")
                       , epitope_id: Optional[str] =  Query(None, description="Returns the Protein to which a given Epitope belongs")
                       , protein_region_id: Optional[str] =  Query(None, description="Returns the Protein that contains a given Protein Region")
                       , aa_positional_change_id: Optional[str] =  Query(None, description="Returns the Protein on which the specified Aa Positional Change falls")
                       , aa_change_id: Optional[str] =  Query(None, description="Returns the Protein on which the specified data Aa Change falls")
                       , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Sequences of amino acids (aa_sequences), form proteins (entity Protein); each protein maps to a specific nucleotide annotation on the basis of its starting and ending position.
Several schemes are used to denote SARS-CoV-2 protein regions; here, we adopt the scheme employed by NCBI GenBank, using both polyproteins ORF1ab and ORF1a and their nonstructural proteins NSP1-NSP16 as instances of the Protein entity, and then mapping ORF1ab and ORF1a to NSP1--NSP16 for denoting mutations (GISAID convention).
Each protein sequence has a given aa_length measured by the number of its amino acids; therefore, proteins' positions are associated with a unique number ranging from 1 to the protein's length.\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Protein entity.\n
Proteins link to Nuc. Annotations, Epitopes, Protein Regions, Aa Positional Changes, and Aa Changes.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_proteins(nuc_annotation_id, epitope_id, protein_region_id, aa_positional_change_id,
                                      aa_change_id, limit, page)


@app.get("/proteins/{protein_id}")
async def get_protein(protein_id: str):
    """The endpoint allows to retrieve one Protein instance, corresponding to the specified identifier."""
    # '''
    # [{$match: {
    #   "protein_characterization.protein_name": "ORF1A"
    # }}, {$project: {
    #   protein_characterization: {
    #     $filter: {
    #       input: "$protein_characterization",
    #       as: "prot",
    #       cond: {$eq: ["$$prot.protein_name", "ORF1A"]}
    #     }
    #   }
    # }}, {$unwind: {
    #   "path": "$protein_characterization",
    #   "preserveNullAndEmptyArrays": false
    # }}, {$group: {
    #   _id: "$protein_characterization"
    # }}, {$replaceWith: {
    #   protein_id: "$_id.protein_name",
    #   aa_length: "$_id.aa_length",
    #   aa_sequence: "$_id.aa_sequence"
    # }}]
    # '''
    return await queries.get_protein(protein_id)


@app.get("/protein_regions")
async def get_protein_regions(protein_id: Optional[str] =  Query(None, description="Returns Protein Regions that belong to the given Protein")
                              , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Proteins include regions with special properties (entity Protein regions) having a start_on_protein and a stop_on_protein position linked to a given protein_id,
as well as a describing name, a general category, and a type.\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Protein Region entity.\n
Protein Regions are connected with Proteins.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_protein_regions(protein_id, limit, page)


@app.get("/protein_regions/{protein_region_id}")
async def get_protein_region(protein_region_id: str):
    """The endpoint allows to retrieve one Protein Region instance, corresponding to the specified identifier."""
    return await queries.get_protein_region(protein_region_id)


@app.get('/aa_residue_changes')
async def get_aa_residue_changes(aa_positional_change_id: Optional[str] =  Query(None, description="Returns the AA Residue Change corresponding to a given Aa Positional Change")
                                 , aa_residue_id: Optional[str] =  Query(None, description="Returns AA Residue Changes that involve a given Aa Residue (either as reference or alternative)")
                                 , reference: Optional[str] = None
                                 , alternative: Optional[str] = None
                                 , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Although the effects of amino acid changes significantly depend on their position on proteins, some characteristics depend just on the specific change - in particular,
each substitution in Aa Positional Change is connected to the entity Aa Residue Change, which involves two residues (entity AA residue), respectively named as reference
and alternative, and is further characterized by the grantham_distance that measures the structural difference between the two residues'
molecules and determines the type of the change (i.e., radical or conservative, being 66 the threshold distance).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Aa Residue Change entity.\n
Aa Residue Changes are connected to Aa Positional Changes, and Aa Residues.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is supported and optional (with limit and page parameters)."""
    return await queries.get_aa_residue_changes(aa_positional_change_id, aa_residue_id, reference, alternative, limit,
                                                page)


@app.get('/aa_residue_changes/{aa_residue_change_id}')
async def get_aa_residue_change(aa_residue_change_id: str):
    """The endpoint allows to retrieve one Aa Residue Change instance, corresponding to the specified identifier."""
    return await queries.get_aa_residue_change(aa_residue_change_id)


@app.get('/aa_residues_ref')
@app.get('/aa_residues_alt')
@app.get('/aa_residues')
async def get_aa_residues(request: Request
                          , aa_residue_change_id: Optional[str] = None
                          , limit: Optional[int] = Query(None, ge=1), page: Optional[int] = Query(None, ge=1)):
    """Each Aa Residue holds given properties (i.e.,
molecular_weight,
isoelectric_point,
hydrophobicity,
potential_side_chain_h_bonds,
polarity,
r_group_structure,
charge,
essentiality,
side_chain_flexibility,
chemical_group_in_the_side_chain.
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Aa Residue entity.
Aa Residues are connected to Aa Residue Changes.
Two specific endpoints
/aa_residues_ref} (resp. /aa_residues_alt) can be used to return only information regarding the reference (resp. alternative) residue.
Different results can be obtained by exploiting the query parameters as described below.
Pagination is supported and optional (with limit and page parameters)."""
#    :param aa_residue_change_id: a two letter string
    return await queries.get_aa_residues(request, aa_residue_change_id, limit, page)


@app.get('/aa_residues_ref/{aa_residue_id}')
@app.get('/aa_residues_alt/{aa_residue_id}')
@app.get('/aa_residues/{aa_residue_id}')
async def get_aa_residue(aa_residue_id: str):
    """The endpoint /aa_residues (as well as its aliases /aa_residues_ref and /aa_residues_alt) allow to retrieve
    one Aa Residue instance, corresponding to the specified identifier."""
    return await queries.get_aa_residue(aa_residue_id)


@app.get('/sequences')
async def get_sequences(nuc_mutation_id: Optional[str] = None
                        , aa_change_id: Optional[str] = None
                        , host_sample_id: Optional[int] = None
                        , limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """The viral Sequence entity contains metadata about
its origin (accession_id in the source_database),
its sequencing characteristics - such as length and percentages of unknown or GC bases (n_percentage and gc_percentage).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Sequence entity.\n
Sequences are linked to their Nuc Mutations, Aa Changes, and Host Samples.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is mandatory (with limit and page parameters).
"""
    return await queries.get_sequences(nuc_mutation_id, aa_change_id, host_sample_id, limit, page)


@app.get('/sequences/{sequence_id}')
async def get_sequence(sequence_id: int):
    """The endpoint allows to retrieve one Sequence instance, corresponding to the specified identifier."""
    return await queries.get_sequence(sequence_id)


@app.get('/host_samples')
async def get_host_samples(sequence_id: Optional[int] = None
                           , limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """The Host Sample entity describes the connected biological aspects: the host organism properties, including location (in terms of continent, country, and region), collection_date, and host_species.\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Host Sample entity.\n
Host Samples are linked to the derived Sequences.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is mandatory (with limit and page parameters)."""
    return await queries.get_host_samples(sequence_id, limit, page)


@app.get('/host_samples/{host_sample_id}')
async def get_host_sample(host_sample_id):
    """The endpoint allows to retrieve one Host Sample instance, corresponding to the specified identifier."""
    return await queries.get_host_sample(host_sample_id)


@app.get('/nuc_mutations')
async def get_nuc_mutations(sequence_id: Optional[int] = None
                            , nuc_positional_mutation_id: Optional[str] = None
                            , limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """Sequences undergo variant calling pipelines; we represent their nucleotide-level mutations in the Nuc. Mutation entity.\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Nuc Mutation entity.\n
Nuc. Mutations are linked to Sequences and to Nuc Positional Mutations.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is mandatory (with limit and page parameters)."""
    return await queries.get_nuc_annotations(sequence_id, nuc_positional_mutation_id, limit, page)


@app.get('/nuc_mutations/{nuc_mutation_id}')
async def get_nuc_mutation(nuc_mutation_id: str):
    """The endpoint allows to retrieve one Nuc Mutation instance, corresponding to the specified identifier."""
    return await queries.get_nuc_mutation(nuc_mutation_id)


@app.get('/aa_changes')
async def get_aa_changes(sequence_id: Optional[int] = None
                         , protein_id: Optional[str] = None
                         , aa_positional_change_id: Optional[str] = None
                         , limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """Sequences undergo variant calling pipelines; we represent their amino acid-level changes in the AA Changes entity.\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Aa Change entity.\n
Aa Changes are linked to Sequences, Proteins, and Aa Positional Changes.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is mandatory (with limit and page parameters)."""
    return await queries.get_aa_changes(sequence_id, protein_id, aa_positional_change_id, limit, page)


@app.get('/aa_changes/{aa_change_id}')
async def get_aa_change(aa_change_id: str):
    """The endpoint allows to retrieve one Aa Change instance, corresponding to the specified identifier."""
    return await queries.get_aa_change(aa_change_id)


@app.get('/epitopes')
async def get_epitopes(assay_id: Optional[int] = None
                       , protein_id: Optional[str] = None
                       , aa_positional_change_id: Optional[str] = None
                       , limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """Epitopes are strings of amino acid residues from a pathogen's protein possibly recognized by antibodies and B/T cell receptors.
They can activate an immune response from the host and are thus employed in testing assays, treatments, and vaccines.
Amino acid changes that fall within epitope segments may compromise their stability and thus affect immune response.
Epitopes are modeled using the Epitope entity, which refers to specific epitope_start and epitope_stop positions linked to a given protein_id and are appropriate
for specific host_species (typically humans or mice, but also genetically modified organisms).\n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Epitope entity.\n
Epitopes are connected to Assays, Proteins, and Aa Positional Changes.\n
Different results can be obtained by exploiting the query parameters as described below.\n
Pagination is mandatory (with limit and page parameters)."""
    return await queries.get_epitopes(assay_id, protein_id, aa_positional_change_id, limit, page)


@app.get('/epitopes/{epitope_id}')
async def get_epitope(epitope_id: int):
    """The endpoint allows to retrieve one Epitope instance, corresponding to the specified identifier."""
    return await queries.get_epitope(epitope_id)


@app.get('/assays')
async def get_assays(epitope_id: Optional[int] = None
                     , limit: int = Query(200, ge=1), page: int = Query(1, ge=1)):
    """Epitopes are confirmed by Assays, which may give positive or negative outcomes.
Assays can be of different assay_types (i.e., B cell, T cell or MHC ligand) and mhc_classes}; for T cell assays an hla_restriction is defined, restricting the population on which the epitope would be effective. \n
The endpoint (without parameters) allows to retrieve the full list of distinct instances of the Assay entity.   n
Assays are linked to Epitopes.  n
Different results can be obtained by exploiting the query parameters as described below.    n
Pagination is mandatory (with limit and page parameters)."""
    return await queries.get_assays(epitope_id, limit, page)


@app.get('/assays/{assay_id}')
async def get_assay(assay_id: int):
    """The endpoint allows to retrieve one Assay instance, corresponding to the specified identifier."""
    return await queries.get_assay(assay_id)


if __name__ == '__main__':
    uvicorn.run("main_beanie:app", reload=True, debug=True, reload_delay=1.0)


# PER AGGIUNGERE UN MIDDLEWARE
# @app.middleware("http")
# async def log_request(request, call_next):
#     print(f'{request.method} {request.url} {app.root_path}')
#     response = await call_next(request)
#     print(f'Status code: {response.status_code}')
#     async for line in response.body_iterator:
#         print(f'    {line}')
#     response = await my_other_awesome_function()
#     return response
#
#
# async def my_other_awesome_function():
#     json_compatible_item_data = jsonable_encoder("heyyy, ce l'abbiamo fatta?")
#     return JSONResponse(content=json_compatible_item_data)


class Entity2Request:

    _endpoint_of_entity = {
        'variants': 'get_variants',
        'namings': 'get_namings',
        'contexts': 'get_contexts',
        'effects': 'get_effects',
        'evidences': 'get_evidences',
        'nuc_positional_mutations': 'get_nuc_positional_mutations',
        'aa_positional_changes': 'get_aa_positional_changes',
        'nuc_annotations': 'get_nuc_annotations',
        'proteins': 'get_proteins',
        'protein_regions': 'get_protein_regions',
        'aa_residue_changes': 'get_aa_residue_changes',
        'aa_residues': 'get_aa_residues',
        'aa_residues_ref': 'get_aa_residues',
        'aa_residues_alt': 'get_aa_residues',
        'sequences': 'get_sequences',
        'host_samples': 'get_host_samples',
        'nuc_mutations': 'get_nuc_mutations',
        'aa_changes': 'get_aa_changes',
        'epitopes': 'get_epitopes',
        'assays': 'get_assays',
    }
    
    _ID_of_entity = {
        'variants': 'variant_id',
        'namings': 'naming_id',
        'contexts': 'context_id',
        'effects': 'effect_id',
        'evidences': 'evidence_id',
        'nuc_positional_mutations': 'nuc_positional_mutation_id',
        'aa_positional_changes': 'aa_positional_change_id',
        'nuc_annotations': 'nuc_annotation_id',
        'proteins': 'protein_id',
        'protein_regions': 'protein_region_id',
        'aa_residue_changes': 'aa_residue_change_id',
        'aa_residues': 'aa_residue_id',
        'aa_residues_ref': 'aa_residue_id',
        'aa_residues_alt': 'aa_residue_id',
        'sequences': 'sequence_id',
        'host_samples': 'host_sample_id',
        'nuc_mutations': 'nuc_mutation_id',
        'aa_changes': 'aa_change_id',
        'epitopes': 'epitope_id',
        'assays': 'assay_id',
    }

    # @classmethod
    # def function_name_for_entity(cls, entity_name: str, path_params, query_params, header_params):
    #     function_name = cls._endpoint_of_entity[entity_name]     # default
    #     if path_params:
    #         function_name = function_name[:-1]
    #     return eval(function_name)

    class FakeRequest:
        class FakeURL:
            def __init__(self, fake_path):
                self.path = fake_path

        def __init__(self, fake_path):
            self.url = self.FakeURL(fake_path)

    @classmethod
    def make_function_call(cls, entity_name: str, path_params, query_params: dict):
        function_name = "queries." + cls._endpoint_of_entity[entity_name]  # default
        if path_params:
            function_name = function_name[:-1]

        if function_name == 'get_aa_residues':      # endpoint /aa_residues with query parameters
            custom_request = cls.FakeRequest(entity_name)
            return eval(function_name)(custom_request, **query_params)
        elif function_name == 'get_aa_residue':     # endpoint /aa_residues with path parameter
            custom_request = cls.FakeRequest(entity_name)
            return eval(function_name)(custom_request, path_params)

        elif path_params:
            return eval(function_name)(path_params)
        else:
            return eval(function_name)(**query_params)

    @classmethod
    def get_id_of_entity(cls, entity_name: str) -> str:
        return cls._ID_of_entity[entity_name]

