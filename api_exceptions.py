from fastapi import HTTPException, status


class MyExceptions:
    compose_request_path_cycle_detected = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST
        , detail="A path cycle was detected in the request. Path cycles are forbidden.")
    unrecognised_aa_residue_change_id = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        , detail="The given aa_residue_change_id is not valid. A valud aa_residue_change_id is made of two AA residue "
                 "letters.")
    illegal_parameters_combination = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST
        , detail="The request express an illegal conjunction of parameters and cannot be interpreted")
    unrecognized_aa_positional_change_id = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        , detail="The given aa_positional_change_id is not syntactically valid.")
    unrecognized_aa_change_id = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        , detail="The given aa_change_id is not syntactically valid.")
    unrecognised_nuc_positional_mutation_id = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        , detail="The given nuc_positional_mutation_id is not syntactically valid.")
    unrecognised_nuc_mutation_id = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        , detail="The given nuc_mutation_id is not syntactically valid.")
    compose_request_unrecognised_command = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST
        , detail="The request contains unrecognised entities.")
    compose_request_no_entity_specified = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST
        , detail="The request does not point to any entity")
    compose_request_unrecognised_query_parameter = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST
        , detail="The request contains a unrecognised query parameter.")
    incomplete_optional_pagination_params = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST
        , detail="The request specifies only one between page and limit. You should define either both or none."
    )
    @staticmethod
    def compose_request_intermediate_result_too_large(request_name):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST
            , detail=f"The intermediate entity {request_name} produces an exceptional high number of results "
                     f"(> 10000) and cannot be handled. It is suggested to retry with different parameters in "
                     f"order to reduce computational cost.")

