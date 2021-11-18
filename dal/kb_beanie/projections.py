from typing import *
from pydantic import Field, BaseModel
from beanie import PydanticObjectId
from dal.kb_beanie.model import Alias, Org2Change, ProteinRegion, GranthamDistance


class MyBaseModel(BaseModel):
    def __getitem__(self, item):
        return getattr(self, item)


class VariantsProjection(MyBaseModel):
    # use "_id", not ID in projected models
    variant_id: Union[PydanticObjectId, str]

    class Settings:
        projection = {"variant_id": "$_id"}


class NamingsProjection(MyBaseModel):
    naming_id: str
    organization: str
    v_class: str

    class Settings:
        projection = {""}


class AAPositionalChangeProjection(MyBaseModel):
    aa_positional_change_id: str
    protein_id: str
    reference: str
    position: int
    alternative: str
    type: str
    length: int

    class Settings:
        projection = {"aa_positional_change_id": "$change_id", "protein_id": "$protein",
                      "reference": "$ref", "position": "$pos",
                      "alternative": "$alt", "type": "$type", "length": "$length", "_id": 0}


class NUCPositionalMutationProjection(MyBaseModel):
    nuc_positional_mutation_id: str
    reference: str
    position: int
    alternative: str
    type: str
    length: int

    class Settings:
        projection = {"nuc_positional_mutation_id": "$change_id", "reference": "$ref", "position": "$pos",
                      "alternative": "alt", "type": "$type", "length": "$length", "_id": 0}


class EffectProjection(MyBaseModel):
    effect_id: PydanticObjectId
    type: Optional[str]
    lv: Optional[str]
    method: Optional[str]

    class Settings:
        projection = {"effect_id": "$_id", "type": "$type", "lv": "$lv", "method": "$method"}


class EvidenceProjection(MyBaseModel):
    evidence_id: PydanticObjectId
    citation: Optional[str]
    type: Optional[str]
    uri: Optional[str]
    publisher: Optional[str]

    class Settings:
        projection = {"evidence_id": "$_id", "citation": "$citation", "type": "$type", "uri": "$uri",
                      "publisher": "$publisher"}


class AAChangeGroupProjection(MyBaseModel):
    aa_change_group_id: PydanticObjectId

    class Settings:
        projection = {"aa_change_group_id": "$_id"}


class NucAnnotationProjection(MyBaseModel):
    nuc_annotation_id: str
    name: str
    start_on_ref: int
    stop_on_ref: int

    class Settings:
        projection = {"nuc_annotation_id": {'$toString': '$_id'}, "name": "$annotation_id"
            , "start_on_ref": "$start_on_ref", "stop_on_ref": "$stop_on_ref"}


class ProteinProjection(MyBaseModel):
    protein_id: str
    aa_length: int
    aa_sequence: str


class ProteinRegionProjection(MyBaseModel):
    protein_region_id: PydanticObjectId
    name: Optional[str]
    type: Optional[str]
    protein_id: Optional[str]
    start_on_protein: Optional[int]
    stop_on_protein: Optional[int]

    class Settings:
        projection = {"protein_region_id": "$_id", "name": "$description", "type": "$type"
            , "protein_id": "$protein_name", "start_on_protein": "$start_on_prot", "stop_on_protein": "$stop_on_prot"}


class AAResidueChangeProjection(MyBaseModel):
    aa_residue_change_id: str
    reference: str
    alternative: str
    grantham_distance: int
    type: int


class AAResidueProjection(MyBaseModel):
    aa_residue_id: str
    molecular_weight: int
    isoelectric_point: float
    hydrophobicity: float
    potential_side_chain_h_bonds: int
    polarity: str
    r_group_structure: str
    charge: Optional[str]
    essentiality: str
    side_chain_flexibility: str
    chemical_group_in_the_side_chain: str

    class Settings:
        projection = {
            'aa_residue_id': '$residue',
            'molecular_weight': '$molecular_weight',
            'isoelectric_point': '$isoelectric_point',
            'hydrophobicity': '$hydrophobicity',
            'potential_side_chain_h_bonds': '$potential_side_chain_h_bonds',
            'polarity': '$polarity',
            'r_group_structure': '$r_group_structure',
            'charge': '$charge',
            'essentiality': '$essentiality',
            'side_chain_flexibility': '$side_chain_flexibility',
            'chemical_group_in_the_side_chain': '$chemical_group_in_the_side_chain'
        }


class RuleProjection(MyBaseModel):
    owner: str
    rule: Optional[str]

    class Settings:
        projection = {"_id": 0}