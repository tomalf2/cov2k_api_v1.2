import base64
import re
import warnings
from enum import Enum
from typing import Optional, List, Callable

import bson.errors
import uvicorn
from fastapi import FastAPI, Request, status, HTTPException, Depends
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

from dal.data_sqlalchemy.model import _session_factory

app = FastAPI()


async def mandatory_pagination(limit: int = 200, page: int = 0) -> dict:
    return {
        "stmt": f"limit {limit} offset {page*limit}",
        "limit": limit,
        "page": page
    }


class OptionalPagination:
    def __init__(self, limit, page):
        if limit is not None and page is not None:
            self.skip = limit*page
            self.limit = limit
            self.first_idx = self.skip
            self.last_idx = self.skip + self.limit
            self.is_set = True
        elif limit is not None or page is not None:
            raise MyExceptions.incomplete_optional_pagination_params
        else:
            self.is_set = False

    def __bool__(self):
        return self.is_set


async def optional_pagination(limit: Optional[int] = None, page: Optional[int] = None):
    return OptionalPagination(limit, page)


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
async def combine(full_path: str, request: Request, pagination: dict = Depends(mandatory_pagination)):
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

    async def make_request(entity_name, path_param, query_params, this_req_pagination_stmt):
        try:
            return await Entity2Request.make_function_call(entity_name, path_param, query_params
                                                           , this_req_pagination_stmt)
        except TypeError as e:
            logger.exception("")
            if 'unexpected keyword argument' in e.args[0]:
                raise MyExceptions.compose_request_unrecognised_query_parameter
            else:
                log_and_raise_http_bad_request()
        except:
            log_and_raise_http_bad_request()

    this_call = call_list.pop()
    final_result = set()
    if request.query_params and not only_pagination_query_params:
        query_param_keyword = list(request.query_params.keys())[0]
        query_param_values = list(request.query_params.values())
    else:
        query_param_keyword = None
        query_param_values = None

    this_call_pagination = {"stmt": "", "limit": pagination["limit"], "page": pagination["page"]}
    # but it could be that the last request have to be repeated as many times as len(query_param_values)
    # let's handle also this case later on
    result_slice_start_idx: int = pagination["page"] * pagination["limit"]
    result_slice_stop_idx: int = result_slice_start_idx + pagination["limit"]

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
                single_call_result: list = await make_request(this_call, path_param, {query_param_keyword: qpv},
                                                              this_call_pagination)
                if len(call_list) == 0:
                    # build result
                    final_result.update(single_call_result)
                    # mimic pagination when necessary
                    if len(final_result) > result_slice_stop_idx:
                        print(f"final_result set is {len(final_result)} long. It is being sorted and sliced.")
                        final_result = sorted(
                            final_result,
                            key=lambda x: x[next_call_query_parameter_keyword]
                        )[result_slice_start_idx:result_slice_stop_idx]
                        break
                else:
                    next_call_query_parameter_values.update([x[next_call_query_parameter_keyword]
                                                             for x in single_call_result])
        else:  # only the first call can be path parameter or no-parameter
            single_call_result: list = await make_request(this_call, path_param, dict(), this_call_pagination)
            path_param = None
            if len(call_list) == 0:
                # build result
                final_result.update(single_call_result)
            else:
                next_call_query_parameter_values.update([x[next_call_query_parameter_keyword]
                                                         for x in single_call_result])

        # kill intermediate requests that generate too high cardinality results
        if len(next_call_query_parameter_values) > 10000:
            raise MyExceptions.compose_request_intermediate_result_too_large(this_call)

        if len(call_list) == 0:
            print(f"\tresult_slice_start_idx {result_slice_start_idx}\n"
                  f"\tresult_slice_stop_idx {result_slice_stop_idx}\n"
                  f"\tresults are sorted and paginated on ID {next_call_query_parameter_keyword}")
        else:
            print(f"\tquery param values for next call are sorted on {next_call_query_parameter_keyword}")

        # set up next call
        query_param_keyword = next_call_query_parameter_keyword
        query_param_values = sorted(next_call_query_parameter_values)   # these are just values (int or string) no need to specify a string
        try:
            this_call = call_list.pop()
        except IndexError:
            this_call = None
    # HERE final_result became a list
    return final_result


# @app.get("/combine/{full_path:path}")
# async def combine(full_path: str, request: Request, pagination: dict = Depends(mandatory_pagination)):
#     # clean full_path
#     while len(full_path) > 0 and full_path[-1] == '/':
#         full_path = full_path[:-1]
#     if len(full_path) == 0:
#         raise MyExceptions.compose_request_no_entity_specified
#
#     # check that first entity is valid (others are checked later)
#     call_list = full_path.split('/')
#     call_list = [x for x in call_list if x]
#     if call_list[0] not in all_available_entities:
#         raise MyExceptions.compose_request_unrecognised_command
#
#     # remove page and limit from query params
#
#
#     # find query type and detect unrecognised entities
#     query_type = None
#     path_param = None
#     only_pagination_query_params = True if set(request.query_params.keys()).issubset(['limit', 'page']) else False
#     if not request.query_params or only_pagination_query_params:
#         # check for unrecognised entities (last one can be path parameter)
#         if not set(call_list[:-1]).issubset(all_available_entities):
#             raise MyExceptions.compose_request_unrecognised_command
#         if call_list[-1] in all_available_entities:
#             query_type = QueryTypes.NO_PARAM
#         else:
#             path_param = call_list[-1]
#             call_list = call_list[:-1]
#             query_type = QueryTypes.PATH_PARM
#     else:
#         if not set(call_list).issubset(all_available_entities):
#             raise MyExceptions.compose_request_unrecognised_command
#         query_type = QueryTypes.QUERY_PARAM
#
#     # check for entity cycles
#     if len(call_list) > len(set(call_list)):
#         raise MyExceptions.compose_request_path_cycle_detected
#
#     # description = {
#     #     "cleaned path": full_path,
#     #     "entities requested": split_entities,
#     #     "query_type": query_type.name,
#     #     "query params": request.query_params,
#     #     "path param": path_param,
#     #     "header params": request.headers
#     # }
#
#     async def make_request(entity_name, path_param, query_params, this_req_pagination_stmt):
#         try:
#             return await Entity2Request.make_function_call(entity_name, path_param, query_params
#                                                            , this_req_pagination_stmt)
#         except TypeError as e:
#             logger.exception("")
#             if 'unexpected keyword argument' in e.args[0]:
#                 raise MyExceptions.compose_request_unrecognised_query_parameter
#             else:
#                 log_and_raise_http_bad_request()
#         except:
#             log_and_raise_http_bad_request()
#
#
#     # call_list = queue(split_entities)
#     # this_call = call_list.pop()
#     # final_result = None
#     # query_keyword = keyword_of_query_params()
#     # query_values = [value_of_query_params()]
#     #
#     # while(this_call):
#     #   next_call_query_values = []
#     #
#     #   if query_values:
#     #       for(query_value in query_values):
#     #           # single_call_result = this_call(query_keyword, query_value)
#     #           # if next_call:
#     #               # next_call_query_values.append(<ID_resulting_in_this_call_parsed_result>)
#     #           # else:
#     #               # append single_call_result to final_result
#     #   elif path_param:
#     #       single_call_result = this_call(path_param)
#     #           # if next_call:
#     #               # next_call_query_values.append(<ID_resulting_in_this_call_parsed_result>)
#     #           # else:
#     #               # append single_call_result to final_result
#     #   else:
#     #       single_call_result = this_call()
#     #           # if next_call:
#     #               # next_call_query_values.append(<ID_resulting_in_this_call_parsed_result>)
#     #           # else:
#     #               # append single_call_result to final_result
#     #
#     #   # set up next call
#     #   if next_call:
#     #       query_keyword = ID_of_entity(this_call)
#     #       query_values = next_call_query_values
#     #       this_call = call_list.pop()
#
#     this_call = call_list.pop()
#     final_result = []
#     if request.query_params and not only_pagination_query_params:
#         query_param_keyword = list(request.query_params.keys())[0]
#         query_param_values = list(request.query_params.values())
#     else:
#         query_param_keyword = None
#         query_param_values = None
#
#     this_call_pagination = {"stmt": "", "limit": pagination["limit"], "page": pagination["page"]}
#     # but it could be that the last request have to be repeated as many times as len(query_param_values)
#     # let's handle also this case later on
#     result_slice_start_idx: int = pagination["page"] * pagination["limit"]
#     result_slice_stop_idx: int = result_slice_start_idx + pagination["limit"]
#
#     while this_call:
#         next_call_query_parameter_values = []
#         next_call_query_parameter_values_set = set()
#         next_call_query_parameter_keyword = Entity2Request.get_id_of_entity(this_call)
#
#         print(f"calling {this_call} with\n"
#               f"\tpath param {path_param}\n"
#               f"\tquery_param_keyword {query_param_keyword}\n"
#               f"\tquery_param_values {query_param_values}\n")
#
#         if query_param_values:
#             # repeated queries at the last stage can bypass the limit on the cardinality of the result ==> we
#             # mimic paging in python
#             for qpv in query_param_values:
#                 single_call_result: list = await make_request(this_call, path_param, {query_param_keyword: qpv},
#                                                               this_call_pagination)
#                 if len(call_list) == 0:
#                     # build result
#                     final_result += single_call_result
#                     # mimic pagination when necessary
#                     if len(final_result) > result_slice_stop_idx:
#                         final_result = final_result[result_slice_start_idx:result_slice_stop_idx]
#                         break
#                 else:
#                     a = set()
#                     a += set()
#
#                     next_call_query_parameter_values += [x[next_call_query_parameter_keyword] for x in single_call_result]
#         else:   # only the first call can be path parameter or no-parameter
#             single_call_result: list = await make_request(this_call, path_param, dict(), this_call_pagination)
#             path_param = None
#             if len(call_list) == 0:
#                 # build result
#                 final_result += single_call_result
#             else:
#                 next_call_query_parameter_values += [x[next_call_query_parameter_keyword] for x in single_call_result]
#
#         # kill intermediate requests that generate too high cardinality results
#         if len(next_call_query_parameter_values) > 10000:
#             raise MyExceptions.compose_request_intermediate_result_too_large(this_call)
#
#         if len(call_list) == 0:
#             print(f"\tresult_slice_start_idx {result_slice_start_idx}\n"
#                   f"\tresult_slice_stop_idx {result_slice_stop_idx}")
#
#         # set up next call
#         query_param_keyword = next_call_query_parameter_keyword
#         query_param_values = next_call_query_parameter_values
#         try:
#             this_call = call_list.pop()
#         except IndexError:
#             this_call = None
#     return final_result


@app.on_event("startup")
async def startup():
    db_name, db_user, db_psw, db_port = read_connection_parameters_csv(f".{sep}postgresql_db_conn_params.csv")
    config_db_engine(db_name, db_user, db_psw, db_port)
    await init_db_model()


@app.on_event("shutdown")
async def shutdown():
    await dispose_db_engine()


@app.get("/variants")
async def get_variants(naming_id: Optional[str] = None
                       , effect_id: Optional[str] = None
                       , context_id: Optional[str] = None
                       , pagination: OptionalPagination = Depends(optional_pagination)
                       ):
    query = dict()
    if naming_id:
        query.update({"aliases.name": naming_id})
    if effect_id:
        query.update({"effects": {"$elemMatch": {"$eq": PydanticObjectId(effect_id)}}})
    if context_id:
        variant_id, owner = context_id.split("_", maxsplit=1)
        query.update({
            '$and': [
                {
                    '_id': variant_id
                }, {
                    '$or': [
                        {
                            'org_2_aa_changes.org': owner
                        }, {
                            'org_2_nuc_changes.org': owner
                        }
                    ]
                }]
        })
    result = Variant.find(query, projection_model=VariantsProjection)
    if pagination:
        result.sort("_id").skip(pagination.skip).limit(pagination.limit)
    result = await result.to_list()
    return result


@app.get("/variants/{variant_id}")
async def get_variant(variant_id: str):
    return await Variant.find_many({"_id": variant_id}, projection_model=VariantsProjection).to_list()


@app.get("/namings")
async def get_namings(variant_id: Optional[str] = None
                      , pagination: OptionalPagination = Depends(optional_pagination)):
    pipeline = []
    '''
    [{$match: {
      _id: "B.1.621"
    }}, {$project: {
      aliases: 1
    }}, {$unwind: {
      path: "$aliases",
      preserveNullAndEmptyArrays: false
    }}, {$project: {
      _id: 0,
      naming_id: "$aliases.name",
      org: "$aliases.org",
      v_class: "$aliases.v_class"
    }}]
    '''
    if variant_id:
        pipeline.append({
            '$match': {
                '_id': variant_id
            }
        })
    pipeline += [
        {
            '$project': {
                'aliases': 1
            }
        }, {
            '$unwind': {
                'path': '$aliases',
                'preserveNullAndEmptyArrays': False
            }
        }, {
            '$project': {
                '_id': 0,
                'naming_id': '$aliases.name',
                'org': '$aliases.org',
                'v_class': '$aliases.v_class'
            }
        }]
    result = await Variant.aggregate(pipeline).to_list()
    if pagination:
        result = sorted(result, key=lambda x: x["naming_id"])[pagination.first_idx:pagination.last_idx]
    return result


@app.get("/namings/{naming_id}")
async def get_naming(naming_id: str):
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
    return await Variant.aggregate([
        {
            '$match': {
                'aliases.name': naming_id
            }
        }, {
            '$project': {
                'aliases': 1
            }
        }, {
            '$unwind': {
                'path': '$aliases',
                'preserveNullAndEmptyArrays': False
            }
        }, {
            '$match': {
                'aliases.name': naming_id
            }
        }, {
            '$group': {
                '_id': '$aliases'
            }
        }, {
            '$project': {
                '_id': 0,
                'naming_id': '$_id.name',
                'org': '$_id.org',
                'v_class': '$_id.v_class'
            }
        }]).to_list()


@app.get("/contexts")
async def get_contexts(variant_id: Optional[str] = None
                       , aa_positional_change_id: Optional[str] = None
                       , nuc_positional_mutation_id: Optional[str] = None
                       , pagination: OptionalPagination = Depends(optional_pagination)):
    query_composer = FilterIntersection()
    if variant_id:
        #   PIPELINE FOR QUERYING VARIANT ID
        # [{$match: {
        #   _id: "B.1.621"
        # }}, {$project: {
        #   characterization: {$concatArrays: ["$org_2_aa_changes", "$org_2_nuc_changes"]}
        # }}, {$project: {
        #   org: "$characterization.org"
        # }}, {$unwind: {
        #   path: "$org",
        #   preserveNullAndEmptyArrays: false
        # }}, {$project: {
        #   "context_id": {$concat: [{$toString: "$_id"}, "_" , "$org"]},
        #   "owner": "$org"
        # }}, {$group: {
        #   _id: {
        #     context_id: "$context_id",
        #     owner: "$owner"
        #   }
        # }}, {$lookup: {
        #   from: 'rule',
        #   localField: '_id.owner',
        #   foreignField: 'owner',
        #   as: 'joined'
        # }}, {$unwind: {
        #   path: "$joined",
        #   preserveNullAndEmptyArrays: false
        # }}, {$project: {
        #   context_id: "$_id.context_id",
        #   owner: "$_id.owner",
        #   rule_description: "$joined.rule",
        #   _id: 0
        # }}]
        pipeline_4_variant_id = [
            {
                '$match': {
                    '_id': variant_id
                }
            }, {
                '$project': {
                    'characterization': {
                        '$concatArrays': [
                            '$org_2_aa_changes', '$org_2_nuc_changes'
                        ]
                    }
                }
            }, {
                '$project': {
                    'org': '$characterization.org'
                }
            }, {
                '$unwind': {
                    'path': '$org',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'context_id': {
                        '$concat': [
                            {
                                '$toString': '$_id'
                            }, '_', '$org'
                        ]
                    },
                    'owner': '$org'
                }
            }, {
                '$group': {
                    '_id': {
                        'context_id': '$context_id',
                        'owner': '$owner'
                    }
                }
            }, {
                '$lookup': {
                    'from': 'rule',
                    'localField': '_id.owner',
                    'foreignField': 'owner',
                    'as': 'joined'
                }
            }, {
                '$unwind': {
                    'path': '$joined',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'context_id': '$_id.context_id',
                    'owner': '$_id.owner',
                    'rule_description': '$joined.rule',
                    '_id': 0
                }
            }]
        result = await Variant.aggregate(pipeline_4_variant_id).to_list()
        query_composer.add_filter(variant_id, result)
    if aa_positional_change_id:
        #       PIPELINE FOR QUERYING BY NUC OR AA CHANGE ID
        # [{$match: {
        #   "org_2_aa_changes.changes": {"$elemMatch": {"$eq": "NSP5:K90R"}}
        # }}, {$project: {
        #   org_2_aa_changes: 1
        # }}, {$unwind: {
        #   path: "$org_2_aa_changes",
        #   preserveNullAndEmptyArrays: false
        # }}, {$match: {
        #   "org_2_aa_changes.changes": {"$elemMatch": {"$eq": "NSP5:K90R"}}
        # }}, {$project: {
        #   org: "$org_2_aa_changes.org"
        # }}, {$project: {
        #   "context_id": {$concat: [{$toString: "$_id"}, "_" , "$org"]},
        #   "owner": "$org"
        # }}, {$group: {
        #   _id: {
        #     context_id: "$context_id",
        #     owner: "$owner"
        #   }
        # }}, {$lookup: {
        #   from: 'rule',
        #   localField: '_id.owner',
        #   foreignField: 'owner',
        #   as: 'joined'
        # }}, {$unwind: {
        #   path: "$joined",
        #   preserveNullAndEmptyArrays: false
        # }}, {$project: {
        #   context_id: "$_id.context_id",
        #   owner: "$_id.owner",
        #   rule_description: "$joined.rule",
        #   _id: 0
        # }}]
        pipeline_4_aa_change = [
            {
                '$match': {
                    'org_2_aa_changes.changes': {
                        '$elemMatch': {
                            '$eq': aa_positional_change_id
                        }
                    }
                }
            }, {
                '$project': {
                    'org_2_aa_changes': 1
                }
            }, {
                '$unwind': {
                    'path': '$org_2_aa_changes',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$match': {
                    'org_2_aa_changes.changes': {
                        '$elemMatch': {
                            '$eq': aa_positional_change_id
                        }
                    }
                }
            }, {
                '$project': {
                    'org': '$org_2_aa_changes.org'
                }
            }, {
                '$project': {
                    'context_id': {
                        '$concat': [
                            {
                                '$toString': '$_id'
                            }, '_', '$org'
                        ]
                    },
                    'owner': '$org'
                }
            }, {
                '$group': {
                    '_id': {
                        'context_id': '$context_id',
                        'owner': '$owner'
                    }
                }
            }, {
                '$lookup': {
                    'from': 'rule',
                    'localField': '_id.owner',
                    'foreignField': 'owner',
                    'as': 'joined'
                }
            }, {
                '$unwind': {
                    'path': '$joined',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'context_id': '$_id.context_id',
                    'owner': '$_id.owner',
                    'rule_description': '$joined.rule',
                    '_id': 0
                }
            }]
        result = await Variant.aggregate(pipeline_4_aa_change).to_list()
        query_composer.add_filter(aa_positional_change_id, result)
    if nuc_positional_mutation_id:
        '''
              PIPELINE FOR QUERYING BY NUC OR AA CHANGE ID
        [{$match: {
          "org_2_nuc_changes.changes": {"$elemMatch": {"$eq": "G174T"}}
        }}, {$project: {
          org_2_nuc_changes: 1
        }}, {$unwind: {
          path: "$org_2_nuc_changes",
          preserveNullAndEmptyArrays: false
        }}, {$match: {
          "org_2_nuc_changes.changes": {"$elemMatch": {"$eq": "G174T"}}
        }}, {$project: {
          org: "$org_2_nuc_changes.org"
        }}, {$unwind: {
          path: "$org",
          preserveNullAndEmptyArrays: false
        }}, {$project: {
          "context_id": {$concat: [{$toString: "$_id"}, "_" , "$org"]},
          "owner": "$org"
        }}, {$group: {
          _id: {
            context_id: "$context_id",
            owner: "$owner"
          }
        }}, {$lookup: {
          from: 'rule',
          localField: '_id.owner',
          foreignField: 'owner',
          as: 'joined'
        }}, {$unwind: {
          path: "$joined",
          preserveNullAndEmptyArrays: false
        }}, {$project: {
          context_id: "$_id.context_id",
          owner: "$_id.owner",
          rule_description: "$joined.rule",
          _id: 0
        }}]
        '''
        pipeline_4_nuc_change_id = [
            {
                '$match': {
                    'org_2_nuc_changes.changes': {
                        '$elemMatch': {
                            '$eq': nuc_positional_mutation_id
                        }
                    }
                }
            }, {
                '$project': {
                    'org_2_nuc_changes': 1
                }
            }, {
                '$unwind': {
                    'path': '$org_2_nuc_changes',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$match': {
                    'org_2_nuc_changes.changes': {
                        '$elemMatch': {
                            '$eq': nuc_positional_mutation_id
                        }
                    }
                }
            }, {
                '$project': {
                    'org': '$org_2_nuc_changes.org'
                }
            }, {
                '$unwind': {
                    'path': '$org',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'context_id': {
                        '$concat': [
                            {
                                '$toString': '$_id'
                            }, '_', '$org'
                        ]
                    },
                    'owner': '$org'
                }
            }, {
                '$group': {
                    '_id': {
                        'context_id': '$context_id',
                        'owner': '$owner'
                    }
                }
            }, {
                '$lookup': {
                    'from': 'rule',
                    'localField': '_id.owner',
                    'foreignField': 'owner',
                    'as': 'joined'
                }
            }, {
                '$unwind': {
                    'path': '$joined',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'context_id': '$_id.context_id',
                    'owner': '$_id.owner',
                    'rule_description': '$joined.rule',
                    '_id': 0
                }
            }]
        result = await Variant.aggregate(pipeline_4_nuc_change_id).to_list()
        query_composer.add_filter(nuc_positional_mutation_id, result)


    query_composer.intersect_results(lambda x: x["context_id"])
    if query_composer.result() != query_composer.NO_FILTERS:
        result = query_composer.result()
    else:
        '''
        [{$project: {
          characterization: {
            $concatArrays: ["$org_2_aa_changes", "$org_2_nuc_changes"]
          }
        }}, {$project: {
          org: "$characterization.org"
        }}, {$unwind: {
          path: "$org",
          preserveNullAndEmptyArrays: false
        }}, {$group: {
          _id: {
            _id: "$_id",
            org: "$org"
          }
        }}, {$project: {
          "context_id": {
            $concat: [{
              $toString: "$_id._id"
            }, "_", "$_id.org"]
          },
          "owner": "$_id.org",
          "_id": 0
        }}, {$lookup: {
          from: 'rule',
          localField: 'owner',
          foreignField: 'owner',
          as: 'joined'
        }}, {$unwind: {
          path: "$joined",
          preserveNullAndEmptyArrays: false
        }}, {$project: {
          context_id: "$context_id",
          owner: "$owner",
          rule_description: "$joined.rule",
          _id: 0
        }}]
        '''
        pipeline_no_filters = [
            {
                '$project': {
                    'characterization': {
                        '$concatArrays': [
                            '$org_2_aa_changes', '$org_2_nuc_changes'
                        ]
                    }
                }
            }, {
                '$project': {
                    'org': '$characterization.org'
                }
            }, {
                '$unwind': {
                    'path': '$org',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$group': {
                    '_id': {
                        '_id': '$_id',
                        'org': '$org'
                    }
                }
            }, {
                '$project': {
                    'context_id': {
                        '$concat': [
                            {
                                '$toString': '$_id._id'
                            }, '_', '$_id.org'
                        ]
                    },
                    'owner': '$_id.org',
                    '_id': 0
                }
            }, {
                '$lookup': {
                    'from': 'rule',
                    'localField': 'owner',
                    'foreignField': 'owner',
                    'as': 'joined'
                }
            }, {
                '$unwind': {
                    'path': '$joined',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'context_id': '$context_id',
                    'owner': '$owner',
                    'rule_description': '$joined.rule',
                    '_id': 0
                }
            }
        ]
        result = await Variant.aggregate(pipeline_no_filters).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["context_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/contexts/{context_id}")
async def get_context(context_id: str):
    variant_id, owner = context_id.split("_", maxsplit=1)
    context_exists = await Variant.find({
        '_id': variant_id,
        '$or': [
            {
                'org_2_aa_changes.org': owner
            }, {
                'org_2_nuc_changes.org': owner
            }
        ]
    }).to_list()
    if context_exists:
        rules = await Rule.find({"owner": owner}, projection_model=RuleProjection).to_list()
        rules = [{"context_id": context_id, "owner": x.owner, "rule": x.rule} for x in rules]
        return rules
    else:
        return []


@app.get("/effects")
async def get_effects(variant_id: Optional[str] = None
                      , aa_positional_change_id: Optional[str] = None
                      , evidence_id: Optional[str] = None
                      , aa_change_group_id: Optional[str] = None
                      , pagination: OptionalPagination = Depends(optional_pagination)):
    effects_of_aa_change = None
    if aa_positional_change_id:
        effects_of_aa_change = await Effect.aggregate(
            [
                {
                    '$match': {
                        'aa_changes': {
                            '$elemMatch': {
                                '$eq': aa_positional_change_id
                            }
                        }
                    }
                }, {
                    '$project': {
                        'aa_changes': 0
                    }
                }], projection_model=EffectProjection).to_list()
    effects_of_var = None
    if variant_id:
        effects_of_var = await Variant.aggregate(
            [{
                '$match': {
                    '_id': variant_id
                }
            }, {
                '$lookup': {
                    'from': Effect.Collection.name,
                    'localField': 'effects',
                    'foreignField': '_id',
                    'as': 'joinedEffects'
                }
            }, {
                '$replaceWith': {
                    'newRoot': '$joinedEffects'
                }
            }, {
                '$unwind': {
                    'path': '$newRoot',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$replaceWith': {
                    '_id': '$newRoot._id',
                    'type': '$newRoot.type',
                    'lv': '$newRoot.lv',
                    'method': '$newRoot.method'
                }
            }], projection_model=EffectProjection).to_list()
    effects_of_source = None
    if evidence_id:
        effects_of_source = await EffectSource.aggregate(
            [{
                '$match': {
                    '_id': PydanticObjectId(evidence_id)
                }
            }, {
                '$project': {
                    'effect_ids': 1,
                    '_id': 0
                }
            }, {
                '$unwind': {
                    'path': '$effect_ids'
                }
            }, {
                '$lookup': {
                    'from': Effect.Collection.name,
                    'localField': 'effect_ids',
                    'foreignField': '_id',
                    'as': 'effect'
                }
            }, {
                '$replaceRoot': {
                    'newRoot': {
                        '$first': '$effect'
                    }
                }
            }], projection_model=EffectProjection).to_list()
    effects_of_aa_group = None
    if aa_change_group_id:
        # {
        #   _id: ObjectId('61708df43578fd55aa616923'),
        #   "aa_changes.1": {$exists: true}
        # }
        effects_of_aa_group = await Effect.find(
            {
                '_id': PydanticObjectId(aa_change_group_id),
                'aa_changes.1': {'$exists': True}
            }
            , projection_model=EffectProjection).to_list()

    filter_intersection = FilterIntersection()\
        .add_filter(aa_positional_change_id, effects_of_aa_change)\
        .add_filter(variant_id, effects_of_var)\
        .add_filter(evidence_id, effects_of_source)\
        .add_filter(aa_change_group_id, effects_of_aa_group)\
        .intersect_results(lambda an_effect: an_effect.effect_id)
    if filter_intersection.result() != FilterIntersection.NO_FILTERS:
        result = filter_intersection.result()
    else:
        result = await Effect.find_all(projection_model=EffectProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["effect_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/effects/{effect_id}")
async def get_effect(effect_id: Optional[str] = None):
    try:
        return await Effect.find({"_id": PydanticObjectId(effect_id)}, projection_model=EffectProjection).to_list()
    except bson.errors.InvalidId:
        return None


@app.get("/evidences")
async def get_evidences(effect_id: Optional[str] = None
                        , pagination: OptionalPagination = Depends(optional_pagination)):
    if effect_id:
        result = await EffectSource.find({'effect_ids': {'$elemMatch': {'$eq': PydanticObjectId(effect_id)}}}
                                       , projection_model=EvidenceProjection).to_list()
    else:
        result = await EffectSource.find_all(projection_model=EvidenceProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["evidence_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/evidences/{evidence_id}")
async def get_evidence(evidence_id: str):
    return await EffectSource.find({"_id": PydanticObjectId(evidence_id)}, projection_model=EvidenceProjection).to_list()


@app.get("/nuc_positional_mutations")
async def get_nuc_positional_mutations(context_id: Optional[str] = None, nuc_annotation_id: Optional[str] = None
                                       , nuc_mutation_id: Optional[str] = None
                                       , pagination: OptionalPagination = Depends(optional_pagination)):
    query_composer = FilterIntersection()
    mutations_of_context = None
    if context_id:
        variant_id, owner = context_id.split("_", maxsplit=1)
        '''
        [{$match: {
          _id: "B.1.351",
          "org_2_nuc_changes.org": "phe"
        }}, {$project: {
          org_2_nuc_changes: 1
        }}, {$unwind: {
          path: "$org_2_nuc_changes",
          preserveNullAndEmptyArrays: false
        }}, {$match: {
          "org_2_nuc_changes.org": "phe"
        }}, {$project: {
          change: "$org_2_nuc_changes.changes"
        }}, {$unwind: {
          path: "$change",
          preserveNullAndEmptyArrays: false
        }}, {$lookup: {
          from: 'nuc_change',
          localField: 'change',
          foreignField: 'change_id',
          as: 'joined'
        }}, {$project: {
          nuc_positional_mutation_id: {$first: "$joined.change_id"},
          reference: {$first: "$joined.ref"},
          position: {$first: "$joined.pos"},
          alternative: {$first: "$joined.alt"},
          type: {$first: "$joined.type"},
          length: {$first: "$joined.length"},
          _id: 0
        }}]
        '''
        mutations_of_context = await Variant.aggregate([
            {
                '$match': {
                    '_id': variant_id,
                    'org_2_nuc_changes.org': owner
                }
            }, {
                '$project': {
                    'org_2_nuc_changes': 1
                }
            }, {
                '$unwind': {
                    'path': '$org_2_nuc_changes',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$match': {
                    'org_2_nuc_changes.org': owner
                }
            }, {
                '$project': {
                    'change': '$org_2_nuc_changes.changes'
                }
            }, {
                '$unwind': {
                    'path': '$change',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$lookup': {
                    'from': 'nuc_change',
                    'localField': 'change',
                    'foreignField': 'change_id',
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'nuc_positional_mutation_id': {
                        '$first': '$joined.change_id'
                    },
                    'reference': {
                        '$first': '$joined.ref'
                    },
                    'position': {
                        '$first': '$joined.pos'
                    },
                    'alternative': {
                        '$first': '$joined.alt'
                    },
                    'type': {
                        '$first': '$joined.type'
                    },
                    'length': {
                        '$first': '$joined.length'
                    },
                    '_id': 0
                }
            }]
        ).to_list()

    mutations_in_annotation = None
    if nuc_annotation_id:
        # [{$match: {
        #   _id: ObjectId('617bca3a896e9264bab572cf')
        # }}, {$lookup: {
        #   from: 'nuc_change',
        #   let: { start_on_ref: "$start_on_ref", stop_on_ref: "$stop_on_ref"},
        #   pipeline: [
        #       {
        #         $match: {
        #           $expr: {
        #             $and: [
        #               {$gte: ["$pos", "$$start_on_ref"]},
        #               {$lte: ["$pos", "$$stop_on_ref"]}
        #             ]
        #           }
        #         }
        #       }
        #     ],
        #   as: "joined"
        # }}, {$project: {
        #   joined: "$joined"
        # }}, {$unwind: {
        #   path: "$joined",
        #   preserveNullAndEmptyArrays: false
        # }}, {$project: {
        #   nuc_positional_mutation_id: "$joined.change_id",
        #   reference: "$joined.ref",
        #   position: "$joined.pos",
        #   alternative: "$joined.alt",
        #   type: "$joined.type",
        #   length: "$joined.length",
        #   _id: 0
        # }}]
        mutations_in_annotation = await Structure.aggregate([
            {
                '$match': {
                    '_id': PydanticObjectId(nuc_annotation_id)
                }
            }, {
                '$lookup': {
                    'from': 'nuc_change',
                    'let': {
                        'start_on_ref': '$start_on_ref',
                        'stop_on_ref': '$stop_on_ref'
                    },
                    'pipeline': [
                        {
                            '$match': {
                                '$expr': {
                                    '$and': [
                                        {
                                            '$gte': [
                                                '$pos', '$$start_on_ref'
                                            ]
                                        }, {
                                            '$lte': [
                                                '$pos', '$$stop_on_ref'
                                            ]
                                        }
                                    ]
                                }
                            }
                        }
                    ],
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'joined': '$joined'
                }
            }, {
                '$unwind': {
                    'path': '$joined',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'nuc_positional_mutation_id': '$joined.change_id',
                    'reference': '$joined.ref',
                    'position': '$joined.pos',
                    'alternative': '$joined.alt',
                    'type': '$joined.type',
                    'length': '$joined.length',
                    '_id': 0
                }
            }]
        ).to_list()

    mutation_matching_nuc_mutation_id = None
    if nuc_mutation_id:
        kb_nuc_mutation_id = vcm_nuc_mut_2_kb_nuc_mut(nuc_mutation_id)
        mutation_matching_nuc_mutation_id = await get_nuc_positional_mutation(kb_nuc_mutation_id)

    query_composer\
        .add_filter(context_id, mutations_of_context)\
        .add_filter(nuc_annotation_id, mutations_in_annotation)\
        .add_filter(nuc_mutation_id, mutation_matching_nuc_mutation_id)\
        .intersect_results(lambda x: x["nuc_positional_mutation_id"])

    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        result = await NUCChange.find_all(projection_model=NUCPositionalMutationProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["nuc_positional_mutation_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/nuc_positional_mutations/{nuc_positional_mutation_id}")
async def get_nuc_positional_mutation(nuc_positional_mutation_id: str):
    return await NUCChange.find({"change_id": nuc_positional_mutation_id}
                                , projection_model=NUCPositionalMutationProjection).to_list()


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
                                    , pagination: OptionalPagination = Depends(optional_pagination)
                                    ):
    query_composer = FilterIntersection()
    if context_id:
        variant_id, owner = context_id.split("_", maxsplit=1)
        '''
        [{$match: {
          _id: "B.1.351",
          "org_2_aa_changes.org": "phe"
        }}, {$project: {
          org_2_aa_changes: 1
        }}, {$unwind: {
          path: "$org_2_aa_changes",
          preserveNullAndEmptyArrays: false
        }}, {$match: {
          "org_2_aa_changes.org": "phe"
        }}, {$project: {
          change: "$org_2_aa_changes.changes"
        }}, {$unwind: {
          path: "$change",
          preserveNullAndEmptyArrays: false
        }}, {$lookup: {
          from: 'aa_change',
          localField: 'change',
          foreignField: 'change_id',
          as: 'joined'
        }}, {$project: {
          aa_positional_change_id: {
            $first: "$joined.change_id"
          },
          protein_id: {
            $first: "$joined.protein"
          },
          reference: {
            $first: "$joined.ref"
          },
          position: {
            $first: "$joined.pos"
          },
          alternative: {
            $first: "$joined.alt"
          },
          type: {
            $first: "$joined.type"
          },
          length: {
            $first: "$joined.length"
          },
          _id: 0
        }}]
        '''
        aa_changes_of_context = await Variant.aggregate([
            {
                '$match': {
                    '_id': variant_id,
                    'org_2_aa_changes.org': owner
                }
            }, {
                '$project': {
                    'org_2_aa_changes': 1
                }
            }, {
                '$unwind': {
                    'path': '$org_2_aa_changes',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$match': {
                    'org_2_aa_changes.org': owner
                }
            }, {
                '$project': {
                    'change': '$org_2_aa_changes.changes'
                }
            }, {
                '$unwind': {
                    'path': '$change',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$lookup': {
                    'from': 'aa_change',
                    'localField': 'change',
                    'foreignField': 'change_id',
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'aa_positional_change_id': {
                        '$first': '$joined.change_id'
                    },
                    'protein_id': {
                        '$first': '$joined.protein'
                    },
                    'reference': {
                        '$first': '$joined.ref'
                    },
                    'position': {
                        '$first': '$joined.pos'
                    },
                    'alternative': {
                        '$first': '$joined.alt'
                    },
                    'type': {
                        '$first': '$joined.type'
                    },
                    'length': {
                        '$first': '$joined.length'
                    },
                    '_id': 0
                }
            }]
        ).to_list()
        query_composer.add_filter(context_id, aa_changes_of_context)
    if effect_id:
        '''
        [{$match: {
          _id: ObjectId('61708df43578fd55aa616923')
        }}, {$project: {
          aa_changes: 1
        }}, {$unwind: {
          path: "$aa_changes",
          preserveNullAndEmptyArrays: false
        }}, {$lookup: {
          from: 'aa_change',
          localField: 'aa_changes',
          foreignField: 'change_id',
          as: 'joined'
        }}, {$project: {
          aa_positional_change_id: {$first: "$joined.change_id"},
          protein_id: {$first: "$joined.protein"},
          reference: {$first: "$joined.ref"},
          position: {$first: "$joined.pos"},
          alternative: {$first: "$joined.alt"},
          type: {$first: "$joined.type"},
          length: {$first: "$joined.length"},
          _id: 0
        }}]
        '''
        changes_of_effect = await Effect.aggregate([
            {
                '$match': {
                    '_id': PydanticObjectId('61708df43578fd55aa616923')
                }
            }, {
                '$project': {
                    'aa_changes': 1
                }
            }, {
                '$unwind': {
                    'path': '$aa_changes',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$lookup': {
                    'from': 'aa_change',
                    'localField': 'aa_changes',
                    'foreignField': 'change_id',
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'aa_positional_change_id': {
                        '$first': '$joined.change_id'
                    },
                    'protein_id': {
                        '$first': '$joined.protein'
                    },
                    'reference': {
                        '$first': '$joined.ref'
                    },
                    'position': {
                        '$first': '$joined.pos'
                    },
                    'alternative': {
                        '$first': '$joined.alt'
                    },
                    'type': {
                        '$first': '$joined.type'
                    },
                    'length': {
                        '$first': '$joined.length'
                    },
                    '_id': 0
                }
            }]).to_list()
        query_composer.add_filter(effect_id, changes_of_effect)
    if protein_id:
        changes_in_protein = await AAChange\
            .find({"protein": protein_id}, projection_model=AAPositionalChangeProjection)\
            .to_list()
        query_composer.add_filter(protein_id, changes_in_protein)
    if aa_change_group_id:
        '''
        [{$match: {
          _id: ObjectId('61708df43578fd55aa616923'),
          "aa_changes.1": {$exists: true}
        }}, {$project: {
          aa_changes: 1
        }}, {$unwind: {
          path: '$aa_changes',
          preserveNullAndEmptyArrays: false
        }}, {$lookup: {
          from: 'aa_change',
          localField: 'aa_changes',
          foreignField: 'change_id',
          as: 'joined'
        }}, {$project: {
          aa_positional_change_id: {$first: "$joined.change_id"},
          protein_id: {$first: "$joined.protein"},
          reference: {$first: "$joined.ref"},
          position: {$first: "$joined.pos"},
          alternative: {$first: "$joined.alt"},
          type: {$first: "$joined.type"},
          length: {$first: "$joined.length"},
          _id: 0
        }}]
        '''
        changes_of_group = await Effect.aggregate([
            {
                '$match': {
                    '_id': PydanticObjectId(aa_change_group_id),
                    'aa_changes.1': {'$exists': True}
                }
            }, {
                '$project': {
                    'aa_changes': 1
                }
            }, {
                '$unwind': {
                    'path': '$aa_changes',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$lookup': {
                    'from': 'aa_change',
                    'localField': 'aa_changes',
                    'foreignField': 'change_id',
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'aa_positional_change_id': {
                        '$first': '$joined.change_id'
                    },
                    'protein_id': {
                        '$first': '$joined.protein'
                    },
                    'reference': {
                        '$first': '$joined.ref'
                    },
                    'position': {
                        '$first': '$joined.pos'
                    },
                    'alternative': {
                        '$first': '$joined.alt'
                    },
                    'type': {
                        '$first': '$joined.type'
                    },
                    'length': {
                        '$first': '$joined.length'
                    },
                    '_id': 0
                }
            }]
        ).to_list()
        query_composer.add_filter(aa_change_group_id, changes_of_group)
    if aa_residue_change_id:
        if len(aa_residue_change_id) != 2:
            raise MyExceptions.unrecognised_aa_residue_change_id
        aa_changes_matching_residue_change = await AAChange.find(
            {"ref": aa_residue_change_id[0], "alt": aa_residue_change_id[1]}
            , projection_model=AAPositionalChangeProjection
        ).to_list()
        query_composer.add_filter(aa_residue_change_id, aa_changes_matching_residue_change)
    if epitope_id:
        async with get_session() as session:
            vcm_protein = await session.execute(
                f"select protein_name from epitope natural join epitope_fragment "
                f"where epi_fragment_id = {epitope_id} and virus_id = 1 limit 1;")
            try:
                vcm_protein = vcm_protein.fetchall()[0]["protein_name"]
            except IndexError:  # no proteins found (the epitope id is wrong)
                return []
        try:
            protein = vcm_syntax_2_short_protein_name[vcm_protein]
        except KeyError:
            return []
        else:
            aa_changes_over_epitope = await AAChange.find(
                {"protein": protein}
                , projection_model=AAPositionalChangeProjection).to_list()
            query_composer.add_filter(epitope_id, aa_changes_over_epitope)
    if aa_change_id:
        query_composer.add_filter(aa_change_id, await get_aa_positional_change(aa_change_id))

    # if reference:
    #     changes_with_ref = await AAChange\
    #         .find({"ref": reference}, projection_model=AAPositionalChangeProjection).to_list()
    #     query_composer.add_filter(reference, changes_with_ref)
    # if alternative:
    #     change_with_alt = await AAChange\
    #         .find({"alt": alternative}, projection_model=AAPositionalChangeProjection).to_list()
    #     query_composer.add_filter(alternative, change_with_alt)

    # intersect results up to here
    query_composer.intersect_results(lambda x: x["aa_positional_change_id"])
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        result = await AAChange.find_all(projection_model=AAPositionalChangeProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["aa_positional_change_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/aa_positional_changes/{aa_positional_change_id}")
async def get_aa_positional_change(aa_positional_change_id: str):
    return await AAChange.find({"change_id": aa_positional_change_id}
                               , projection_model=AAPositionalChangeProjection).to_list()


@app.get('/aa_change_groups')
async def get_aa_change_groups(aa_positional_change_id: Optional[str] = None
                               , effect_id: Optional[str] = None
                               , pagination: OptionalPagination = Depends(optional_pagination)):
    query_composer = FilterIntersection()
    if aa_positional_change_id:
        groups_of_positional_change = await Effect.find({
            "aa_changes.1": {"$exists": True}
             , "aa_changes": {"$elemMatch": {"$eq": aa_positional_change_id}}
        }, projection_model=AAChangeGroupProjection).to_list()
        query_composer.add_filter(aa_positional_change_id, groups_of_positional_change)
    if effect_id:
        groups_of_effect_id = await Effect.find({
            "_id": PydanticObjectId(effect_id),
            "aa_changes.1": {"$exists": True}
        }, projection_model=AAChangeGroupProjection).to_list()
        query_composer.add_filter(effect_id, groups_of_effect_id)

    query_composer.intersect_results(lambda x: x.aa_change_group_id)
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        result = await Effect.find(
            {"aa_changes.1": {"$exists": True}}
            , projection_model=AAChangeGroupProjection
        ).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["aa_change_group_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get('/aa_change_groups/{aa_change_group_id}')
async def get_aa_change_group(aa_change_group_id: str):
    return await Effect.find({
        "_id": PydanticObjectId(aa_change_group_id),
        "aa_changes.1": {"$exists": True}
    } , projection_model=AAChangeGroupProjection).to_list()


@app.get("/nuc_annotations")
async def get_nuc_annotations(protein_id: Optional[str] = None
                              , nuc_positional_mutation_id: Optional[str] = None
                              # , pos: Optional[int] = None
                              , pagination: OptionalPagination = Depends(optional_pagination)
                              ):
    query_composer = FilterIntersection()
    if protein_id:
        genes_of_protein = await Structure.find({"protein_characterization.protein_name": protein_id},
                                                projection_model=NucAnnotationProjection).to_list()
        query_composer.add_filter(protein_id, genes_of_protein)
    if nuc_positional_mutation_id:
        # [{$match: {
        #   change_id: "G13617A"
        # }}, {$lookup: {
        #   from: 'structure',
        #   let: {pos: "$pos"},
        #   pipeline: [
        #     {
        #       $match: {
        #         $expr: {
        #           $and: [
        #             {$gte: ["$$pos", "$start_on_ref"]},
        #             {$lte: ["$$pos", "$stop_on_ref"]}
        #           ]
        #         }
        #       }
        #     }
        #   ],
        #   as: "joined"
        # }}, {$project: {
        #   joined: 1
        # }}, {$unwind: {
        #   path: "$joined",
        #   preserveNullAndEmptyArrays: false
        # }}, {$project: {
        #   _id: 0,
        #   nuc_annotation_id: "$joined._id",
        #   name: "$joined.annotation_id",
        #   start_on_ref: "$joined.start_on_ref",
        #   stop_on_ref: "$joined.stop_on_ref"
        # }}]
        annotations_of_positional_mutation = await NUCChange.aggregate([
            {
                '$match': {
                    'change_id': nuc_positional_mutation_id
                }
            }, {
                '$lookup': {
                    'from': 'structure',
                    'let': {
                        'pos': '$pos'
                    },
                    'pipeline': [
                        {
                            '$match': {
                                '$expr': {
                                    '$and': [
                                        {
                                            '$gte': [
                                                '$$pos', '$start_on_ref'
                                            ]
                                        }, {
                                            '$lte': [
                                                '$$pos', '$stop_on_ref'
                                            ]
                                        }
                                    ]
                                }
                            }
                        }
                    ],
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'joined': 1
                }
            }, {
                '$unwind': {
                    'path': '$joined',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    '_id': 0,
                    'nuc_annotation_id': {'$toString': '$joined._id'},
                    'name': '$joined.annotation_id',
                    'start_on_ref': '$joined.start_on_ref',
                    'stop_on_ref': '$joined.stop_on_ref'
                }
            }]
        ).to_list()
        query_composer.add_filter(nuc_positional_mutation_id, annotations_of_positional_mutation)
    # if pos:
    #     genes_at_pos = await Structure.find({"start_on_ref": {"$lte": pos}, "stop_on_ref": {"$gte": pos}},
    #                                         projection_model=GeneProjection).to_list()
    #     query_composer.add_filter(pos, genes_at_pos)

    query_composer.intersect_results(lambda x: x["nuc_annotation_id"])
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        result = await Structure.find_all(projection_model=NucAnnotationProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["nuc_annotation_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/nuc_annotations/{nuc_annotation_id}")
async def get_nuc_annotation(nuc_annotation_id):
    return await Structure.find({"_id": PydanticObjectId(nuc_annotation_id)}
                                , projection_model=NucAnnotationProjection).to_list()


@app.get("/proteins")
async def get_proteins(nuc_annotation_id: Optional[str] = None
                       , epitope_id: Optional[str] = None
                       , protein_region_id: Optional[str] = None
                       , aa_positional_change_id: Optional[str] = None
                       , aa_change_id: Optional[str] = None
                       , pagination: OptionalPagination = Depends(optional_pagination)):
    query_composer = FilterIntersection()
    if nuc_annotation_id:
        '''
        [{$match: {
          '_id': ObjectId('617bca3a896e9264bab572c9')
        }}, {$project: {
          protein_characterization: 1
        }}, {$unwind: {
          "path": "$protein_characterization",
          "preserveNullAndEmptyArrays": false
        }}, {$replaceWith: {
          protein_id: "$protein_characterization.protein_name",
          aa_length: "$protein_characterization.aa_length",
          aa_sequence: "$protein_characterization.aa_sequence"
        }}]
        '''
        proteins_of_nuc_annotation = await Structure.aggregate([
            {
                '$match': {
                    '_id': PydanticObjectId(nuc_annotation_id)
                }
            }, {
                '$project': {
                    'protein_characterization': 1
                }
            }, {
                '$unwind': {
                    'path': '$protein_characterization',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$replaceWith': {
                    'protein_id': '$protein_characterization.protein_name',
                    'aa_length': '$protein_characterization.aa_length',
                    'aa_sequence': '$protein_characterization.aa_sequence'
                }
            }]
        ).to_list()
        query_composer.add_filter(nuc_annotation_id, proteins_of_nuc_annotation)
    if epitope_id:
        async with get_session() as session:
            vcm_protein = await session.execute(
                f"select protein_name from epitope natural join epitope_fragment "
                f"where epi_fragment_id = {epitope_id} and virus_id = 1 limit 1;")
            try:
                vcm_protein = vcm_protein.fetchall()[0]["protein_name"]
            except IndexError:  # no proteins found (the epitope id is wrong)
                return []
        try:
            protein = vcm_syntax_2_short_protein_name[vcm_protein]
        except KeyError:
            return []
        else:
            '''
        [{$match: {
          "protein_characterization.protein_name": "NSP12"
        }}, {$project: {
          protein_characterization: {
            $filter: {
              input: "$protein_characterization",
              as: "prot",
              cond: {$eq: ["$$prot.protein_name", "NSP12"]}
            }
          }
        }
        }, {$unwind: {
          "path": "$protein_characterization",
          "preserveNullAndEmptyArrays": false
        }}, {$replaceWith: {
          protein_id: "$protein_characterization.protein_name",
          aa_length: "$protein_characterization.aa_length",
          aa_sequence: "$protein_characterization.aa_sequence"
        }}]
        '''
            proteins_of_epitope = await Structure.aggregate([
                {
                    '$match': {
                        'protein_characterization.protein_name': protein
                    }
                }, {
                    '$project': {
                        'protein_characterization': {
                            '$filter': {
                                'input': '$protein_characterization',
                                'as': 'prot',
                                'cond': {
                                    '$eq': [
                                        '$$prot.protein_name', protein
                                    ]
                                }
                            }
                        }
                    }
                }, {
                    '$unwind': {
                        'path': '$protein_characterization',
                        'preserveNullAndEmptyArrays': False
                    }
                }, {
                    '$replaceWith': {
                        'protein_id': '$protein_characterization.protein_name',
                        'aa_length': '$protein_characterization.aa_length',
                        'aa_sequence': '$protein_characterization.aa_sequence'
                    }
                }]).to_list()
            query_composer.add_filter(epitope_id, proteins_of_epitope)
    if protein_region_id:
        '''
        [{$match: {
          _id: ObjectId('617bfe15ff5aa31a8daf8a70')
        }}, {$project: {
          protein_name: 1
        }}, {$lookup: {
          from: 'structure',
          localField: 'protein_name',
          foreignField: 'protein_characterization.protein_name',
          as: 'joined'
        }}, {$project: {
          "protein_characterization": {$concatArrays: "$joined.protein_characterization"}
        }}, {$unwind: {
          path: '$protein_characterization',
          preserveNullAndEmptyArrays: false
        }}, {$unwind: {
          path: "$protein_characterization",
          preserveNullAndEmptyArrays: false
        }}, {$project: {
          protein_id: "$protein_characterization.protein_name",
          aa_length: "$protein_characterization.aa_length",
          aa_sequence: "$protein_characterization.aa_sequence",
          _id: 0   
        }}]
        '''
        proteins_of_subregion = await ProteinRegion.aggregate([

            {
                '$match': {
                    '_id': PydanticObjectId(protein_region_id)
                }
            }, {
                '$project': {
                    'protein_name': 1
                }
            }, {
                '$lookup': {
                    'from': 'structure',
                    'localField': 'protein_name',
                    'foreignField': 'protein_characterization.protein_name',
                    'as': 'joined'
                }
            }, {
                '$project': {
                    'protein_characterization': {
                        '$concatArrays': '$joined.protein_characterization'
                    }
                }
            }, {
                '$unwind': {
                    'path': '$protein_characterization',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$unwind': {
                    'path': '$protein_characterization',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'protein_id': '$protein_characterization.protein_name',
                    'aa_length': '$protein_characterization.aa_length',
                    'aa_sequence': '$protein_characterization.aa_sequence',
                    '_id': 0
                }
            }]
        ).to_list()
        query_composer.add_filter(protein_region_id, proteins_of_subregion)
    if aa_positional_change_id or aa_change_id:
        aa_positional_change_id = aa_positional_change_id if aa_positional_change_id else aa_change_id
        try:
            protein_name, _ = aa_positional_change_id.split(":", maxsplit=1)
            if not protein_name:
                raise ValueError
        except:
            query_composer.add_filter(aa_positional_change_id, [])
        else:
            '''
            [{$match: {
              "protein_characterization.protein_name": "NSP12"
            }}, {$project: {
              proteins: {
                $filter: {
                  input: "$protein_characterization",
                  as: "prot",
                  cond: {$eq: ["$$prot.protein_name", "NSP12"]}
                }
              }
            }}, {$unwind: {
              path: "$proteins",
              preserveNullAndEmptyArrays: false
            }}, {$project: {
              protein_id: "$proteins.protein_name",
              aa_length: "$proteins.aa_length",
              aa_sequence: "$proteins.aa_sequence",
              _id: 0
            }}]        
            '''
            protein_of_aa_change = await Structure.aggregate([
                {
                    '$match': {
                        'protein_characterization.protein_name': protein_name
                    }
                }, {
                    '$project': {
                        'proteins': {
                            '$filter': {
                                'input': '$protein_characterization',
                                'as': 'prot',
                                'cond': {
                                    '$eq': [
                                        '$$prot.protein_name', protein_name
                                    ]
                                }
                            }
                        }
                    }
                }, {
                    '$unwind': {
                        'path': '$proteins',
                        'preserveNullAndEmptyArrays': False
                    }
                }, {
                    '$project': {
                        'protein_id': '$proteins.protein_name',
                        'aa_length': '$proteins.aa_length',
                        'aa_sequence': '$proteins.aa_sequence',
                        '_id': 0
                    }
                }]
            ).to_list()
            query_composer.add_filter(aa_positional_change_id, protein_of_aa_change)

    query_composer.intersect_results(lambda x: x["protein_id"])
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        # [{$project: {
        #   protein_characterization: 1
        # }}, {$unwind: {
        #   "path": "$protein_characterization",
        #   "preserveNullAndEmptyArrays": false
        # }}, {$replaceWith: {
        #   protein_id: "$protein_characterization.protein_name",
        #   aa_length: "$protein_characterization.aa_length",
        #   aa_sequence: "$protein_characterization.aa_sequence"
        # }}]
        result = await Structure.aggregate([
            {
                '$project': {
                    'protein_characterization': 1
                }
            }, {
                '$unwind': {
                    'path': '$protein_characterization',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$replaceWith': {
                    'protein_id': '$protein_characterization.protein_name',
                    'aa_length': '$protein_characterization.aa_length',
                    'aa_sequence': '$protein_characterization.aa_sequence'
                }
            }]
        ).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["protein_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/proteins/{protein_id}")
async def get_protein(protein_id: str):
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
    return await Structure.aggregate([
        {
            '$match': {
                'protein_characterization.protein_name': protein_id
            }
        }, {
            '$project': {
                'protein_characterization': {
                    '$filter': {
                        'input': '$protein_characterization',
                        'as': 'prot',
                        'cond': {
                            '$eq': [
                                '$$prot.protein_name', protein_id
                            ]
                        }
                    }
                }
            }
        }, {
            '$unwind': {
                'path': '$protein_characterization',
                'preserveNullAndEmptyArrays': False
            }
        }, {
            '$group': {
                '_id': '$protein_characterization'
            }
        }, {
            '$replaceWith': {
                'protein_id': '$_id.protein_name',
                'aa_length': '$_id.aa_length',
                'aa_sequence': '$_id.aa_sequence'
            }
        }]).to_list()


@app.get("/protein_regions")
async def get_protein_regions(protein_id: Optional[str] = None
                              , pagination: OptionalPagination = Depends(optional_pagination)):
    query_composer = FilterIntersection()
    if protein_id:
        regions_in_protein = await ProteinRegion.find({
            "protein_name": protein_id
        }, projection_model=ProteinRegionProjection).to_list()
        query_composer.add_filter(protein_id, regions_in_protein)

    query_composer.intersect_results(lambda x: x.protein_region_id)
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        result = await ProteinRegion.find_all(projection_model=ProteinRegionProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["protein_region_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get("/protein_regions/{protein_region_id}")
async def get_protein_region(protein_region_id: str):
    return await ProteinRegion.find({"_id": PydanticObjectId(protein_region_id)}
                                    , projection_model=ProteinRegionProjection).to_list()


@app.get('/aa_residue_changes')
async def get_aa_residue_changes(aa_positional_change_id: Optional[str] = None
                                 , aa_residue_id: Optional[str] = None
                                 , reference: Optional[str] = None
                                 , alternative: Optional[str] = None
                                 , pagination: OptionalPagination = Depends(optional_pagination)):
    query_composer = FilterIntersection()
    if aa_positional_change_id and reference and alternative\
            or aa_positional_change_id and (reference or alternative):
        return MyExceptions.illegal_parameters_combination
    elif aa_positional_change_id or (reference and alternative):
        if aa_positional_change_id:
            ref_alt_aa_pos_change_regex = re.fullmatch(r'[a-zA-Z]+:([a-zA-Z\-\*]*)[\d/]+([a-zA-Z\-\*]+)'
                                                       , aa_positional_change_id)
            if not ref_alt_aa_pos_change_regex:
                raise MyExceptions.unrecognized_aa_positional_change_id
            else:
                ref, alt = ref_alt_aa_pos_change_regex.groups()
        else:
            ref, alt = reference, alternative
        '''
        [{$match: {
          residue: "A"
        }}, {$project: {
          residue: 1,
          grantham_distance: {$objectToArray: "$grantham_distance"}
        }}, {$unwind: {
          path: "$grantham_distance",
          preserveNullAndEmptyArrays: false
        }}, {$match: {
          "grantham_distance.k": "H"
        }}, {$project: {
          aa_residue_change_id: {$concat: ["$residue", "$grantham_distance.k"]},
          reference: "$residue",
          alternative: "$grantham_distance.k",
          grantham_distance: {$toInt: "$grantham_distance.v"},
          _id: 0
        }}, {$addFields: {
          type: {
            $cond: [
              {$gte: ["$grantham_distance", 66]}, 
              "radical", 
              "conservative"
            ]
          }
        }}]
        '''
        residue_changes_of_aa_change = await AAResidue.aggregate([
            {
                '$match': {
                    'residue': ref
                }
            }, {
                '$project': {
                    'residue': 1,
                    'grantham_distance': {
                        '$objectToArray': '$grantham_distance'
                    }
                }
            }, {
                '$unwind': {
                    'path': '$grantham_distance',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$match': {
                    'grantham_distance.k': alt
                }
            }, {
                '$project': {
                    'aa_residue_change_id': {
                        '$concat': ['$residue', '$grantham_distance.k']
                    },
                    'reference': '$residue',
                    'alternative': '$grantham_distance.k',
                    'grantham_distance': {
                        '$toInt': '$grantham_distance.v'
                    },
                    '_id': 0
                }
            }, {
                '$addFields': {
                    'type': {
                        '$cond': [
                            {
                                '$gte': [
                                    '$grantham_distance', 66
                                ]
                            }, 'radical', 'conservative'
                        ]
                    }
                }
            }
        ]).to_list()
        query_composer.add_filter(aa_positional_change_id, residue_changes_of_aa_change)
    elif reference or alternative or aa_residue_id:
        '''
        [{$match: {
          residue: "A"
        }}, {$project: {
          residue: 1,
          grantham_distance: {$objectToArray: "$grantham_distance"}
        }}, {$unwind: {
          path: "$grantham_distance",
          preserveNullAndEmptyArrays: false
        }}, {$project: {
          aa_residue_change_id: {$concat: ["$residue", "$grantham_distance.k"]},
          reference: "$residue",
          alternative: "$grantham_distance.k",
          grantham_distance: {$toInt: "$grantham_distance.v"},
          _id: 0
        }}, {$addFields: {
          type: {
            $cond: [
              {$gte: ["$grantham_distance", 66]}, 
              "radical", 
              "conservative"
            ]
          }
        }}]
        '''
        if reference:
            a_residue = reference
        elif alternative:
            a_residue = alternative
        else:
            a_residue = aa_residue_id
        pipeline = [
            {
                '$match': {
                    'residue': a_residue
                }
            }, {
                '$project': {
                    'residue': 1,
                    'grantham_distance': {
                        '$objectToArray': '$grantham_distance'
                    }
                }
            }, {
                '$unwind': {
                    'path': '$grantham_distance',
                    'preserveNullAndEmptyArrays': False
                }
            }]
        if reference or aa_residue_id:
            pipeline.append(
                {
                    '$project': {
                        'aa_residue_change_id': {
                            '$concat': [
                                '$residue', '$grantham_distance.k'
                            ]
                        },
                        'reference': '$residue',
                        'alternative': '$grantham_distance.k',
                        'grantham_distance': {
                            '$toInt': '$grantham_distance.v'
                        },
                        '_id': 0
                    }
                })
        else:
            pipeline.append(
                {
                    '$project': {
                        'aa_residue_change_id': {
                            '$concat': [
                                '$grantham_distance.k', '$residue'
                            ]
                        },
                        'reference': '$grantham_distance.k',
                        'alternative': '$residue',
                        'grantham_distance': {
                            '$toInt': '$grantham_distance.v'
                        },
                        '_id': 0
                    }
                })
        pipeline.append(
            {
                '$addFields': {
                    'type': {
                        '$cond': [
                            {
                                '$gte': [
                                    '$grantham_distance', 66
                                ]
                            }, 'radical', 'conservative'
                        ]
                    }
                }
            })
        residue_change_with_a_single_residue = await AAResidue.aggregate(pipeline).to_list()
        query_composer.add_filter(a_residue, residue_change_with_a_single_residue)

    query_composer.intersect_results(lambda x: x["aa_residue_change_id"])
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        '''
        [{$project: {
          residue: 1,
          grantham_distance: {$objectToArray: "$grantham_distance"}
        }}, {$unwind: {
          path: "$grantham_distance",
          preserveNullAndEmptyArrays: false
        }}, {$project: {
          aa_residue_change_id: {$concat: ["$residue", "$grantham_distance.k"]},
          reference: "$residue",
          alternative: "$grantham_distance.k",
          grantham_distance: {$toInt: "$grantham_distance.v"},
          _id: 0
        }}, {$addFields: {
          type: {
            $cond: [
              {$gte: ["$grantham_distance", 66]}, 
              "radical", 
              "conservative"
            ]
          }
        }}]
        '''
        result = await AAResidue.aggregate([
            {
                '$project': {
                    'residue': 1,
                    'grantham_distance': {
                        '$objectToArray': '$grantham_distance'
                    }
                }
            }, {
                '$unwind': {
                    'path': '$grantham_distance',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$project': {
                    'aa_residue_change_id': {
                        '$concat': [
                            '$residue', '$grantham_distance.k'
                        ]
                    },
                    'reference': '$residue',
                    'alternative': '$grantham_distance.k',
                    'grantham_distance': {
                        '$toInt': '$grantham_distance.v'
                    },
                    '_id': 0
                }
            }, {
                '$addFields': {
                    'type': {
                        '$cond': [
                            {
                                '$gte': [
                                    '$grantham_distance', 66
                                ]
                            }, 'radical', 'conservative'
                        ]
                    }
                }
            }
        ]).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["aa_residue_change_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get('/aa_residue_changes/{aa_residue_change_id}')
async def get_aa_residue_change(aa_residue_change_id: str):
    if len(aa_residue_change_id) != 2:
        raise MyExceptions.unrecognised_aa_residue_change_id
    '''
        [{$match: {
          residue: "A"
        }}, {$project: {
          aa_residue_change_id: "AD",
          reference: "$residue",
          alternative: "D",
          grantham_distance: "$grantham_distance.D",
          _id: 0
        }}, {$addFields: {
          type: {
            $cond: [{
              $gte: ["$grantham_distance", 66]
            }, "radical", "conservative"]
          }
        }}]
        '''
    return await AAResidue.aggregate([
        {
            '$match': {
                'residue': aa_residue_change_id[0]
            }
        }, {
            '$project': {
                'aa_residue_change_id': aa_residue_change_id,
                'reference': '$residue',
                'alternative': aa_residue_change_id[1],
                'grantham_distance': f'$grantham_distance.{aa_residue_change_id[1]}',
                '_id': 0
            }
        }, {
            '$addFields': {
                'type': {
                    '$cond': [
                        {
                            '$gte': [
                                '$grantham_distance', 66
                            ]
                        }, 'radical', 'conservative'
                    ]
                }
            }
        }]).to_list()


@app.get('/aa_residues_ref')
@app.get('/aa_residues_alt')
@app.get('/aa_residues')
async def get_aa_residues(request: Request, aa_residue_change_id: Optional[str] = None
                          , pagination: OptionalPagination = Depends(optional_pagination)):
    """
    :param aa_residue_change_id: a two letter string
    """
    query_composer = FilterIntersection()
    if aa_residue_change_id:
        if len(aa_residue_change_id) != 2:
            raise MyExceptions.unrecognised_aa_residue_change_id
        # form query based on the request: aa_residues or aa_residues_alt or aa_residues_ref
        url_called = request.url.path
        if url_called.endswith("ref"):
            query = {'residue': aa_residue_change_id[0]}
        elif url_called.endswith("alt"):
            query = {'residue': aa_residue_change_id[1]}
        else:
            query = {'$or': [{'residue': aa_residue_change_id[0]}, {'residue': aa_residue_change_id[1]}]}
        # do the query
        residues_of_residue_change_id = await AAResidue.find(query, projection_model=AAResidueProjection).to_list()
        query_composer.add_filter(aa_residue_change_id, residues_of_residue_change_id)

    query_composer.intersect_results(lambda x: x.aa_residue_id)
    if query_composer.result() != FilterIntersection.NO_FILTERS:
        result = query_composer.result()
    else:
        result = await AAResidue.find_all(projection_model=AAResidueProjection).to_list()
    if pagination:
        return sorted(result, key=lambda x: x["aa_residue_id"])[pagination.first_idx:pagination.last_idx]
    else:
        return result


@app.get('/aa_residues_ref/{aa_residue_id}')
@app.get('/aa_residues_alt/{aa_residue_id}')
@app.get('/aa_residues/{aa_residue_id}')
async def get_aa_residue(aa_residue_id: str):
    return await AAResidue.find({"residue": aa_residue_id}, projection_model=AAResidueProjection).to_list()


@app.get('/sequences')
async def get_sequences(nuc_mutation_id: Optional[str] = None
                        , aa_change_id: Optional[str] = None
                        , host_sample_id: Optional[int] = None
                        , pagination: dict = Depends(mandatory_pagination)):
    final_pagination_stmt = f'order by sequence_id {pagination["stmt"]}'
    async with get_session() as session:
        query_composer = FilterIntersection()

        select_query = "select sequence_id, accession_id, database_source, length, n_percentage, gc_percentage "
        if nuc_mutation_id:
            nuc_mutation_id = nuc_mutation_id.lower()
            nuc_change_re_match = re.fullmatch(r'([a-zA-Z\-\*]*)([\d/]+)([a-zA-Z\-\*]+)', nuc_mutation_id)
            if not nuc_change_re_match:
                raise MyExceptions.unrecognised_nuc_mutation_id
            else:
                ref, pos, alt = nuc_change_re_match.groups()
            query = f"{select_query} from sequence natural join sequencing_project natural join nucleotide_variant nv " \
                    f"where nv.sequence_original = '{ref}' " \
                    f"and nv.start_original = {pos} " \
                    f"and nv.sequence_alternative = '{alt}' " \
                    f"and virus_id = 1 " \
                    f"{final_pagination_stmt};"
            sequences_with_nuc_change = await session.execute(query)
            sequences_with_nuc_change = sequences_with_nuc_change.fetchall()
            query_composer.add_filter(nuc_mutation_id, sequences_with_nuc_change)
        if aa_change_id:
            prot, ref, pos, alt = aa_change_id_2_vcm_aa_change(aa_change_id)
            query = f"{select_query} from sequence natural join sequencing_project natural join annotation a " \
                    f"natural join aminoacid_variant av " \
                    f"where a.product = '{prot}' " \
                    f"and av.sequence_aa_original = '{ref}' " \
                    f"and av.start_aa_original = {pos} " \
                    f"and av.sequence_aa_alternative = '{alt}' " \
                    f"and virus_id = 1" \
                    f"{final_pagination_stmt};"
            sequences_with_aa_change = await session.execute(query)
            sequences_with_aa_change = sequences_with_aa_change.fetchall()
            query_composer.add_filter(aa_change_id, sequences_with_aa_change)
        if host_sample_id:
            query = f"{select_query} from sequence natural join sequencing_project natural join host_sample hs " \
                    f"where hs.host_sample_id = {host_sample_id} " \
                    f"and virus_id = 1 " \
                    f"{final_pagination_stmt};"
            sequences_of_host_sample = await session.execute(query)
            sequences_of_host_sample = sequences_of_host_sample.fetchall()
            query_composer.add_filter(host_sample_id, sequences_of_host_sample)

        query_composer.intersect_results(lambda x: x.sequence_id)
        if query_composer.result() != FilterIntersection.NO_FILTERS:
            return query_composer.result()
        else:
            query = f"{select_query} from sequence natural join sequencing_project " \
                    f"where virus_id = 1 " \
                    f"{final_pagination_stmt};"
            all_sequences = await session.execute(query)
            return all_sequences.fetchall()

    # try:
    #     # stmt = select(Sequence).limit(10)
    #     # result = await session.execute(stmt)
    #     # for x in result.fetchall():
    #     #     print(x[0].sequence_id)
    #     print(Sequence.__name__)
    #     query = "select sequence_id from sequence limit 10"
    #     # query = select([Column("sequence_id")]).limit(10)
    #     result = await session.execute(query)
    #     for x in result.scalars().all():
    #         # print(x.sequence_id, x.length)
    #         print(x)
    #
    # finally:
    #     await await session.close()
    # return None


@app.get('/sequences/{sequence_id}')
async def get_sequence(sequence_id: int):
    async with get_session() as session:
        query = f"select sequence_id, accession_id, database_source, length, n_percentage, gc_percentage  " \
                f"from sequence natural join sequencing_project " \
                f"where sequence_id = {sequence_id} " \
                f"limit 1;"
        result = await session.execute(query)
        result = result.fetchall()
        return result


@app.get('/host_samples')
async def get_host_samples(sequence_id: Optional[int] = None
                           , pagination: dict = Depends(mandatory_pagination)):
    pagination_stmt = f'order by host_sample_id {pagination["stmt"]}'
    async with get_session() as session:
        query_composer = FilterIntersection()
        select_from_query = \
            "select host_sample_id, geo_group as \"continent\", country, region, collection_date, " \
            "host_taxon_name as \"host_specie\" " \
            "from host_sample natural join host_specie "

        if sequence_id:
            query = f"{select_from_query} natural join sequence s " \
                    f"where s.sequence_id = {sequence_id} " \
                    f"and s.virus_id = 1 " \
                    f"{pagination_stmt};"
            host_samples_of_sequence_id = await session.execute(query)
            host_samples_of_sequence_id = host_samples_of_sequence_id.fetchall()
            query_composer.add_filter(sequence_id, host_samples_of_sequence_id)

        query_composer.intersect_results(lambda x: x.host_sample_id)
        if query_composer.result() != FilterIntersection.NO_FILTERS:
            return query_composer.result()
        else:
            query = f"{select_from_query} natural join sequence where virus_id = 1 {pagination_stmt};"
            all_host_samples = await session.execute(query)
            all_host_samples = all_host_samples.fetchall()
            return all_host_samples


@app.get('/host_samples/{host_sample_id}')
async def get_host_sample(host_sample_id):
    async with get_session() as session:
        result = await session.execute(
            "select host_sample_id, geo_group as \"continent\", country, region, collection_date, "
            "host_taxon_name as \"host_specie\" "
            "from host_sample natural join host_specie "
            f"where host_sample_id = {host_sample_id} "
            f"limit 1;"
        )
        return result.fetchall()


@app.get('/nuc_mutations')
async def get_nuc_mutations(sequence_id: Optional[int] = None
                            , nuc_positional_mutation_id: Optional[str] = None
                            , pagination: dict = Depends(mandatory_pagination)):
    pagination_stmt = f'order by sequence_original, start_original, sequence_alternative ' \
                      f'{pagination["stmt"]}'
    async with get_session() as session:
        query_composer = FilterIntersection()
        select_from_where_query = \
            "select distinct upper(concat(sequence_original, start_original, sequence_alternative)) as \"nuc_mutation_id\", " \
            "upper(sequence_original) as \"reference\", " \
            " start_original as \"position\", upper(sequence_alternative) as \"alternative\", " \
            "variant_type as \"type\", variant_length as \"length\" " \
            "from nucleotide_variant natural join sequence where virus_id = 1 "

        if sequence_id:
            query = f"{select_from_where_query} and sequence_id = {sequence_id} " \
                    f"{pagination_stmt};"
            nuc_mutations_of_sequence = await session.execute(query)
            nuc_mutations_of_sequence = nuc_mutations_of_sequence.fetchall()
            query_composer.add_filter(sequence_id, nuc_mutations_of_sequence)
        if nuc_positional_mutation_id:
            result = await get_nuc_mutation(nuc_positional_mutation_id)
            query_composer.add_filter(nuc_positional_mutation_id, result)

        query_composer.intersect_results(lambda x: x.nuc_mutation_id)
        if query_composer.result() != FilterIntersection.NO_FILTERS:
            return query_composer.result()
        else:
            query = f"{select_from_where_query} {pagination_stmt};"
            all_mutations = await session.execute(query)
            all_mutations = all_mutations.fetchall()
            return all_mutations


@app.get('/nuc_mutations/{nuc_mutation_id}')
async def get_nuc_mutation(nuc_mutation_id: str):
    async with get_session() as session:
        ref, pos, alt = kb_nuc_mut_2_vcm_nuc_mut(nuc_mutation_id)
        query = "select upper(concat(sequence_original, start_original, sequence_alternative)) as \"nuc_mutation_id\", " \
                "upper(sequence_original) as \"reference\", " \
                "start_original as \"position\", upper(sequence_alternative) as \"alternative\", " \
                "variant_type as \"type\", variant_length as \"length\" " \
                "from nucleotide_variant natural join sequence " \
                "where virus_id = 1 " \
                f"and sequence_original = '{ref}' " \
                f"and start_original = {pos} " \
                f"and sequence_alternative = '{alt}' " \
                f"limit 1;"
        mutations_equal_to_positional_mutation = await session.execute(query)
        return mutations_equal_to_positional_mutation.fetchall()


@app.get('/aa_changes')
async def get_aa_changes(sequence_id: Optional[int] = None
                         , protein_id: Optional[str] = None
                         , aa_positional_change_id: Optional[str] = None
                         , pagination: dict = Depends(mandatory_pagination)):
    pagination_stmt = f'order by product, reference, position, alternative {pagination["stmt"]}'
    async with get_session() as session:
        query_composer = FilterIntersection()
        # the following query omits the aa_change_id because it is built using the protein, but the protein name
        # must be converted
        select_from_where_query = \
            "select distinct product as \"protein\", sequence_aa_original as \"reference\", " \
            "start_aa_original as \"position\", sequence_aa_alternative as \"alternative\", " \
            "variant_aa_type as \"type\", variant_aa_length as \"length\" " \
            "from aminoacid_variant natural join annotation natural join sequence where virus_id = 1 "

        if sequence_id:
            query = f"{select_from_where_query} and sequence_id = {sequence_id} {pagination_stmt};"
            aa_changes_of_sequence = await session.execute(query)
            aa_changes_of_sequence = [vcm_aa_change_2_aa_change_id(x) for x in aa_changes_of_sequence.fetchall()]
            query_composer.add_filter(sequence_id, aa_changes_of_sequence)
        if protein_id:
            query = f"{select_from_where_query} and product = '{short_protein_name_2_vcm_syntax.get(protein_id, '_')}' " \
                    f"{pagination_stmt};"
            aa_changes_in_prot = await session.execute(query)
            aa_changes_in_prot = [vcm_aa_change_2_aa_change_id(x, protein_id) for x in aa_changes_in_prot.fetchall()]
            query_composer.add_filter(protein_id, aa_changes_in_prot)
        if aa_positional_change_id:
            result = await get_aa_change(aa_positional_change_id)
            query_composer.add_filter(aa_positional_change_id, result)

        query_composer.intersect_results(lambda x: x["aa_change_id"])
        if query_composer.result() != FilterIntersection.NO_FILTERS:
            return query_composer.result()
        else:
            query = f"{select_from_where_query} {pagination_stmt};"
            all_aa_changes = await session.execute(query)
            all_aa_changes = [vcm_aa_change_2_aa_change_id(x) for x in all_aa_changes.fetchall()]
            return all_aa_changes


@app.get('/aa_changes/{aa_change_id}')
async def get_aa_change(aa_change_id: str):
    async with get_session() as session:
        prot, ref, pos, alt = aa_change_id_2_vcm_aa_change(aa_change_id)
        result = await session.execute(
            "select product as \"protein\", sequence_aa_original as \"reference\", "
            "start_aa_original as \"position\", sequence_aa_alternative as \"alternative\", "
            "variant_aa_type as \"type\", variant_aa_length as \"length\" "
            "from aminoacid_variant natural join annotation natural join sequence where virus_id = 1 "
            f"and product = '{prot}' "
            f"and sequence_aa_original = '{ref}' "
            f"and start_aa_original = {pos} "
            f"and sequence_aa_alternative = '{alt}' "
            f"limit 1;"
        )
        result = [vcm_aa_change_2_aa_change_id(x) for x in result.fetchall()]
        return result


@app.get('/epitopes')
async def get_epitopes(assay_id: Optional[int] = None
                       , protein_id: Optional[str] = None
                       , aa_positional_change_id: Optional[str] = None
                       , pagination: dict = Depends(mandatory_pagination)):
    pagination_stmt = f'order by epi_fragment_id {pagination["stmt"]}'
    query_composer = FilterIntersection()
    select_from_where_query = f"select epi_fragment_id as \"epitope_id\" , protein_name as \"protein_id\", " \
                              f"host_taxon_name as \"host_species\", epi_frag_annotation_start as \"epitope_start\", " \
                              f"epi_frag_annotation_stop as \"epitope_stop\" " \
                              f"from epitope natural join epitope_fragment natural join host_specie " \
                              f"where virus_id = 1 "
    async with get_session() as session:
        if assay_id:
            query = f"{select_from_where_query} " \
                    f"and (assay_type, mhc_allele, mhc_class) = ( " \
                    "   select assay_type, mhc_allele, mhc_class " \
                    "   from epitope " \
                    f"  where epitope_id = {assay_id} limit 1 ) " \
                    f"{pagination_stmt};"
            epitopes_in_assay = await session.execute(query)
            epitopes_in_assay = [epitope_protein_2_kb_protein(x) for x in epitopes_in_assay.fetchall()]
            query_composer.add_filter(assay_id, epitopes_in_assay)
        if protein_id:
            vcm_protein = short_protein_name_2_vcm_syntax.get(protein_id, "_")
            query = f"{select_from_where_query} " \
                    f"and protein_name = '{vcm_protein}' {pagination_stmt};"
            epitopes_in_protein = await session.execute(query)
            epitopes_in_protein = [epitope_protein_2_kb_protein(x, protein_id) for x in epitopes_in_protein.fetchall()]
            query_composer.add_filter(protein_id, epitopes_in_protein)
        if aa_positional_change_id:
            prot, ref, pos, alt = aa_change_id_2_vcm_aa_change(aa_positional_change_id)
            query = f"{select_from_where_query} and protein_name = '{prot}' " \
                    f"and epi_frag_annotation_start < {pos} and epi_frag_annotation_stop > {pos} " \
                    f"{pagination_stmt};"
            epitopes_over_aa_change = await session.execute(query)
            epitopes_over_aa_change = [epitope_protein_2_kb_protein(x) for x in epitopes_over_aa_change.fetchall()]
            query_composer.add_filter(aa_positional_change_id, epitopes_over_aa_change)

        query_composer.intersect_results(lambda x: x["epitope_id"])
        if query_composer.result() != FilterIntersection.NO_FILTERS:
            return query_composer.result()
        else:
            query = f"{select_from_where_query} {pagination_stmt};"
            all_epitopes = await session.execute(query)
            all_epitopes = [epitope_protein_2_kb_protein(x) for x in all_epitopes.fetchall()]
            return all_epitopes


@app.get('/epitopes/{epitope_id}')
async def get_epitope(epitope_id: int):
    async with get_session() as session:
        result = await session.execute(
            f"select epi_fragment_id as \"epitope_id\" , protein_name as \"protein_id\", "
            f"host_taxon_name as \"host_species\", epi_frag_annotation_start as \"epitope_start\", "
            f"epi_frag_annotation_stop as \"epitope_stop\" "
            f"from epitope natural join epitope_fragment natural join host_specie "
            f"where virus_id = 1 "
            f"and epi_fragment_id = {epitope_id} "
            f"limit 1;"
        )
        return [epitope_protein_2_kb_protein(x) for x in result.fetchall()]


@app.get('/assays')
async def get_assays(epitope_id: Optional[int] = None
                     , pagination: dict = Depends(mandatory_pagination)):
    pagination_stmt = f'order by assay_type, mhc_class, mhc_allele, epitope_id {pagination["stmt"]}'
    query_composer = FilterIntersection()
    select_from_query = "select distinct on (assay_type, mhc_class, mhc_allele) " \
                        "epitope_id as \"assay_id\", assay_type, mhc_class, mhc_allele as \"mhc_restriction\" " \
                        "from epitope"
    async with get_session() as session:
        if epitope_id:
            query = f"{select_from_query} natural join epitope_fragment where virus_id = 1 " \
                    f"and epi_fragment_id = {epitope_id} " \
                    f"{pagination_stmt};"
            assays_of_epitope = await session.execute(query)
            assays_of_epitope = assays_of_epitope.fetchall()
            query_composer.add_filter(epitope_id, assays_of_epitope)

        query_composer.intersect_results(lambda x: x.assay_id)
        if query_composer.result() != FilterIntersection.NO_FILTERS:
            return query_composer.result()
        else:
            query = f"{select_from_query} where virus_id = 1 {pagination_stmt};"
            all_assays = await session.execute(query)
            all_assays = all_assays.fetchall()
            return all_assays

    # other option for generating an hash-like ID but is ugly
    # select_query = "select concat_ws('#', assay_type, mhc_class, mhc_allele) as \"assay_id\", " \
    #                "assay_type, mhc_class, mhc_allele as \"mhc_restriction\" " \
    #                "from epitope "
    # convert assay_id to binary
    # all_assays = [{
    #         "assay_id": base64.b64encode(x["assay_id"].encode()),
    #         "assay_type": x.assay_type,
    #         "mhc_class": x.mhc_class,
    #         "mhc_allele": x.mhc_restriction
    #     } for x in all_assays]


@app.get('/assays/{assay_id}')
async def get_assay(assay_id: int):
    async with get_session() as session:
        result = await session.execute(
            f"select {assay_id} as \"assay_id\", "
            f"assay_type, mhc_class, mhc_allele as \"mhc_restriction\" "
            f"from epitope "
            f"where epitope_id = {assay_id} and virus_id = 1 "
            f"limit 1;"
        )
        return result.fetchall()


class FilterIntersection:
    NO_FILTERS = "!NO_FILTERS"

    def __init__(self):
        self._query2result = dict()
        self._result_combined_filters = FilterIntersection.NO_FILTERS

    def add_filter(self, input_query, result):
        if input_query:
            self._query2result[input_query] = result
        return self

    def intersect_results(self, use_id_selector: Callable):
        if len(self._query2result) == 1:
            self._result_combined_filters = list(self._query2result.values())[0]
        elif len(self._query2result) == 0:
            pass
        else:
            keys = list(self._query2result.keys())
            common_ids = set((use_id_selector(x) for x in self._query2result[keys[0]]))
            for k in keys[1:]:
                common_ids.intersection_update((use_id_selector(x) for x in self._query2result[k]))
            self._result_combined_filters = [x for x in self._query2result[keys[0]] if use_id_selector(x) in common_ids]
        return self

    def result(self):
        return self._result_combined_filters


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
        'sequences': 'get_sequence',
        'host_samples': 'get_host_sample',
        'nuc_mutations': 'get_nuc_mutation',
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
    def make_function_call(cls, entity_name: str, path_params, query_params: dict, pagination: dict):
        function_name = cls._endpoint_of_entity[entity_name]  # default
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
            if entity_name in ('sequences', 'host_samples', 'aa_changes', 'nuc_mutations', 'epitopes', 'assays'):
                return eval(function_name)(**query_params, pagination=pagination)
            else:
                return eval(function_name)(**query_params)

    @classmethod
    def get_id_of_entity(cls, entity_name: str) -> str:
        return cls._ID_of_entity[entity_name]


class CombinePaginationSimulation:
    def __init__(self, limit, page):
        self.limit = limit
        self.page = page
        # self.elements_to_skip_counter = self.slice_start_idx()

    def slice_start_idx(self):
        return self.limit * self.page

    def slice_stop_idx(self):
        return self.limit * (self.page + 1)
