from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, Float, SmallInteger, REAL, Date
from sqlalchemy.engine import Engine
from sqlalchemy.orm.session import Session
from sqlalchemy.future import select

_db_engine: Engine
_base = declarative_base()
_session_factory: sessionmaker = None
_last_config_parameters = ()


def config_db_engine(db_name, db_user, db_psw, db_port):
    """
    Call this method once to initialize the database session factory and prepare it to execute queries.
    """
    global _db_engine, _session_factory, _last_config_parameters
    _last_config_parameters = (db_name, db_user, db_psw, db_port)
    logger.info('configuring db... make sure a connection is available')
    _db_engine = create_async_engine(f'postgresql+asyncpg://{db_user}:{db_psw}@localhost:{db_port}/{db_name}', echo=True)\
        .execution_options(schema_translate_map={None: "public"})

    _session_factory = sessionmaker(bind=_db_engine, expire_on_commit=False, class_=AsyncSession, autocommit=False)
    logger.info('db configured')


def read_connection_parameters_csv(file_path: str):
    with open(file_path, mode='r') as f:
        f.readline()
        db_name, db_user, db_psw, db_port = f.readline().rstrip().split(",")
    return db_name, db_user, db_psw, db_port


def get_session() -> Session:
    return _session_factory()


async def dispose_db_engine():
    await _db_engine.dispose()


class HostSpecie(_base):
    __tablename__ = 'host_specie'

    host_id = Column(Integer, primary_key=True, autoincrement=True)

    host_taxon_id = Column(Integer)
    host_taxon_name = Column(String)


class HostSample(_base):
    __tablename__ = 'host_sample'

    host_sample_id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer)
    collection_date = Column(String)
    coll_date_precision = Column(SmallInteger)
    isolation_source = Column(String)
    originating_lab = Column(String)

    province = Column(String)
    region = Column(String)
    country = Column(String)
    geo_group = Column(String)

    #     extra
    age = Column(Integer)
    gender = Column(String)


class SequencingProject(_base):
    __tablename__ = 'sequencing_project'

    sequencing_project_id = Column(Integer, primary_key=True, autoincrement=True)

    sequencing_lab = Column(String)
    submission_date = Column(Date)
    database_source = Column(String)
    bioproject_id = Column(String)


class Sequence(_base):
    __tablename__ = 'sequence'

    sequence_id = Column(Integer, primary_key=True, autoincrement=True)
    # FKs
    experiment_type_id = Column(Integer, nullable=False)
    virus_id = Column(Integer, nullable=False)
    host_sample_id = Column(Integer, nullable=False)
    sequencing_project_id = Column(Integer, nullable=False)

    accession_id = Column(String, nullable=False)
    alternative_accession_id = Column(String, nullable=True)
    strain_name = Column(String)
    is_reference = Column(Boolean, nullable=False)
    is_complete = Column(Boolean)
    strand = Column(String)
    length = Column(Integer)
    gc_percentage = Column(Float)
    n_percentage = Column(Float)
    lineage = Column(String)
    clade = Column(String)
    gisaid_only = Column(Boolean, default=True, nullable=False)


class NucleotideSequence(_base):
    __tablename__ = 'nucleotide_sequence'

    sequence_id = Column(Integer, primary_key=True)
    nucleotide_sequence = Column(String)


class Annotation(_base):
    __tablename__ = 'annotation'

    annotation_id = Column(Integer, primary_key=True, autoincrement=True)
    sequence_id = Column(Integer, nullable=False)

    feature_type = Column(String, nullable=False)
    start = Column(Integer)
    stop = Column(Integer)
    gene_name = Column(String)
    product = Column(String)
    external_reference = Column(String)


class AnnotationSequence(_base):
    __tablename__ = 'annotation_sequence'

    annotation_id = Column(Integer, primary_key=True)
    sequence_id = Column(Integer, nullable=False)

    product = Column(String)
    aminoacid_sequence = Column(String)
    annotation_nucleotide_sequence = Column(String)


class NucleotideVariant(_base):
    __tablename__ = 'nucleotide_variant'

    nucleotide_variant_id = Column(Integer, primary_key=True)
    sequence_id = Column(Integer, nullable=False)

    sequence_original = Column(String, nullable=False)
    sequence_alternative = Column(String, nullable=False)
    start_original = Column(Integer)
    start_alternative = Column(Integer)
    variant_length = Column(Integer, nullable=False)
    variant_type = Column(String, nullable=False)

    def get_list(self):
        return [self.start_original, self.variant_length, self.sequence_original, self.sequence_alternative,
                self.variant_type]

    def get_list_columns(self):
        return ['start', 'length', 'sequence_original', 'alt_sequence', 'variant_type']


class AminoAcidVariant(_base):
    __tablename__ = 'aminoacid_variant'

    aminoacid_variant_id = Column(Integer, primary_key=True)
    annotation_id = Column(Integer, nullable=False)

    sequence_aa_original = Column(String, nullable=False)
    sequence_aa_alternative = Column(String, nullable=False)
    start_aa_original = Column(Integer)
    variant_aa_length = Column(Integer, nullable=False)
    variant_aa_type = Column(String, nullable=False)


class Epitope(_base):
    __tablename__ = 'epitope'

    epitope_id = Column(Integer, primary_key=True, autoincrement=True)
    epitope_iri = Column(String)
    iedb_epitope_id = Column(Integer)
    virus_id = Column(String, nullable=False)
    host_id = Column(Integer, nullable=False)
    source_host_name = Column(String)
    source_host_iri = Column(String)
    protein_name = Column(String)
    cell_type = Column(String)
    mhc_class = Column(String)
    mhc_allele = Column(String)
    response_frequency_pos = Column(REAL)
    epitope_sequence = Column(String)
    epi_annotation_start = Column(Integer)
    epi_annotation_stop = Column(Integer)
    external_link = Column(String)
    prediction_process = Column(String)
    is_linear = Column(Boolean)
    assay_type = Column(String)


class EpitopeFragment(_base):
    __tablename__ = 'epitope_fragment'

    epi_fragment_id = Column(Integer, primary_key=True, autoincrement=True)
    epitope_id = Column(Integer)
    epi_fragment_sequence = Column(String)
    epi_frag_annotation_start = Column(Integer)
    epi_frag_annotation_stop = Column(Integer)