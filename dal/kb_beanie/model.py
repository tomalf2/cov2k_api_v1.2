from typing import *
from pydantic import Field, BaseModel
from beanie import Document, init_beanie, PydanticObjectId
import motor
from loguru import logger


class Alias(BaseModel):
    org: str
    name: str
    v_class: Optional[str] = None


class Org2Change(BaseModel):
    org: str
    changes: List[str]


class Variant(Document):
    # document's "_id" is implicitly mapped to the automatically added field "id" in this object
    # here, I have to tell that the id can be also of type str
    id: Union[PydanticObjectId, str] = Field(primary_field=True)
    aliases: List[Alias]
    org_2_aa_changes: List[Org2Change]
    org_2_nuc_changes: List[Org2Change]
    effects: List[PydanticObjectId]

    class Collection:
        name = "variant"


class Effect(Document):
    type: Optional[str] = None
    lv: Optional[str] = None
    method: Optional[str] = None
    aa_changes: List[str] = None
    aa_change_groups: List[PydanticObjectId] = None

    class Collection:
        name = "effect"


class NUCChange(Document):
    change_id: str
    ref: str
    pos: int
    alt: str
    type: str
    length: int
    is_optional: bool

    class Collection:
        name = "nuc_change"


class AAChange(NUCChange):
    protein: str

    class Collection:
        name = "aa_change"


class EffectSource(Document):
    effect_ids: List[PydanticObjectId]
    citation: Optional[str]
    type: Optional[str]
    uri: Optional[str]
    publisher: Optional[str]

    class Collection:
        name = "evidence"


class ProteinCharacterization(BaseModel):
    protein_name: str
    aa_length: Optional[int]
    aa_sequence: Optional[str]


class Structure(Document):
    annotation_id: str
    start_on_ref: int
    stop_on_ref: int
    protein_characterization: Optional[List[ProteinCharacterization]]

    class Collection:
        name = "structure"


class ProteinRegion(Document):
    protein_name: str
    start_on_prot: Optional[int]
    stop_on_prot: Optional[int]
    description: Optional[str]
    _type: Optional[str]

    class Collection:
        name = "protein_region"


class GranthamDistance(BaseModel):
    pass


class AAResidue(Document):
    residue: str
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
    grantham_distance: Dict

    class Collection:
        name = "aa_residue"


class Rule(Document):
    owner: str
    rule: Optional[str]

    class Collection:
        name = "rule"


# Call this from within your event loop to get beanie setup.
async def init_db_model(db_name: str):
    # Crete Motor client
    client = motor.motor_asyncio.AsyncIOMotorClient(
        "mongodb://localhost:27017"
    )

    logger.info(f"Connecting to MONGO DB  {db_name}")
    # Init beanie with the Product document class
    await init_beanie(database=client[db_name],
                      document_models=[Variant, Effect, NUCChange, AAChange, EffectSource, Structure, ProteinRegion,
                                       AAResidue, Rule])


def read_mongodb_connection_parameters(file_path: str):
    with open(file_path, mode='r') as f:
        f.readline()
        db_name = f.readline().rstrip()
    return db_name
